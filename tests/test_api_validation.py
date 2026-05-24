from pathlib import Path

from fastapi.testclient import TestClient

from apps.api import main as api_main
from eeg_io.registry import JsonRegistryRepository


def _client_with_dataset(repository, monkeypatch) -> TestClient:
    monkeypatch.setattr(api_main, "registry_repository", repository)
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


def _upload_and_map_events(client: TestClient, csv_content: bytes) -> None:
    upload_response = client.post(
        "/datasets/dataset-001/files/events",
        files={"file": ("events.csv", csv_content, "text/csv")},
    )
    mapping_response = client.post("/datasets/dataset-001/events/mapping", json={})
    assert upload_response.status_code == 201
    assert mapping_response.status_code == 200


def test_validate_dataset_marks_complete_dataset_valid(tmp_path, monkeypatch):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    client = _client_with_dataset(repository, monkeypatch)
    _upload_eeg(client)
    _upload_and_map_events(
        client,
        (
            b"onset,duration,trial_type,stimulus,response,correct,rt\n"
            b"1.0,0.2,target,A,left,1,0.45\n"
            b"2.0,0.2,standard,B,right,0,0.51\n"
        ),
    )

    response = client.get("/datasets/dataset-001/validation")
    dataset_response = client.get("/datasets/dataset-001")

    assert response.status_code == 200
    payload = response.json()
    assert payload["dataset_id"] == "dataset-001"
    assert payload["status"] == "valid"
    assert payload["valid"] is True
    assert payload["errors"] == []
    assert payload["warnings"] == []
    assert dataset_response.json()["status"] == "valid"


def test_validate_dataset_reports_missing_recording_and_event_log(
    tmp_path,
    monkeypatch,
):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    client = _client_with_dataset(repository, monkeypatch)

    response = client.get("/datasets/dataset-001/validation")
    dataset_response = client.get("/datasets/dataset-001")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "invalid"
    assert payload["valid"] is False
    assert {issue["code"] for issue in payload["errors"]} == {
        "recording_missing",
        "event_log_missing",
    }
    assert dataset_response.json()["status"] == "invalid"


def test_validate_dataset_rejects_events_outside_recording_duration(
    tmp_path,
    monkeypatch,
):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    client = _client_with_dataset(repository, monkeypatch)
    _upload_eeg(client)
    _upload_and_map_events(
        client,
        (
            b"onset,duration,trial_type,stimulus,response,correct,rt\n"
            b"999.0,0.2,target,A,left,1,0.45\n"
        ),
    )

    response = client.get("/datasets/dataset-001/validation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "invalid"
    assert any(
        issue["code"] == "event_onset_out_of_range"
        for issue in payload["errors"]
    )


def test_validate_dataset_keeps_optional_event_fields_as_warnings(
    tmp_path,
    monkeypatch,
):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    client = _client_with_dataset(repository, monkeypatch)
    _upload_eeg(client)
    _upload_and_map_events(
        client,
        b"onset,trial_type\n1.0,target\n2.0,standard\n",
    )

    response = client.get("/datasets/dataset-001/validation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "valid"
    assert payload["valid"] is True
    assert payload["errors"] == []
    assert {issue["code"] for issue in payload["warnings"]} == {
        "event_duration_missing",
        "event_response_missing",
        "event_correct_missing",
        "event_reaction_time_missing",
    }
