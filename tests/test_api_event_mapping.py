from fastapi.testclient import TestClient

from apps.api import main as api_main
from eeg_io.registry import JsonRegistryRepository


def _create_dataset_with_event_upload(repository, monkeypatch):
    monkeypatch.setattr(api_main, "registry_repository", repository)
    client = TestClient(api_main.app)
    client.post("/projects", json={"project_id": "project-001", "name": "Memory EEG"})
    client.post(
        "/projects/project-001/experiments",
        json={
            "experiment_id": "experiment-001",
            "name": "Oddball task",
            "default_event_mapping": {
                "onset_seconds": "stim_onset",
                "trial_type": "condition",
                "correct": "key_resp.corr",
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
    client.post(
        "/datasets/dataset-001/files/events",
        files={
            "file": (
                "psychopy.csv",
                b"stim_onset,condition,key_resp.corr\n1.0,target,1\n2.0,standard,0\n",
                "text/csv",
            )
        },
    )
    return client


def test_map_dataset_events_uses_experiment_default_mapping(tmp_path, monkeypatch):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    client = _create_dataset_with_event_upload(repository, monkeypatch)

    response = client.post("/datasets/dataset-001/events/mapping", json={})
    get_response = client.get("/datasets/dataset-001/events")

    assert response.status_code == 200
    payload = response.json()
    assert payload["dataset_id"] == "dataset-001"
    assert payload["row_count"] == 2
    assert payload["mapping"]["onset_seconds"] == "stim_onset"
    assert payload["events"][0]["onset_seconds"] == 1.0
    assert payload["events"][0]["trial_type"] == "target"
    assert payload["events"][0]["correct"] is True
    assert payload["events"][1]["correct"] is False
    assert get_response.status_code == 200
    assert get_response.json() == payload


def test_map_dataset_events_accepts_request_mapping_override(tmp_path, monkeypatch):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    client = _create_dataset_with_event_upload(repository, monkeypatch)

    response = client.post(
        "/datasets/dataset-001/events/mapping",
        json={
            "mapping": {
                "onset_seconds": "stim_onset",
                "trial_type": "condition",
            }
        },
    )

    assert response.status_code == 200
    assert response.json()["mapping"]["correct"] is None
    assert response.json()["events"][0]["correct"] is None


def test_map_dataset_events_accepts_preset(tmp_path, monkeypatch):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    client = _create_dataset_with_event_upload(repository, monkeypatch)

    response = client.post(
        "/datasets/dataset-001/events/mapping",
        json={"preset": "psychopy"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mapping"]["onset_seconds"] == "stim_onset"
    assert payload["mapping"]["trial_type"] == "condition"
    assert payload["mapping"]["correct"] == "key_resp.corr"
    assert payload["events"][0]["trial_type"] == "target"
    assert payload["events"][0]["correct"] is True


def test_map_dataset_events_mapping_override_takes_precedence_over_preset(
    tmp_path,
    monkeypatch,
):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    client = _create_dataset_with_event_upload(repository, monkeypatch)

    response = client.post(
        "/datasets/dataset-001/events/mapping",
        json={
            "preset": "bids_events",
            "mapping": {
                "onset_seconds": "stim_onset",
                "trial_type": "condition",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mapping"]["onset_seconds"] == "stim_onset"
    assert payload["mapping"]["trial_type"] == "condition"
    assert payload["mapping"]["correct"] is None
    assert payload["events"][0]["trial_type"] == "target"


def test_map_dataset_events_applies_row_filter(tmp_path, monkeypatch):
    repository = JsonRegistryRepository(tmp_path / "uploads")
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
                "trial_type": "trial_type",
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
    client.post(
        "/datasets/dataset-001/files/events",
        files={
            "file": (
                "events.tsv",
                (
                    b"onset\ttrial_type\tstatus\n"
                    b"1.0\ttarget\tkeep\n"
                    b"2.0\tstandard\tkeep\n"
                    b"3.0\ttarget\treject\n"
                ),
                "text/tab-separated-values",
            )
        },
    )

    response = client.post(
        "/datasets/dataset-001/events/mapping",
        json={
            "row_filter": {
                "include": [{"column": "trial_type", "equals": "target"}],
                "exclude": [{"column": "status", "equals": "reject"}],
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["row_count"] == 3
    assert payload["filter_count"] == 2
    assert [event["source_row"] for event in payload["events"]] == [1]
    assert repository.get_event_log("dataset-001").filter_count == 2


def test_map_dataset_events_reports_missing_onset_mapping(tmp_path, monkeypatch):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    client = _create_dataset_with_event_upload(repository, monkeypatch)

    response = client.post(
        "/datasets/dataset-001/events/mapping",
        json={"mapping": {"trial_type": "condition"}},
    )

    assert response.status_code == 422
    assert "onset_seconds" in response.json()["detail"]


def test_get_dataset_events_requires_mapped_event_log(tmp_path, monkeypatch):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    client = _create_dataset_with_event_upload(repository, monkeypatch)

    response = client.get("/datasets/dataset-001/events")

    assert response.status_code == 404
    assert response.json()["detail"] == "Event log not found"
