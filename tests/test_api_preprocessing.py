from pathlib import Path

from fastapi.testclient import TestClient

from apps.api import main as api_main
from eeg_io.registry import JsonRegistryRepository, JsonRunRepository


def _client_with_dataset(tmp_path, monkeypatch) -> TestClient:
    repository = JsonRegistryRepository(tmp_path / "uploads")
    run_repository = JsonRunRepository(tmp_path / "runs")
    monkeypatch.setattr(api_main, "registry_repository", repository)
    monkeypatch.setattr(api_main, "run_repository", run_repository)
    monkeypatch.setattr(api_main, "PROCESSED_DIR", tmp_path / "processed")

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
    payload = response.json()
    assert payload["dataset_id"] == "dataset-001"
    assert payload["status"] == "completed"
    assert payload["config"]["resample_hz"] == 50.0
    assert payload["finished_at_utc"] is not None
    assert payload["errors"] == []
    assert Path(payload["output_path"]).is_file()
    metadata = payload["output_metadata"]
    assert metadata["input_file_id"]
    assert metadata["input_original_filename"] == "sample_resting_raw.fif"
    assert metadata["input_path"].endswith("sample_resting_raw.fif")
    assert metadata["input_size_bytes"] > 0
    assert metadata["input_checksum_sha256"]
    assert metadata["input_sampling_rate_hz"] > 0
    assert metadata["input_duration_seconds"] > 0
    assert metadata["output_path"] == payload["output_path"]
    assert metadata["output_size_bytes"] > 0
    assert metadata["output_checksum_sha256"]
    assert metadata["output_sampling_rate_hz"] == 50.0
    assert metadata["output_duration_seconds"] > 0
    assert metadata["mne_version"]

    get_response = client.get(f"/preprocessing-runs/{payload['run_id']}")
    list_response = client.get("/datasets/dataset-001/preprocessing-runs")

    assert get_response.status_code == 200
    assert get_response.json() == payload
    assert list_response.status_code == 200
    assert list_response.json()["runs"] == [payload]


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
