from pathlib import Path
from time import sleep
from dataclasses import replace
import json

from fastapi.testclient import TestClient
import pytest

from apps.api import main as api_main
from eeg_core.domain import (
    PreprocessingConfig,
    PreprocessingRun,
    PreprocessingRunStatus,
    RunKind,
)
from eeg_io.registry import JsonRegistryRepository, JsonRunRepository


def _client_with_dataset(tmp_path, monkeypatch) -> TestClient:
    repository = JsonRegistryRepository(tmp_path / "uploads")
    run_repository = JsonRunRepository(tmp_path / "runs")
    monkeypatch.setattr(api_main, "registry_repository", repository)
    monkeypatch.setattr(api_main, "run_repository", run_repository)
    monkeypatch.setattr(api_main, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(api_main, "EPOCHS_DIR", tmp_path / "epochs")
    monkeypatch.setattr(api_main, "ERP_DIR", tmp_path / "erp")

    client = TestClient(api_main.app)
    client.post("/projects", json={"project_id": "project-001", "name": "Memory EEG"})
    client.post(
        "/projects/project-001/experiments",
        json={
            "experiment_id": "experiment-001",
            "name": "Oddball task",
            "default_event_mapping": {
                "onset_seconds": "onset",
                "duration_seconds": "duration",
                "trial_type": "trial_type",
                "stimulus": "stimulus",
                "response": "response",
                "correct": "correct",
                "reaction_time_seconds": "rt",
            },
        },
    )
    client.post(
        "/datasets",
        json={
            "dataset_id": "dataset-001",
            "project_id": "project-001",
            "experiment_id": "experiment-001",
            "participant_label": "sub-001",
            "session_label": "ses-001",
        },
    )
    return client


def _upload_eeg(client: TestClient) -> None:
    fixture_path = Path("tests/fixtures/eeg/sample_resting_raw.fif")
    with fixture_path.open("rb") as eeg_file:
        response = client.post(
            "/datasets/dataset-001/files/eeg",
            files={
                "file": (
                    "sample_resting_raw.fif",
                    eeg_file,
                    "application/octet-stream",
                )
            },
        )
    assert response.status_code == 201


def _upload_and_map_events(client: TestClient) -> None:
    fixture_path = Path("tests/fixtures/events/psychopy_minimal.csv")
    with fixture_path.open("rb") as event_file:
        upload_response = client.post(
            "/datasets/dataset-001/files/events",
            files={"file": ("events.csv", event_file, "text/csv")},
        )
    mapping_response = client.post("/datasets/dataset-001/events/mapping", json={})
    assert upload_response.status_code == 201
    assert mapping_response.status_code == 200


def _save_preprocessing_run(
    dataset_id: str = "dataset-001",
    run_id: str = "preprocess-001",
    status: PreprocessingRunStatus = PreprocessingRunStatus.PENDING,
) -> PreprocessingRun:
    run = PreprocessingRun(
        run_id=run_id,
        dataset_id=dataset_id,
        config=PreprocessingConfig(reference="average"),
        status=status,
        output_path=f"data/processed/{dataset_id}/{run_id}/raw_preprocessed_raw.fif",
    )
    api_main.run_repository.save_preprocessing_run(run)
    return run


def _wait_for_run_status(
    client: TestClient,
    run_id: str,
    expected_status: str,
) -> dict:
    for _ in range(100):
        response = client.get(f"/preprocessing-runs/{run_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] == expected_status:
            return payload
        sleep(0.05)
    raise AssertionError(f"Run {run_id} did not reach {expected_status}")


def test_create_preprocessing_run_requires_valid_dataset(tmp_path, monkeypatch):
    client = _client_with_dataset(tmp_path, monkeypatch)

    response = client.post(
        "/datasets/dataset-001/preprocessing-runs",
        json={"reference": "average"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Dataset must be valid before preprocessing."


def test_create_preprocessing_run_writes_output_and_metadata(tmp_path, monkeypatch):
    client = _client_with_dataset(tmp_path, monkeypatch)
    _upload_eeg(client)
    _upload_and_map_events(client)

    response = client.post(
        "/datasets/dataset-001/preprocessing-runs",
        json={"resample_hz": 50.0, "reference": "average"},
    )

    assert response.status_code == 201
    queued_payload = response.json()
    assert queued_payload["dataset_id"] == "dataset-001"
    assert queued_payload["run_kind"] == RunKind.PREPROCESSING
    assert queued_payload["schema_version"] == 1
    assert queued_payload["status"] == "pending"
    assert queued_payload["started_at_utc"] is None
    assert queued_payload["finished_at_utc"] is None
    assert queued_payload["config"]["resample_hz"] == 50.0
    assert queued_payload["output_metadata"]["input_file_id"]
    assert queued_payload["diagnostics"] == {}

    payload = _wait_for_run_status(
        client,
        queued_payload["run_id"],
        "completed",
    )

    assert payload["status"] == "completed"
    assert payload["started_at_utc"] is not None
    assert payload["finished_at_utc"] is not None
    assert payload["errors"] == []
    assert payload["warnings"] == []
    assert Path(payload["output_path"]).is_file()
    assert Path(payload["output_path"]).name == "raw_preprocessed_raw.fif"
    metadata = payload["output_metadata"]
    assert metadata["input_file_id"]
    assert metadata["input_original_filename"] == "sample_resting_raw.fif"
    assert metadata["input_path"].endswith("sample_resting_raw.fif")
    assert metadata["input_size_bytes"] > 0
    assert metadata["input_checksum_sha256"]
    assert metadata["input_sampling_rate_hz"] > 0
    assert metadata["input_duration_seconds"] > 0
    assert metadata["artifact_root"] == str(Path(payload["output_path"]).parent)
    assert metadata["primary_artifact_path"] == payload["output_path"]
    assert metadata["primary_artifact_size_bytes"] > 0
    assert metadata["primary_artifact_checksum_sha256"]
    assert metadata["artifact_count"] == 5
    assert metadata["provenance_available"] is True
    assert metadata["provenance_schema_version"] == 1
    assert metadata["output_path"] == payload["output_path"]
    assert metadata["output_size_bytes"] > 0
    assert metadata["output_checksum_sha256"]
    assert metadata["output_sampling_rate_hz"] == 50.0
    assert metadata["output_duration_seconds"] > 0
    assert metadata["mne_version"]
    assert metadata["diagnostics_available"] is True
    assert metadata["diagnostics_file_count"] == 3
    assert metadata["artifact_bad_channel_count"] == 0
    assert metadata["artifact_annotation_count"] == 0
    assert metadata["artifact_bad_channel_detection_status"] == "not_requested"
    assert metadata["artifact_bad_channel_candidate_count"] == 0
    assert metadata["worker_schema_version"] == 1
    assert metadata["worker_exit_code"] == 0

    summary_path = Path(str(metadata["preprocessing_summary_path"]))
    filter_report_path = Path(str(metadata["filter_report_path"]))
    artifact_summary_path = Path(str(metadata["artifact_summary_path"]))
    artifact_manifest_path = Path(str(metadata["artifact_manifest_path"]))
    provenance_path = Path(str(metadata["provenance_path"]))
    worker_payload_path = Path(str(metadata["worker_payload_path"]))
    worker_result_path = Path(str(metadata["worker_result_path"]))
    worker_stdout_path = Path(str(metadata["worker_stdout_path"]))
    worker_stderr_path = Path(str(metadata["worker_stderr_path"]))
    assert summary_path.is_file()
    assert filter_report_path.is_file()
    assert artifact_summary_path.is_file()
    assert artifact_manifest_path.is_file()
    assert provenance_path.is_file()
    assert worker_payload_path.is_file()
    assert worker_result_path.is_file()
    assert worker_stdout_path.is_file()
    assert worker_stderr_path.is_file()

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    filter_report = json.loads(filter_report_path.read_text(encoding="utf-8"))
    artifact_summary = json.loads(artifact_summary_path.read_text(encoding="utf-8"))
    artifact_manifest = json.loads(artifact_manifest_path.read_text(encoding="utf-8"))
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    worker_payload = json.loads(worker_payload_path.read_text(encoding="utf-8"))
    worker_result = json.loads(worker_result_path.read_text(encoding="utf-8"))
    assert summary["config"]["resample_hz"] == 50.0
    assert summary["output"]["sampling_rate_hz"] == 50.0
    assert filter_report["resample"]["status"] == "applied"
    assert filter_report["reference"]["status"] == "applied"
    assert artifact_summary["artifact_rejection"]["enabled"] is False
    assert worker_payload["schema_version"] == 1
    assert worker_payload["job"] == "preprocessing"
    assert worker_payload["run_id"] == payload["run_id"]
    assert worker_payload["config"]["resample_hz"] == 50.0
    assert worker_result["schema_version"] == 1
    assert worker_result["status"] == "completed"
    assert worker_result["error"] is None
    assert artifact_manifest["schema_version"] == 1
    assert artifact_manifest["artifact_root"] == str(Path(payload["output_path"]).parent)
    assert artifact_manifest["artifact_count"] == 5
    assert {
        artifact["logical_name"] for artifact in artifact_manifest["artifacts"]
    } == {
        "raw_preprocessed",
        "preprocessing_summary",
        "filter_report",
        "artifact_summary",
        "provenance",
    }
    assert provenance["run"]["run_id"] == payload["run_id"]
    assert provenance["run"]["run_kind"] == "preprocessing"
    assert provenance["sources"][0]["role"] == "eeg_file"
    assert provenance["config_snapshot"]["reference"] == "average"
    assert provenance["software_versions"]["mne"] == metadata["mne_version"]
    for artifact in artifact_manifest["artifacts"]:
        artifact_path = Path(str(artifact["path"])).resolve()
        assert artifact_path.is_relative_to(Path(str(metadata["artifact_root"])).resolve())

    list_response = client.get("/datasets/dataset-001/preprocessing-runs")

    assert list_response.status_code == 200
    assert list_response.json()["runs"] == [payload]


def test_create_preprocessing_run_accepts_artifact_aware_contract(
    tmp_path,
    monkeypatch,
):
    client = _client_with_dataset(tmp_path, monkeypatch)
    _upload_eeg(client)
    _upload_and_map_events(client)
    recording = api_main.registry_repository.get_recording("dataset-001")
    assert recording is not None
    channel_name = recording.metadata.channel_names[0]

    response = client.post(
        "/datasets/dataset-001/preprocessing-runs",
        json={
            "manual_bad_channels": [channel_name],
            "bad_channel_detection": {
                "enabled": True,
                "method": "deviation",
                "zscore_threshold": 4.0,
            },
            "bad_channel_interpolation": {"enabled": True},
            "ica": {
                "enabled": True,
                "n_components": 0.95,
                "exclude_components": [0],
                "eog_channels": [channel_name],
            },
            "artifact_handling": {
                "eog_enabled": True,
                "eog_channels": [channel_name],
            },
            "qc": {"metrics": ["channel_status", "psd", "ica"]},
        },
    )

    assert response.status_code == 201
    queued_payload = response.json()
    assert queued_payload["config"]["artifact_schema_version"] == 1
    assert queued_payload["config"]["manual_bad_channels"] == [channel_name]
    assert queued_payload["config"]["bad_channel_detection"]["method"] == "deviation"
    assert queued_payload["config"]["bad_channel_interpolation"]["enabled"] is True
    assert queued_payload["config"]["ica"]["exclude_components"] == [0]
    assert queued_payload["config"]["artifact_handling"]["eog_channels"] == [
        channel_name
    ]
    assert queued_payload["config"]["qc"]["metrics"] == [
        "channel_status",
        "psd",
        "ica",
    ]

    payload = _wait_for_run_status(client, queued_payload["run_id"], "completed")

    assert "ICA config was captured but is not executed until Phase B7." in payload[
        "warnings"
    ]
    artifact_summary_path = Path(
        str(payload["output_metadata"]["artifact_summary_path"])
    )
    artifact_summary = json.loads(artifact_summary_path.read_text(encoding="utf-8"))
    assert artifact_summary["schema_version"] == 1
    assert artifact_summary["bad_channels"]["manual"]["channels"] == [channel_name]
    assert payload["output_metadata"]["artifact_bad_channel_detection_status"] == (
        "completed"
    )
    assert payload["output_metadata"]["artifact_bad_channel_candidate_count"] == 0
    assert artifact_summary["bad_channels"]["detection"]["status"] == "completed"
    assert artifact_summary["bad_channels"]["detection"]["candidate_count"] == 0
    assert artifact_summary["bad_channels"]["interpolation"]["status"] == "schema_only"
    assert artifact_summary["ica"]["status"] == "schema_only"
    assert artifact_summary["qc"]["config"]["metrics"] == [
        "channel_status",
        "psd",
        "ica",
    ]


def test_create_preprocessing_run_rejects_unknown_artifact_channel(
    tmp_path,
    monkeypatch,
):
    client = _client_with_dataset(tmp_path, monkeypatch)
    _upload_eeg(client)
    _upload_and_map_events(client)

    response = client.post(
        "/datasets/dataset-001/preprocessing-runs",
        json={"manual_bad_channels": ["MissingChannel"]},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == [
        "manual_bad_channels contains unknown channels: MissingChannel"
    ]


def test_create_preprocessing_run_persists_failed_run_details(
    tmp_path,
    monkeypatch,
):
    client = _client_with_dataset(tmp_path, monkeypatch)
    _upload_eeg(client)
    _upload_and_map_events(client)

    def fail_preprocessing_subprocess(*args, **kwargs):
        raise api_main.WorkerSubprocessError(
            "synthetic preprocessing failure",
            worker_exit_code=1,
            processing_warnings=["captured warning before failure"],
        )

    monkeypatch.setattr(
        api_main,
        "_run_preprocessing_subprocess",
        fail_preprocessing_subprocess,
    )

    response = client.post(
        "/datasets/dataset-001/preprocessing-runs",
        json={"reference": "average"},
    )
    failed_payload = _wait_for_run_status(
        client,
        response.json()["run_id"],
        "failed",
    )
    list_response = client.get("/datasets/dataset-001/preprocessing-runs")

    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert list_response.status_code == 200
    runs = list_response.json()["runs"]
    assert len(runs) == 1
    assert runs[0] == failed_payload
    assert failed_payload["status"] == "failed"
    assert failed_payload["warnings"] == ["captured warning before failure"]
    assert failed_payload["diagnostics"]["warnings"][0] == {
        "severity": "warning",
        "source": "preprocessing",
        "code": "unstructured_warning",
        "impact": "captured warning before failure",
        "suggested_action": None,
    }
    assert failed_payload["errors"] == ["synthetic preprocessing failure"]
    assert runs[0]["output_metadata"]["input_file_id"]
    assert runs[0]["output_metadata"]["worker_exit_code"] == 1
    stored_run = api_main.run_repository.get_preprocessing_run(
        failed_payload["run_id"]
    )
    assert stored_run is not None
    assert stored_run.diagnostics["warnings"][0].source == "preprocessing"
    assert stored_run.diagnostics["warnings"][0].code == "unstructured_warning"
    assert stored_run.diagnostics["warnings"][0].impact == (
        "captured warning before failure"
    )


def test_preprocessing_subprocess_failure_preserves_worker_artifacts(
    tmp_path,
    monkeypatch,
):
    run_repository = JsonRunRepository(tmp_path / "runs")
    monkeypatch.setattr(api_main, "run_repository", run_repository)
    worker_artifacts = api_main._preprocessing_worker_artifact_paths(
        "preprocess-failed"
    )

    try:
        api_main._run_preprocessing_subprocess(
            run_id="preprocess-failed",
            input_path=str(tmp_path / "input.fif"),
            output_path=str(tmp_path / "output.fif"),
            config=PreprocessingConfig(high_pass_hz=True),
            worker_artifacts=worker_artifacts,
        )
    except api_main.WorkerSubprocessError as exc:
        error = exc
    else:
        raise AssertionError("Expected preprocessing subprocess to fail.")

    assert error.worker_exit_code == 1
    assert str(error) == "Payload config high_pass_hz must be a number or null."
    assert worker_artifacts["payload"].is_file()
    assert worker_artifacts["result"].is_file()
    assert worker_artifacts["stdout"].is_file()
    assert worker_artifacts["stderr"].is_file()
    result = json.loads(worker_artifacts["result"].read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert result["run_id"] == "preprocess-failed"


@pytest.mark.parametrize(
    ("process_label", "error_cls"),
    [
        ("Preprocessing", api_main.WorkerSubprocessError),
        ("Epoching", api_main.EpochWorkerSubprocessError),
        ("ERP", api_main.ErpWorkerSubprocessError),
    ],
)
def test_worker_result_loader_reports_malformed_results(
    tmp_path,
    process_label,
    error_cls,
):
    missing_path = tmp_path / "missing_result.json"
    with pytest.raises(error_cls) as missing_error:
        api_main._load_worker_result(
            result_path=missing_path,
            returncode=7,
            stderr="boom",
            process_label=process_label,
            error_cls=error_cls,
        )
    assert missing_error.value.worker_exit_code == 7
    assert str(missing_error.value) == (
        f"{process_label} subprocess exited with code 7. stderr: boom"
    )

    invalid_path = tmp_path / "invalid_result.json"
    invalid_path.write_text("{", encoding="utf-8")
    with pytest.raises(error_cls) as invalid_error:
        api_main._load_worker_result(
            result_path=invalid_path,
            returncode=0,
            stderr="",
            process_label=process_label,
            error_cls=error_cls,
        )
    assert invalid_error.value.worker_exit_code == 0
    assert str(invalid_error.value) == (
        f"{process_label} subprocess returned invalid JSON."
    )

    non_object_path = tmp_path / "non_object_result.json"
    non_object_path.write_text("[]", encoding="utf-8")
    with pytest.raises(error_cls) as non_object_error:
        api_main._load_worker_result(
            result_path=non_object_path,
            returncode=0,
            stderr="",
            process_label=process_label,
            error_cls=error_cls,
        )
    assert non_object_error.value.worker_exit_code == 0
    assert str(non_object_error.value) == (
        f"{process_label} subprocess returned a non-object result."
    )


def test_cancel_pending_preprocessing_run_marks_cancelled(tmp_path, monkeypatch):
    client = _client_with_dataset(tmp_path, monkeypatch)
    _save_preprocessing_run(status=PreprocessingRunStatus.PENDING)

    cancel_response = client.post("/preprocessing-runs/preprocess-001/cancel")
    get_response = client.get("/preprocessing-runs/preprocess-001")

    assert cancel_response.status_code == 200
    payload = cancel_response.json()
    assert payload["status"] == "cancelled"
    assert payload["finished_at_utc"] is not None
    assert payload["cancel_requested_at_utc"] is not None
    assert payload["warnings"] == ["Run cancelled before preprocessing started."]
    assert get_response.json() == payload


def test_cancel_running_preprocessing_run_requests_cancellation(
    tmp_path,
    monkeypatch,
):
    client = _client_with_dataset(tmp_path, monkeypatch)
    _save_preprocessing_run(status=PreprocessingRunStatus.RUNNING)

    response = client.post("/preprocessing-runs/preprocess-001/cancel")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "cancelling"
    assert payload["finished_at_utc"] is None
    assert payload["cancel_requested_at_utc"] is not None
    assert payload["warnings"] == [
        "Cancellation requested; preprocessing will stop at the next checkpoint."
    ]


def test_preprocessing_run_cancel_checkpoint_marks_cancelled(
    tmp_path,
    monkeypatch,
):
    client = _client_with_dataset(tmp_path, monkeypatch)
    _upload_eeg(client)
    _upload_and_map_events(client)

    def cancel_during_preprocessing_subprocess(run_id, **kwargs):
        run = api_main.run_repository.list_preprocessing_runs()[0]
        api_main.run_repository.save_preprocessing_run(
            replace(
                run,
                status=PreprocessingRunStatus.CANCELLING,
                cancel_requested_at_utc="2026-05-24T00:00:00+00:00",
                warnings=["Cancellation requested; preprocessing will stop at the next checkpoint."],
            )
        )
        assert api_main._is_cancellation_requested(run_id)
        raise api_main.PreprocessingError(
            "Preprocessing cancelled.",
            processing_warnings=["Cancellation terminated preprocessing subprocess."],
        )

    monkeypatch.setattr(
        api_main,
        "_run_preprocessing_subprocess",
        cancel_during_preprocessing_subprocess,
    )

    response = client.post(
        "/datasets/dataset-001/preprocessing-runs",
        json={"reference": "average"},
    )
    payload = _wait_for_run_status(client, response.json()["run_id"], "cancelled")

    assert payload["status"] == "cancelled"
    assert payload["cancel_requested_at_utc"] == "2026-05-24T00:00:00+00:00"
    assert payload["errors"] == ["Preprocessing cancelled."]
    assert "Cancellation terminated preprocessing subprocess." in payload["warnings"]


def test_preprocessing_worker_recovers_pending_runs(tmp_path, monkeypatch):
    client = _client_with_dataset(tmp_path, monkeypatch)
    _upload_eeg(client)
    _upload_and_map_events(client)

    recording = api_main.registry_repository.get_recording("dataset-001")
    assert recording is not None
    uploaded_file = next(
        uploaded_file
        for uploaded_file in api_main.registry_repository.list_uploaded_files(
            "dataset-001"
        )
        if uploaded_file.file_id == recording.file_id
    )
    run_id = "preprocess-recovered"
    output_path = (
        tmp_path / "processed" / "dataset-001" / run_id / "raw_preprocessed_raw.fif"
    )
    run = PreprocessingRun(
        run_id=run_id,
        dataset_id="dataset-001",
        config=PreprocessingConfig(resample_hz=50.0, reference="average"),
        status=PreprocessingRunStatus.PENDING,
        output_path=str(output_path),
        output_metadata=api_main._preprocessing_input_provenance(
            uploaded_file=uploaded_file,
            recording=recording,
        ),
    )
    api_main.run_repository.save_preprocessing_run(run)

    api_main.preprocessing_worker.recover()
    payload = _wait_for_run_status(client, run_id, "completed")

    assert payload["output_metadata"]["output_sampling_rate_hz"] == 50.0
    assert Path(payload["output_path"]).is_file()


def test_create_preprocessing_run_rejects_invalid_filter_order(
    tmp_path,
    monkeypatch,
):
    client = _client_with_dataset(tmp_path, monkeypatch)
    _upload_eeg(client)
    _upload_and_map_events(client)

    response = client.post(
        "/datasets/dataset-001/preprocessing-runs",
        json={"high_pass_hz": 40.0, "low_pass_hz": 1.0},
    )

    assert response.status_code == 422
    assert "high_pass_hz must be lower than low_pass_hz." in response.json()["detail"]


def test_create_preprocessing_run_rejects_cutoff_at_or_above_nyquist(
    tmp_path,
    monkeypatch,
):
    client = _client_with_dataset(tmp_path, monkeypatch)
    _upload_eeg(client)
    _upload_and_map_events(client)

    response = client.post(
        "/datasets/dataset-001/preprocessing-runs",
        json={"low_pass_hz": 999.0},
    )

    assert response.status_code == 422
    assert any("Nyquist frequency" in error for error in response.json()["detail"])


def test_create_preprocessing_run_rejects_upsampling_and_unknown_reference(
    tmp_path,
    monkeypatch,
):
    client = _client_with_dataset(tmp_path, monkeypatch)
    _upload_eeg(client)
    _upload_and_map_events(client)

    response = client.post(
        "/datasets/dataset-001/preprocessing-runs",
        json={"resample_hz": 999.0, "reference": "MissingChannel"},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any("input sampling rate" in error for error in detail)
    assert "reference contains unknown channels: MissingChannel" in detail


def test_analysis_output_path_helpers_use_configured_roots(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "PROCESSED_DIR", tmp_path / "processed-root")
    monkeypatch.setattr(api_main, "EPOCHS_DIR", tmp_path / "epochs-root")
    monkeypatch.setattr(api_main, "ERP_DIR", tmp_path / "erp-root")

    assert api_main._preprocessing_output_path(
        "dataset-001",
        "preprocess-001",
    ) == (
        tmp_path
        / "processed-root"
        / "dataset-001"
        / "preprocess-001"
        / "raw_preprocessed_raw.fif"
    )
    assert api_main._epoch_output_path("dataset-001", "epoch-001") == (
        tmp_path / "epochs-root" / "dataset-001" / "epoch-001" / "epochs-epo.fif"
    )
    assert api_main._erp_output_directory("dataset-001", "erp-001") == (
        tmp_path / "erp-root" / "dataset-001" / "erp-001"
    )
