from fastapi.testclient import TestClient

from apps.api import main as api_main
from eeg_io.registry import JsonRegistryRepository


def test_create_and_list_projects(tmp_path, monkeypatch):
    monkeypatch.setattr(
        api_main,
        "registry_repository",
        JsonRegistryRepository(tmp_path / "uploads"),
    )
    client = TestClient(api_main.app)

    create_response = client.post(
        "/projects",
        json={
            "project_id": "project-001",
            "name": "Memory EEG",
            "description": "Pilot upload registry",
            "metadata": {"site": "lab-a"},
        },
    )
    list_response = client.get("/projects")

    assert create_response.status_code == 201
    assert create_response.json() == {
        "project_id": "project-001",
        "name": "Memory EEG",
        "description": "Pilot upload registry",
        "metadata": {"site": "lab-a"},
    }
    assert list_response.status_code == 200
    assert list_response.json()["projects"] == [create_response.json()]


def test_create_and_list_project_experiments(tmp_path, monkeypatch):
    monkeypatch.setattr(
        api_main,
        "registry_repository",
        JsonRegistryRepository(tmp_path / "uploads"),
    )
    client = TestClient(api_main.app)
    client.post(
        "/projects",
        json={"project_id": "project-001", "name": "Memory EEG"},
    )

    create_response = client.post(
        "/projects/project-001/experiments",
        json={
            "experiment_id": "experiment-001",
            "name": "Oddball task",
            "task_name": "oddball",
            "default_event_mapping": {
                "onset_seconds": "stim_onset",
                "trial_type": "condition",
                "reaction_time_seconds": "key_resp.rt",
            },
        },
    )
    list_response = client.get("/projects/project-001/experiments")

    assert create_response.status_code == 201
    assert create_response.json()["project_id"] == "project-001"
    assert create_response.json()["default_event_mapping"]["onset_seconds"] == (
        "stim_onset"
    )
    assert list_response.status_code == 200
    assert list_response.json()["experiments"] == [create_response.json()]


def test_experiment_routes_require_existing_project(tmp_path, monkeypatch):
    monkeypatch.setattr(
        api_main,
        "registry_repository",
        JsonRegistryRepository(tmp_path / "uploads"),
    )
    client = TestClient(api_main.app)

    create_response = client.post(
        "/projects/missing-project/experiments",
        json={"name": "Oddball task"},
    )
    list_response = client.get("/projects/missing-project/experiments")

    assert create_response.status_code == 404
    assert list_response.status_code == 404
