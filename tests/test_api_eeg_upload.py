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


def test_upload_eeg_file_discovers_adjacent_bids_sidecars(tmp_path, monkeypatch):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    monkeypatch.setattr(api_main, "registry_repository", repository)
    client = TestClient(api_main.app)
    _create_dataset(client)
    eeg_directory = repository.eeg_directory("dataset-001")
    eeg_directory.mkdir(parents=True, exist_ok=True)
    (eeg_directory / "sub-001_task-oddball_eeg.json").write_text(
        '{"PowerLineFrequency": 60, "EEGReference": "Cz"}',
        encoding="utf-8",
    )
    (eeg_directory / "sub-001_task-oddball_channels.tsv").write_text(
        "name\ttype\tunits\tstatus\tstatus_description\n"
        "Fp1\tEEG\tuV\tgood\t\n"
        "Fp2\tEEG\tuV\tbad\tnoisy electrode\n",
        encoding="utf-8",
    )
    (eeg_directory / "sub-001_task-oddball_events.tsv").write_text(
        "onset\tduration\ttrial_type\n1.0\t0.1\ttarget\n",
        encoding="utf-8",
    )

    fixture_path = Path("tests/fixtures/eeg/sample_resting_raw.fif")
    with fixture_path.open("rb") as eeg_file:
        response = client.post(
            "/datasets/dataset-001/files/eeg",
            files={
                "file": (
                    "sub-001_task-oddball_eeg.fif",
                    eeg_file,
                    "application/octet-stream",
                )
            },
        )

    assert response.status_code == 201
    payload = response.json()
    assert {
        candidate["sidecar_type"]: candidate["status"]
        for candidate in payload["sidecar_discovery"]["candidates"]
    } == {
        "eeg_json": "valid",
        "channels_tsv": "valid",
        "events_tsv": "valid",
    }
    assert payload["sidecar_discovery"]["diagnostics"] == []
    assert payload["recording"]["metadata"]["line_frequency_hz"] == 60.0
    assert payload["recording"]["metadata"]["reference"] == "Cz"
    assert payload["recording"]["metadata"]["channel_details"][1]["status"] == "bad"
    stored_recording = repository.get_recording("dataset-001")
    assert stored_recording is not None
    assert stored_recording.metadata.reference == "Cz"


def test_upload_eeg_file_reports_invalid_discovered_sidecar_without_failing(
    tmp_path,
    monkeypatch,
):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    monkeypatch.setattr(api_main, "registry_repository", repository)
    client = TestClient(api_main.app)
    _create_dataset(client)
    eeg_directory = repository.eeg_directory("dataset-001")
    eeg_directory.mkdir(parents=True, exist_ok=True)
    (eeg_directory / "sub-001_task-rest_eeg.json").write_text(
        '{"PowerLineFrequency": "sixty"}',
        encoding="utf-8",
    )

    fixture_path = Path("tests/fixtures/eeg/sample_resting_raw.fif")
    with fixture_path.open("rb") as eeg_file:
        response = client.post(
            "/datasets/dataset-001/files/eeg",
            files={
                "file": (
                    "sub-001_task-rest_eeg.fif",
                    eeg_file,
                    "application/octet-stream",
                )
            },
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["sidecar_discovery"]["candidates"][0]["status"] == "invalid"
    assert payload["sidecar_discovery"]["diagnostics"][0]["code"] == (
        "bids_sidecar_invalid"
    )
    assert payload["recording"]["metadata"]["line_frequency_hz"] is None


def test_upload_channels_sidecar_enriches_recording_metadata(tmp_path, monkeypatch):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    monkeypatch.setattr(api_main, "registry_repository", repository)
    client = TestClient(api_main.app)
    _create_dataset(client)
    _upload_fixture_eeg(client)

    sidecar_path = Path("tests/fixtures/bids/sub-001_task-oddball_channels.tsv")
    with sidecar_path.open("rb") as sidecar_file:
        response = client.post(
            "/datasets/dataset-001/files/sidecars",
            files={
                "file": (
                    sidecar_path.name,
                    sidecar_file,
                    "text/tab-separated-values",
                )
            },
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["uploaded_file"]["kind"] == "metadata"
    assert payload["uploaded_file"]["original_filename"].endswith("_channels.tsv")
    assert payload["recording"]["metadata"]["channel_details"] == [
        {
            "name": "Fp1",
            "type": "EEG",
            "units": "uV",
            "status": "good",
            "status_description": None,
        },
        {
            "name": "Fp2",
            "type": "EEG",
            "units": "uV",
            "status": "bad",
            "status_description": "noisy electrode",
        },
        {
            "name": "EOG1",
            "type": "EOG",
            "units": None,
            "status": None,
            "status_description": None,
        },
    ]
    stored_recording = repository.get_recording("dataset-001")
    assert stored_recording is not None
    assert stored_recording.metadata.channel_details[1].status == "bad"


def test_upload_eeg_json_sidecar_enriches_line_frequency_and_reference(
    tmp_path,
    monkeypatch,
):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    monkeypatch.setattr(api_main, "registry_repository", repository)
    client = TestClient(api_main.app)
    _create_dataset(client)
    _upload_fixture_eeg(client)

    sidecar_path = Path("tests/fixtures/bids/sub-001_task-oddball_eeg.json")
    with sidecar_path.open("rb") as sidecar_file:
        response = client.post(
            "/datasets/dataset-001/files/sidecars",
            files={
                "file": (
                    sidecar_path.name,
                    sidecar_file,
                    "application/json",
                )
            },
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["uploaded_file"]["kind"] == "metadata"
    assert payload["recording"]["metadata"]["line_frequency_hz"] == 60.0
    assert payload["recording"]["metadata"]["reference"] == "Cz"
    stored_recording = repository.get_recording("dataset-001")
    assert stored_recording is not None
    assert stored_recording.metadata.line_frequency_hz == 60.0
    assert stored_recording.metadata.reference == "Cz"


def test_upload_sidecar_requires_recording(tmp_path, monkeypatch):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    monkeypatch.setattr(api_main, "registry_repository", repository)
    client = TestClient(api_main.app)
    _create_dataset(client)

    response = client.post(
        "/datasets/dataset-001/files/sidecars",
        files={"file": ("sub-001_task-rest_eeg.json", b"{}")},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Recording not found"


def test_upload_sidecar_rejects_unsupported_filename(tmp_path, monkeypatch):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    monkeypatch.setattr(api_main, "registry_repository", repository)
    client = TestClient(api_main.app)
    _create_dataset(client)
    _upload_fixture_eeg(client)

    response = client.post(
        "/datasets/dataset-001/files/sidecars",
        files={"file": ("participants.tsv", b"participant_id\nsub-001\n")},
    )

    assert response.status_code == 422
    assert "expected *_channels.tsv or *_eeg.json" in response.json()["detail"]


def _create_dataset(client: TestClient) -> None:
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


def _upload_fixture_eeg(client: TestClient) -> None:
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
