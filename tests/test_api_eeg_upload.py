from pathlib import Path
import warnings

from fastapi.testclient import TestClient

from apps.api import main as api_main
from eeg_io.registry import JsonRegistryRepository


def test_upload_eeg_file_extracts_metadata_and_updates_dataset(tmp_path, monkeypatch):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    monkeypatch.setattr(api_main, "registry_repository", repository)
    client = TestClient(api_main.app)
    client.post("/projects", json={"project_id": "project-001", "name": "Memory EEG"})
    client.post(
        "/projects/project-001/experiments",
        json={"experiment_id": "experiment-001", "name": "Oddball task"},
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
    payload = response.json()
    assert payload["dataset"]["dataset_id"] == "dataset-001"
    assert payload["dataset"]["status"] == "needs_mapping"
    assert payload["dataset"]["recording_id"] == payload["recording"]["recording_id"]
    assert payload["uploaded_file"]["kind"] == "eeg"
    assert payload["uploaded_file"]["original_filename"] == "sample_resting_raw.fif"
    assert payload["uploaded_file"]["size_bytes"] > 0
    assert payload["uploaded_file"]["checksum_sha256"]
    assert payload["recording"]["metadata"]["format"] == "fif"
    assert payload["recording"]["metadata"]["channels"] == 8

    stored_path = Path(payload["uploaded_file"]["stored_path"])
    assert stored_path.is_file()
    assert repository.get_recording("dataset-001").recording_id == (
        payload["recording"]["recording_id"]
    )


def test_upload_eeg_file_requires_existing_dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(
        api_main,
        "registry_repository",
        JsonRegistryRepository(tmp_path / "uploads"),
    )
    client = TestClient(api_main.app)
    fixture_path = Path("tests/fixtures/eeg/sample_resting_raw.fif")

    with fixture_path.open("rb") as eeg_file:
        response = client.post(
            "/datasets/missing-dataset/files/eeg",
            files={"file": ("sample_resting_raw.fif", eeg_file)},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Dataset not found"


def test_upload_eeg_file_rejects_unreadable_eeg(tmp_path, monkeypatch):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    monkeypatch.setattr(api_main, "registry_repository", repository)
    client = TestClient(api_main.app)
    client.post("/projects", json={"project_id": "project-001", "name": "Memory EEG"})
    client.post(
        "/projects/project-001/experiments",
        json={"experiment_id": "experiment-001", "name": "Oddball task"},
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

    with warnings.catch_warnings(record=True) as warning_records:
        warnings.simplefilter("always")
        response = client.post(
            "/datasets/dataset-001/files/eeg",
            files={"file": ("not-eeg.fif", b"not an eeg file")},
        )

    assert response.status_code == 422
    assert "Could not read EEG metadata" in response.json()["detail"]
    warning_messages = [str(record.message) for record in warning_records]
    assert any(
        "does not conform to MNE naming conventions" in warning
        for warning in warning_messages
    )
    assert any("Invalid tag" in warning for warning in warning_messages)


def test_upload_eeg_file_does_not_overwrite_existing_filename(tmp_path, monkeypatch):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    monkeypatch.setattr(api_main, "registry_repository", repository)
    client = TestClient(api_main.app)
    client.post("/projects", json={"project_id": "project-001", "name": "Memory EEG"})
    client.post(
        "/projects/project-001/experiments",
        json={"experiment_id": "experiment-001", "name": "Oddball task"},
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
    fixture_path = Path("tests/fixtures/eeg/sample_resting_raw.fif")

    stored_paths = []
    for _ in range(2):
        with fixture_path.open("rb") as eeg_file:
            response = client.post(
                "/datasets/dataset-001/files/eeg",
                files={"file": ("sample_resting_raw.fif", eeg_file)},
            )
        assert response.status_code == 201
        stored_paths.append(response.json()["uploaded_file"]["stored_path"])

    assert stored_paths[0] != stored_paths[1]
    assert Path(stored_paths[1]).name == "sample_resting-1_raw.fif"
    assert Path(stored_paths[0]).is_file()
    assert Path(stored_paths[1]).is_file()
