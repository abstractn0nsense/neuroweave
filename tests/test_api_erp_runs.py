from pathlib import Path
from time import sleep
import json
import shutil

from fastapi.testclient import TestClient

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


def _client(tmp_path, monkeypatch) -> TestClient:
    registry = JsonRegistryRepository(tmp_path / "uploads")
    runs = JsonRunRepository(tmp_path / "runs")
    monkeypatch.setattr(api_main, "registry_repository", registry)
    monkeypatch.setattr(api_main, "run_repository", runs)
    monkeypatch.setattr(api_main, "EPOCHS_DIR", tmp_path / "epochs")
    monkeypatch.setattr(api_main, "ERP_DIR", tmp_path / "erp")
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
        / "raw_preprocessed.fif"
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


def _epoch_payload() -> dict:
    return {
        "preprocessing_run_id": "preprocess-001",
        "condition_field": "trial_type",
        "tmin_seconds": -0.1,
        "tmax_seconds": 0.3,
        "baseline_start_seconds": None,
        "baseline_end_seconds": None,
        "reject_eeg_uv": None,
    }


def _wait_for_run_status(
    client: TestClient,
    path: str,
    expected_status: str,
) -> dict:
    for _ in range(120):
        response = client.get(path)
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] == expected_status:
            return payload
        sleep(0.05)
    raise AssertionError(f"Run {path} did not reach {expected_status}")


def _create_completed_epoch_run(client: TestClient) -> dict:
    response = client.post("/datasets/dataset-001/epoch-runs", json=_epoch_payload())
    assert response.status_code == 201
    run_id = response.json()["run_id"]
    return _wait_for_run_status(client, f"/epoch-runs/{run_id}", "completed")


