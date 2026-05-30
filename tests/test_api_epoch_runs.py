from pathlib import Path

from fastapi.testclient import TestClient

from apps.api import main as api_main
from eeg_core.domain import (
    Dataset,
    DatasetStatus,
    EventColumnMapping,
    EventLog,
    NormalizedEvent,
    PreprocessingConfig,
    PreprocessingRun,
    PreprocessingRunStatus,
    Recording,
    RecordingMetadata,
    RunKind,
)
from eeg_io.registry import JsonRegistryRepository, JsonRunRepository


class FakeEpochWorker:
    def __init__(self) -> None:
        self.enqueued_run_ids: list[str] = []

    def enqueue(self, run_id: str) -> None:
        self.enqueued_run_ids.append(run_id)


def _client(tmp_path, monkeypatch) -> TestClient:
    registry = JsonRegistryRepository(tmp_path / "uploads")
    runs = JsonRunRepository(tmp_path / "runs")
    worker = FakeEpochWorker()
    monkeypatch.setattr(api_main, "registry_repository", registry)
    monkeypatch.setattr(api_main, "run_repository", runs)
    monkeypatch.setattr(api_main, "epoch_worker", worker)
    monkeypatch.setattr(api_main, "EPOCHS_DIR", tmp_path / "epochs")
    return TestClient(api_main.app)


def _seed_dataset(
    tmp_path,
    *,
    status: DatasetStatus = DatasetStatus.VALID,
    preprocessing_status: PreprocessingRunStatus = PreprocessingRunStatus.COMPLETED,
    preprocessing_output_exists: bool = True,
    events: list[NormalizedEvent] | None = None,
) -> PreprocessingRun:
    selected_events = events if events is not None else [
        NormalizedEvent(
            onset_seconds=1.0,
            source_row=1,
            trial_type="standard",
        ),
        NormalizedEvent(
            onset_seconds=2.0,
            source_row=2,
            trial_type="target",
        ),
    ]
    api_main.registry_repository.save_dataset(
        Dataset(
            dataset_id="dataset-001",
            project_id="project-001",
            experiment_id="experiment-001",
            participant_id="participant-001",
            session_id="session-001",
            status=status,
            recording_id="recording-001",
            event_log_id="event-log-001",
        )
    )
    api_main.registry_repository.save_recording(
        Recording(
            recording_id="recording-001",
            dataset_id="dataset-001",
            file_id="file-001",
            metadata=RecordingMetadata(
                dataset_id="dataset-001",
                file_format="fif",
                channel_count=8,
                sampling_rate_hz=256.0,
                duration_seconds=4.0,
                channel_names=["Fp1", "Fp2"],
            ),
        )
    )
    api_main.registry_repository.save_event_log(
        EventLog(
            event_log_id="event-log-001",
            dataset_id="dataset-001",
            file_id="file-002",
            mapping=EventColumnMapping(
                onset_seconds="onset",
                trial_type="trial_type",
            ),
            row_count=len(selected_events),
            events=selected_events,
        )
    )

    output_path = (
        tmp_path
        / "processed"
        / "dataset-001"
        / "preprocess-001"
        / "raw_preprocessed_raw.fif"
    )
    if preprocessing_output_exists:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"placeholder")

    run = PreprocessingRun(
        run_id="preprocess-001",
        dataset_id="dataset-001",
        config=PreprocessingConfig(reference="average"),
        status=preprocessing_status,
        output_path=str(output_path),
        output_metadata={
            "output_sampling_rate_hz": 128.0,
            "output_duration_seconds": 4.0,
        },
    )
    api_main.run_repository.save_preprocessing_run(run)
    return run


def _valid_payload(**overrides) -> dict:
    payload = {
        "preprocessing_run_id": "preprocess-001",
        "condition_field": "trial_type",
        "tmin_seconds": -0.2,
        "tmax_seconds": 0.8,
        "baseline_start_seconds": -0.2,
        "baseline_end_seconds": 0.0,
        "reject_eeg_uv": 150.0,
    }
    payload.update(overrides)
    return payload


