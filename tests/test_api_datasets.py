from fastapi.testclient import TestClient

from apps.api import main as api_main
from eeg_io.registry import JsonRegistryRepository


def test_create_list_and_get_dataset(tmp_path, monkeypatch):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    monkeypatch.setattr(api_main, "registry_repository", repository)
    client = TestClient(api_main.app)
    client.post("/projects", json={"project_id": "project-001", "name": "Memory EEG"})
    client.post(
        "/projects/project-001/experiments",
        json={"experiment_id": "experiment-001", "name": "Oddball task"},
    )

    create_response = client.post(
        "/datasets",
        json={
            "dataset_id": "dataset-001",
            "project_id": "project-001",
            "experiment_id": "experiment-001",
            "participant_id": "participant-001",
            "participant_label": "sub-001",
            "participant_group": "control",
            "session_id": "session-001",
            "session_label": "ses-001",
            "metadata": {"site": "lab-a"},
        },
    )
    list_response = client.get("/datasets?project_id=project-001")
    get_response = client.get("/datasets/dataset-001")

    assert create_response.status_code == 201
    assert create_response.json() == {
        "dataset_id": "dataset-001",
        "project_id": "project-001",
        "experiment_id": "experiment-001",
        "participant_id": "participant-001",
        "session_id": "session-001",
        "status": "needs_files",
        "recording_id": None,
        "event_log_id": None,
        "metadata": {
            "site": "lab-a",
            "participant_label": "sub-001",
            "session_label": "ses-001",
        },
    }
    assert list_response.status_code == 200
    assert list_response.json()["datasets"] == [create_response.json()]
    assert get_response.status_code == 200
    assert get_response.json() == create_response.json()

    assert repository.get_participant("participant-001").label == "sub-001"
    assert repository.eeg_directory("dataset-001").is_dir()
    assert repository.events_directory("dataset-001").is_dir()


def test_create_dataset_requires_existing_project(tmp_path, monkeypatch):
    monkeypatch.setattr(
        api_main,
        "registry_repository",
        JsonRegistryRepository(tmp_path / "uploads"),
    )
    client = TestClient(api_main.app)

    response = client.post(
        "/datasets",
        json={
            "project_id": "missing-project",
            "experiment_id": "experiment-001",
            "participant_label": "sub-001",
            "session_label": "ses-001",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


def test_create_dataset_requires_project_experiment_pair(tmp_path, monkeypatch):
    monkeypatch.setattr(
        api_main,
        "registry_repository",
        JsonRegistryRepository(tmp_path / "uploads"),
    )
    client = TestClient(api_main.app)
    client.post("/projects", json={"project_id": "project-001", "name": "Memory EEG"})
    client.post("/projects", json={"project_id": "project-002", "name": "Vision EEG"})
    client.post(
        "/projects/project-002/experiments",
        json={"experiment_id": "experiment-002", "name": "Visual task"},
    )

    response = client.post(
        "/datasets",
        json={
            "project_id": "project-001",
            "experiment_id": "experiment-002",
            "participant_label": "sub-001",
            "session_label": "ses-001",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Experiment not found"


def test_get_dataset_returns_404_for_missing_dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(
        api_main,
        "registry_repository",
        JsonRegistryRepository(tmp_path / "uploads"),
    )
    client = TestClient(api_main.app)

    response = client.get("/datasets/missing-dataset")

    assert response.status_code == 404
    assert response.json()["detail"] == "Dataset not found"