def test_erp_worker_completes_run_and_writes_evoked_artifacts(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _seed_epochable_dataset(tmp_path)
    epoch_run = _create_completed_epoch_run(client)

    response = client.post(
        "/datasets/dataset-001/erp-runs",
        json={"epoch_run_id": epoch_run["run_id"]},
    )

    assert response.status_code == 201
    queued = response.json()
    assert queued["status"] == "pending"

    payload = _wait_for_run_status(client, f"/erp-runs/{queued['run_id']}", "completed")

    assert payload["started_at_utc"] is not None
    assert payload["finished_at_utc"] is not None
    assert payload["errors"] == []
    assert Path(payload["output_path"]).is_file()
    metadata = payload["output_metadata"]
    assert metadata["artifact_root"] == str(Path(payload["output_path"]).parent)
    assert metadata["primary_artifact_path"] == payload["output_path"]
    assert metadata["artifact_count"] == 7
    assert metadata["output_path"] == payload["output_path"]
    assert metadata["output_file_format"] == "fif"
    assert metadata["input_epoch_run_id"] == epoch_run["run_id"]
    assert metadata["condition_count"] == 2
    assert metadata["evoked_count"] == 2
    assert metadata["plot_count"] == 2
    assert metadata["plot_status"] == "completed"
    assert metadata["preview_plot_filename"] == "erp_standard.png"
    assert metadata["preview_plot_url"].startswith(f"/artifacts/{payload['run_id']}/")
    assert metadata["erp_metadata_available"] is True

    erp_metadata_path = Path(str(metadata["erp_metadata_path"]))
    artifact_manifest_path = Path(str(metadata["artifact_manifest_path"]))
    assert erp_metadata_path.is_file()
    assert artifact_manifest_path.is_file()

    erp_metadata = json.loads(erp_metadata_path.read_text(encoding="utf-8"))
    artifact_manifest = json.loads(artifact_manifest_path.read_text(encoding="utf-8"))
    conditions = erp_metadata["conditions"]
    assert erp_metadata["run_id"] == payload["run_id"]
    assert erp_metadata["dataset_id"] == "dataset-001"
    assert [condition["condition"] for condition in conditions] == [
        "standard",
        "target",
    ]
    assert [condition["nave"] for condition in conditions] == [1, 2]
    assert {
        artifact["logical_name"] for artifact in artifact_manifest["artifacts"]
    } == {
        "evoked_standard",
        "evoked_target",
        "png_standard",
        "png_target",
        "svg_standard",
        "svg_target",
        "erp_metadata",
    }
    for condition in conditions:
        assert Path(condition["evoked_path"]).is_file()
        assert Path(condition["plot_png_path"]).is_file()
        assert Path(condition["plot_svg_path"]).is_file()
        assert condition["plot_status"] == "completed"
        assert condition["plot_mode"] == "gfp"
        assert condition["channel_count"] == 8
        assert condition["sampling_rate_hz"] == 256.0
        assert "peak_positive" in condition["channel_time_summary"]
        assert "peak_negative" in condition["channel_time_summary"]
        assert "global_field_power_peak" in condition["channel_time_summary"]

    artifact_response = client.get(
        f"/artifacts/{payload['run_id']}/{metadata['preview_plot_filename']}"
    )
    assert artifact_response.status_code == 200
    assert artifact_response.headers["content-type"] == "image/png"
    assert artifact_response.content.startswith(b"\x89PNG")


def test_erp_run_can_select_condition_subset(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _seed_epochable_dataset(tmp_path)
    epoch_run = _create_completed_epoch_run(client)

    response = client.post(
        "/datasets/dataset-001/erp-runs",
        json={"epoch_run_id": epoch_run["run_id"], "conditions": ["target"]},
    )
    assert response.status_code == 201

    payload = _wait_for_run_status(
        client,
        f"/erp-runs/{response.json()['run_id']}",
        "completed",
    )
    erp_metadata = json.loads(
        Path(str(payload["output_metadata"]["erp_metadata_path"])).read_text(
            encoding="utf-8"
        )
    )

    assert payload["output_metadata"]["condition_count"] == 1
    assert [condition["condition"] for condition in erp_metadata["conditions"]] == [
        "target"
    ]
    assert erp_metadata["conditions"][0]["nave"] == 2


def test_erp_plot_failure_keeps_completed_run_queryable(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _seed_epochable_dataset(tmp_path)
    epoch_run = _create_completed_epoch_run(client)

    response = client.post(
        "/datasets/dataset-001/erp-runs",
        json={
            "epoch_run_id": epoch_run["run_id"],
            "plot_mode": "channel",
            "plot_channel": "missing-channel",
        },
    )
    assert response.status_code == 201

    payload = _wait_for_run_status(
        client,
        f"/erp-runs/{response.json()['run_id']}",
        "completed",
    )
    metadata = payload["output_metadata"]
    erp_metadata = json.loads(
        Path(str(metadata["erp_metadata_path"])).read_text(encoding="utf-8")
    )

    assert payload["status"] == "completed"
    assert payload["errors"] == []
    assert metadata["evoked_count"] == 2
    assert metadata["plot_count"] == 0
    assert metadata["plot_status"] == "partial"
    assert metadata["preview_plot_filename"] is None
    assert payload["warnings"]
    assert all(
        condition["plot_status"] == "failed"
        for condition in erp_metadata["conditions"]
    )
    assert all(
        "ERP plot generation failed" in condition["plot_warnings"][0]
        for condition in erp_metadata["conditions"]
    )


def test_erp_run_rejects_missing_or_failed_epoch_run(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _seed_epochable_dataset(tmp_path)

    missing_response = client.post(
        "/datasets/dataset-001/erp-runs",
        json={"epoch_run_id": "epoch-missing"},
    )
    assert missing_response.status_code == 404

    failed_epoch = EpochRun(
        run_id="epoch-failed",
        dataset_id="dataset-001",
        config=EpochConfig(
            preprocessing_run_id="preprocess-001",
            condition_field="trial_type",
            tmin_seconds=-0.1,
            tmax_seconds=0.3,
        ),
        status=EpochRunStatus.FAILED,
        output_path=str(
            tmp_path / "epochs" / "dataset-001" / "epoch-failed" / "epochs.fif"
        ),
    )
    api_main.run_repository.save_epoch_run(failed_epoch)

    failed_response = client.post(
        "/datasets/dataset-001/erp-runs",
        json={"epoch_run_id": "epoch-failed"},
    )
    assert failed_response.status_code == 422
    assert "Epoch run must be completed before ERP generation." in failed_response.text


def test_erp_worker_persists_failed_execution(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _seed_epochable_dataset(tmp_path)
    epoch_run = _create_completed_epoch_run(client)

    def fail_erp_subprocess(*args, **kwargs):
        raise api_main.ErpError(
            "synthetic ERP failure",
            processing_warnings=["captured ERP warning"],
        )

    monkeypatch.setattr(api_main, "_run_erp_subprocess", fail_erp_subprocess)

    response = client.post(
        "/datasets/dataset-001/erp-runs",
        json={"epoch_run_id": epoch_run["run_id"]},
    )
    payload = _wait_for_run_status(
        client,
        f"/erp-runs/{response.json()['run_id']}",
        "failed",
    )

    assert payload["status"] == "failed"
    assert payload["warnings"] == ["captured ERP warning"]
    assert payload["errors"] == ["synthetic ERP failure"]
    assert not Path(payload["output_path"]).exists()
    assert "erp_metadata_path" not in payload["output_metadata"]
