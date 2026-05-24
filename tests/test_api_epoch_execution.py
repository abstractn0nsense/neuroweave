from pathlib import Path
from time import sleep
import json
import shutil

from fastapi.testclient import TestClient
import mne

from apps.api import main as api_main
from eeg_core.domain import (
    Dataset,
    DatasetStatus,
    EpochConfig,
    EpochRun,
    EpochRunStatus,
    EventColumnMapping,
    EventLog,
    NormalizedEvent,
    PreprocessingConfig,
    PreprocessingRun,
    PreprocessingRunStatus,
    Recording,
    RecordingMetadata,
)
from eeg_io.registry import JsonRegistryRepository, JsonRunRepository
from eeg_processing import epoch_preprocessed_eeg


def _client(tmp_path, monkeypatch) -> TestClient:
    registry = JsonRegistryRepository(tmp_path / "uploads")
    runs = JsonRunRepository(tmp_path / "runs")
    monkeypatch.setattr(api_main, "registry_repository", registry)
    monkeypatch.setattr(api_main, "run_repository", runs)
    monkeypatch.setattr(api_main, "EPOCHS_DIR", tmp_path / "epochs")
    return TestClient(api_main.app)


def _seed_epochable_dataset(tmp_path) -> PreprocessingRun:
    api_main.registry_repository.save_dataset(
        Dataset(
            dataset_id="dataset-001",
            project_id="project-001",
            experiment_id="experiment-001",
            participant_id="participant-001",
            session_id="session-001",
            status=DatasetStatus.VALID,
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
                channel_names=["Fp1", "Fp2", "F3", "F4", "C3", "C4", "P3", "P4"],
            ),
        )
    )
    api_main.registry_repository.save_event_log(
        EventLog(
            event_log_id="event-log-001",
            dataset_id="dataset-001",
            file_id="file-002",
            mapping=EventColumnMapping(onset_seconds="onset", trial_type="trial_type"),
            row_count=3,
            events=[
                NormalizedEvent(
                    onset_seconds=1.0,
                    source_row=1,
                    trial_type="target",
                ),
                NormalizedEvent(
                    onset_seconds=2.0,
                    source_row=2,
                    trial_type="standard",
                ),
                NormalizedEvent(
                    onset_seconds=3.0,
                    source_row=3,
                    trial_type="target",
                ),
            ],
        )
    )

    output_path = (
        tmp_path
        / "processed"
        / "dataset-001"
        / "preprocess-001"
        / "raw_preprocessed_raw.fif"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile("tests/fixtures/eeg/sample_resting_raw.fif", output_path)
    run = PreprocessingRun(
        run_id="preprocess-001",
        dataset_id="dataset-001",
        config=PreprocessingConfig(reference="average"),
        status=PreprocessingRunStatus.COMPLETED,
        output_path=str(output_path),
        output_metadata={
            "output_sampling_rate_hz": 256.0,
            "output_duration_seconds": 4.0,
        },
    )
    api_main.run_repository.save_preprocessing_run(run)
    return run


def _epoch_payload(**overrides) -> dict:
    payload = {
        "preprocessing_run_id": "preprocess-001",
        "condition_field": "trial_type",
        "tmin_seconds": -0.1,
        "tmax_seconds": 0.3,
        "baseline_start_seconds": None,
        "baseline_end_seconds": None,
        "reject_eeg_uv": None,
    }
    payload.update(overrides)
    return payload


def _wait_for_epoch_status(
    client: TestClient,
    run_id: str,
    expected_status: str,
) -> dict:
    for _ in range(120):
        response = client.get(f"/epoch-runs/{run_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] == expected_status:
            return payload
        sleep(0.05)
    raise AssertionError(f"Epoch run {run_id} did not reach {expected_status}")


def test_epoch_worker_completes_run_and_writes_artifacts(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _seed_epochable_dataset(tmp_path)

    response = client.post("/datasets/dataset-001/epoch-runs", json=_epoch_payload())

    assert response.status_code == 201
    queued = response.json()
    assert queued["status"] == "pending"

    payload = _wait_for_epoch_status(client, queued["run_id"], "completed")

    assert payload["started_at_utc"] is not None
    assert payload["finished_at_utc"] is not None
    assert payload["errors"] == []
    assert Path(payload["output_path"]).is_file()
    assert Path(payload["output_path"]).name == "epochs-epo.fif"
    metadata = payload["output_metadata"]
    assert metadata["artifact_root"] == str(Path(payload["output_path"]).parent)
    assert metadata["primary_artifact_path"] == payload["output_path"]
    assert metadata["primary_artifact_size_bytes"] > 0
    assert metadata["primary_artifact_checksum_sha256"]
    assert metadata["artifact_count"] == 4
    assert metadata["output_path"] == payload["output_path"]
    assert metadata["output_size_bytes"] > 0
    assert metadata["output_checksum_sha256"]
    assert metadata["output_file_format"] == "fif"
    assert metadata["output_sampling_rate_hz"] == 256.0
    assert metadata["input_preprocessing_run_id"] == "preprocess-001"
    assert metadata["condition_count"] == 2
    assert metadata["event_count_total"] == 3
    assert metadata["event_count_used"] == 3
    assert metadata["event_count_skipped"] == 0
    assert metadata["epoch_count"] == 3
    assert metadata["dropped_epoch_count"] == 0
    assert metadata["diagnostics_available"] is True
    assert metadata["diagnostics_file_count"] == 3

    summary_path = Path(str(metadata["epoch_summary_path"]))
    condition_counts_path = Path(str(metadata["condition_counts_path"]))
    drop_log_path = Path(str(metadata["drop_log_path"]))
    artifact_manifest_path = Path(str(metadata["artifact_manifest_path"]))
    assert summary_path.is_file()
    assert condition_counts_path.is_file()
    assert drop_log_path.is_file()
    assert artifact_manifest_path.is_file()

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    condition_counts = json.loads(condition_counts_path.read_text(encoding="utf-8"))
    drop_log = json.loads(drop_log_path.read_text(encoding="utf-8"))
    artifact_manifest = json.loads(artifact_manifest_path.read_text(encoding="utf-8"))
    assert summary["run_id"] == payload["run_id"]
    assert summary["dataset_id"] == "dataset-001"
    assert summary["events"]["event_id"] == {"standard": 1, "target": 2}
    assert summary["epochs"]["retained"] == 3
    assert condition_counts["schema_version"] == 1
    assert condition_counts["totals"] == {
        "candidate_event_count": 3,
        "retained_epoch_count": 3,
        "dropped_epoch_count": 0,
    }
    assert condition_counts["conditions"]["standard"] == {
        "event_id": 1,
        "candidate_event_count": 1,
        "retained_epoch_count": 1,
        "dropped_epoch_count": 0,
    }
    assert condition_counts["conditions"]["target"] == {
        "event_id": 2,
        "candidate_event_count": 2,
        "retained_epoch_count": 2,
        "dropped_epoch_count": 0,
    }
    assert summary["timing"] == {
        "tmin_seconds": -0.1,
        "tmax_seconds": 0.3,
        "epoch_duration_seconds": 0.4,
        "baseline": {"start_seconds": None, "end_seconds": None},
        "sampling_rate_hz": 256.0,
        "samples_per_epoch": 104,
    }
    assert drop_log == {
        "schema_version": 1,
        "summary": {
            "retained_epoch_count": 3,
            "dropped_epoch_count": 0,
            "reasons": {},
        },
        "entries": [],
    }
    assert artifact_manifest["artifact_count"] == 4
    assert {
        artifact["logical_name"] for artifact in artifact_manifest["artifacts"]
    } == {"epochs", "epoch_summary", "condition_counts", "drop_log"}


def test_epoch_worker_persists_failed_execution(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _seed_epochable_dataset(tmp_path)

    def fail_epoching_subprocess(*args, **kwargs):
        raise api_main.EpochingError(
            "synthetic epoching failure",
            processing_warnings=["captured epoch warning"],
        )

    monkeypatch.setattr(api_main, "_run_epoching_subprocess", fail_epoching_subprocess)

    response = client.post("/datasets/dataset-001/epoch-runs", json=_epoch_payload())
    payload = _wait_for_epoch_status(client, response.json()["run_id"], "failed")

    assert payload["status"] == "failed"
    assert payload["warnings"] == ["captured epoch warning"]
    assert payload["errors"] == ["synthetic epoching failure"]
    assert not Path(payload["output_path"]).exists()
    assert "epoch_summary_path" not in payload["output_metadata"]
    assert "condition_counts_path" not in payload["output_metadata"]
    assert "drop_log_path" not in payload["output_metadata"]


def test_epoch_diagnostics_summarize_drop_reasons(tmp_path, monkeypatch):
    _client(tmp_path, monkeypatch)
    _seed_epochable_dataset(tmp_path)
    preprocessing_run = api_main.run_repository.get_preprocessing_run("preprocess-001")
    event_log = api_main.registry_repository.get_event_log("dataset-001")
    assert preprocessing_run is not None
    assert event_log is not None
    raw_path = Path(str(preprocessing_run.output_path))
    raw = mne.io.read_raw_fif(raw_path, preload=True, verbose=False)
    data = raw.get_data()
    sample = int(2.0 * raw.info["sfreq"])
    data[:, sample] = 1000e-6
    spiky_raw = mne.io.RawArray(data, raw.info.copy(), verbose=False)
    spiky_raw.save(raw_path, overwrite=True, verbose=False)

    metadata = epoch_preprocessed_eeg(
        input_path=raw_path,
        output_path=tmp_path / "epochs" / "epochs-epo.fif",
        event_log=event_log,
        config=EpochConfig(**_epoch_payload(reject_eeg_uv=500.0)),
        preprocessing_run_id=preprocessing_run.run_id,
    )
    condition_counts = metadata["diagnostics"]["condition_counts"]
    drop_log = metadata["diagnostics"]["drop_log"]
    summary = metadata["diagnostics"]["epoch_summary"]

    assert metadata["epoch_count"] == 2
    assert metadata["dropped_epoch_count"] == 1
    assert condition_counts["totals"] == {
        "candidate_event_count": 3,
        "retained_epoch_count": 2,
        "dropped_epoch_count": 1,
    }
    assert condition_counts["conditions"]["standard"] == {
        "event_id": 1,
        "candidate_event_count": 1,
        "retained_epoch_count": 0,
        "dropped_epoch_count": 1,
    }
    assert condition_counts["conditions"]["target"] == {
        "event_id": 2,
        "candidate_event_count": 2,
        "retained_epoch_count": 2,
        "dropped_epoch_count": 0,
    }
    assert drop_log["summary"]["retained_epoch_count"] == 2
    assert drop_log["summary"]["dropped_epoch_count"] == 1
    assert sum(drop_log["summary"]["reasons"].values()) >= 1
    assert len(drop_log["entries"]) == 1
    assert drop_log["entries"][0]["condition"] == "standard"
    assert drop_log["entries"][0]["event_code"] == 1
    assert drop_log["entries"][0]["event_index"] == 1
    assert drop_log["entries"][0]["sample"] == 512
    assert drop_log["entries"][0]["reasons"]
    assert summary["drop_reasons"] == drop_log["summary"]
    assert summary["conditions"] == condition_counts


def test_epoch_worker_recovers_pending_runs(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _seed_epochable_dataset(tmp_path)
    run_id = "epoch-recovered"
    output_path = tmp_path / "epochs" / "dataset-001" / run_id / "epochs-epo.fif"
    preprocessing_run = api_main.run_repository.get_preprocessing_run("preprocess-001")
    event_log = api_main.registry_repository.get_event_log("dataset-001")
    recording = api_main.registry_repository.get_recording("dataset-001")
    assert preprocessing_run is not None
    run = EpochRun(
        run_id=run_id,
        dataset_id="dataset-001",
        config=EpochConfig(
            preprocessing_run_id="preprocess-001",
            condition_field="trial_type",
            tmin_seconds=-0.1,
            tmax_seconds=0.3,
        ),
        status=EpochRunStatus.PENDING,
        output_path=str(output_path),
        output_metadata=api_main._epoch_input_provenance(
            preprocessing_run=preprocessing_run,
            event_log=event_log,
            recording=recording,
        ),
    )
    api_main.run_repository.save_epoch_run(run)

    api_main.epoch_worker.recover()
    payload = _wait_for_epoch_status(client, run_id, "completed")

    assert payload["output_metadata"]["epoch_count"] == 3
    assert Path(payload["output_path"]).is_file()
