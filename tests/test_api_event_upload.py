from fastapi.testclient import TestClient

from apps.api import main as api_main
from eeg_io.registry import JsonRegistryRepository


def test_upload_event_log_stores_file_and_returns_preview(tmp_path, monkeypatch):
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

    response = client.post(
        "/datasets/dataset-001/files/events",
        files={
            "file": (
                "psychopy.csv",
                (
                    b"stim_onset,condition,key_resp.keys,key_resp.rt\n"
                    b"1.0,target,space,0.42\n"
                ),
                "text/csv",
            )
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["dataset"]["status"] == "needs_mapping"
    assert payload["dataset"]["event_log_id"] == payload["uploaded_file"]["file_id"]
    assert payload["uploaded_file"]["kind"] == "events"
    assert payload["preview"]["columns"] == [
        "stim_onset",
        "condition",
        "key_resp.keys",
        "key_resp.rt",
    ]
    assert payload["preview"]["row_count"] == 1
    assert payload["preview"]["preview_rows"][0]["condition"] == "target"
    assert payload["sidecar_discovery"]["candidates"] == []
    assert repository.get_events_preview("dataset-001") == payload["preview"]


def test_upload_bids_events_file_discovers_events_sidecar(tmp_path, monkeypatch):
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

    response = client.post(
        "/datasets/dataset-001/files/events",
        files={
            "file": (
                "sub-001_task-oddball_events.tsv",
                b"onset\tduration\ttrial_type\n1.0\t0.1\ttarget\n",
                "text/tab-separated-values",
            )
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["sidecar_discovery"]["bids_basename"] == "sub-001_task-oddball"
    assert payload["sidecar_discovery"]["candidates"] == [
        {
            "sidecar_type": "events_tsv",
            "path": payload["uploaded_file"]["stored_path"],
            "status": "valid",
            "diagnostics": [],
        }
    ]
    assert payload["sidecar_files"] == []


def test_upload_event_log_requires_existing_dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(
        api_main,
        "registry_repository",
        JsonRegistryRepository(tmp_path / "uploads"),
    )
    client = TestClient(api_main.app)

    response = client.post(
        "/datasets/missing-dataset/files/events",
        files={"file": ("events.tsv", b"onset\ttrial_type\n1.0\ttarget\n")},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Dataset not found"


def test_upload_event_log_rejects_empty_file(tmp_path, monkeypatch):
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

    response = client.post(
        "/datasets/dataset-001/files/events",
        files={"file": ("events.csv", b"")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Event log is empty"