def test_create_epoch_run_persists_pending_run(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _seed_dataset(tmp_path)

    response = client.post(
        "/datasets/dataset-001/epoch-runs",
        json=_valid_payload(),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["dataset_id"] == "dataset-001"
    assert payload["run_kind"] == RunKind.EPOCH
    assert payload["schema_version"] == 1
    assert payload["config"] == _valid_payload()
    assert payload["status"] == "pending"
    assert payload["started_at_utc"] is None
    assert payload["finished_at_utc"] is None
    assert payload["cancel_requested_at_utc"] is None
    assert payload["warnings"] == []
    assert payload["errors"] == []
    assert payload["output_metadata"]["input_preprocessing_run_id"] == "preprocess-001"
    assert payload["output_metadata"]["input_sampling_rate_hz"] == 128.0
    assert payload["output_metadata"]["event_log_id"] == "event-log-001"
    assert payload["output_metadata"]["event_count"] == 2

    output_path = Path(payload["output_path"])
    assert output_path.name == "epochs-epo.fif"
    assert output_path.parent.is_dir()
    assert not output_path.exists()

    get_response = client.get(f"/epoch-runs/{payload['run_id']}")
    list_response = client.get("/datasets/dataset-001/epoch-runs")

    assert get_response.status_code == 200
    assert get_response.json() == payload
    assert list_response.status_code == 200
    assert list_response.json()["runs"] == [payload]
    assert len(api_main.run_repository.list_preprocessing_runs("dataset-001")) == 1
    assert api_main.epoch_worker.enqueued_run_ids == [payload["run_id"]]


def test_create_epoch_run_requires_existing_dataset(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/datasets/missing-dataset/epoch-runs",
        json=_valid_payload(),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Dataset not found"


def test_create_epoch_run_requires_existing_preprocessing_run(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _seed_dataset(tmp_path)

    response = client.post(
        "/datasets/dataset-001/epoch-runs",
        json=_valid_payload(preprocessing_run_id="missing-preprocess"),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Preprocessing run not found"


def test_create_epoch_run_rejects_non_completed_preprocessing_run(
    tmp_path,
    monkeypatch,
):
    client = _client(tmp_path, monkeypatch)
    _seed_dataset(
        tmp_path,
        preprocessing_status=PreprocessingRunStatus.RUNNING,
    )

    response = client.post(
        "/datasets/dataset-001/epoch-runs",
        json=_valid_payload(),
    )

    assert response.status_code == 422
    assert (
        "Preprocessing run must be completed before epoching."
        in response.json()["detail"]
    )
    assert api_main.run_repository.list_epoch_runs("dataset-001") == []


def test_create_epoch_run_rejects_invalid_condition_config(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _seed_dataset(tmp_path)

    response = client.post(
        "/datasets/dataset-001/epoch-runs",
        json=_valid_payload(
            condition_field="reaction_time_seconds",
            tmin_seconds=0.8,
            tmax_seconds=0.0,
        ),
    )

    assert response.status_code == 422
    assert "Unsupported condition field: reaction_time_seconds." in response.json()[
        "detail"
    ]
    assert "tmin_seconds must be lower than tmax_seconds." in response.json()["detail"]
    assert api_main.run_repository.list_epoch_runs("dataset-001") == []


def test_create_epoch_run_persists_out_of_bounds_warning(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _seed_dataset(
        tmp_path,
        events=[
            NormalizedEvent(
                onset_seconds=1.0,
                source_row=1,
                trial_type="standard",
            ),
            NormalizedEvent(
                onset_seconds=3.6,
                source_row=2,
                trial_type="target",
            ),
        ],
    )

    response = client.post(
        "/datasets/dataset-001/epoch-runs",
        json=_valid_payload(tmin_seconds=-0.2, tmax_seconds=0.8),
    )

    assert response.status_code == 201
    assert response.json()["warnings"] == [
        "1 candidate events fall outside the epoch window bounds and will be skipped."
    ]
    assert response.json()["diagnostics"]["warnings"][0] == {
        "severity": "warning",
        "source": "validation",
        "code": "unstructured_warning",
        "impact": response.json()["warnings"][0],
        "suggested_action": None,
    }
    stored = api_main.run_repository.get_epoch_run(response.json()["run_id"])
    assert stored is not None
    assert stored.warnings == response.json()["warnings"]
    assert stored.diagnostics["warnings"][0].source == "validation"
    assert stored.diagnostics["warnings"][0].code == "unstructured_warning"
    assert stored.diagnostics["warnings"][0].impact == response.json()["warnings"][0]


def test_get_and_list_epoch_runs_return_404_for_missing_records(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    get_response = client.get("/epoch-runs/missing-run")
    list_response = client.get("/datasets/missing-dataset/epoch-runs")

    assert get_response.status_code == 404
    assert get_response.json()["detail"] == "Epoch run not found"
    assert list_response.status_code == 404
    assert list_response.json()["detail"] == "Dataset not found"
