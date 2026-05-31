from fastapi.testclient import TestClient

from apps.api import main as api_main
from eeg_core.domain import (
    PreprocessingConfig,
    PreprocessingRun,
    PreprocessingRunStatus,
)
from eeg_io.registry import JsonRegistryRepository, JsonRunRepository


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


def test_delete_dataset_local_data_requires_confirmation_and_removes_local_files(
    tmp_path,
    monkeypatch,
):
    registry_repository = JsonRegistryRepository(tmp_path / "uploads")
    run_repository = JsonRunRepository(tmp_path / "runs")
    monkeypatch.setattr(api_main, "registry_repository", registry_repository)
    monkeypatch.setattr(api_main, "run_repository", run_repository)
    monkeypatch.setattr(api_main, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(api_main, "EPOCHS_DIR", tmp_path / "epochs")
    monkeypatch.setattr(api_main, "ERP_DIR", tmp_path / "erp")
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
    (registry_repository.eeg_directory("dataset-001") / "source.fif").write_text(
        "uploaded",
        encoding="utf-8",
    )
    output_dir = tmp_path / "processed" / "dataset-001" / "preprocess-001"
    output_dir.mkdir(parents=True)
    output_path = output_dir / "raw_preprocessed_raw.fif"
    output_path.write_text("processed", encoding="utf-8")
    manifest_path = output_dir / "artifact_manifest.json"
    manifest_path.write_text('{"schema_version": 1}\n', encoding="utf-8")
    run_repository.save_preprocessing_run(
        PreprocessingRun(
            run_id="preprocess-001",
            dataset_id="dataset-001",
            config=PreprocessingConfig(),
            status=PreprocessingRunStatus.COMPLETED,
            output_path=str(output_path),
            output_metadata={"artifact_manifest_path": str(manifest_path)},
        )
    )

    rejected = client.delete(
        "/datasets/dataset-001/local-data?confirm_dataset_id=wrong"
    )
    assert rejected.status_code == 400
    assert rejected.json()["detail"] == "confirm_dataset_id must match dataset_id"

    dry_run = client.delete(
        "/datasets/dataset-001/local-data?confirm_dataset_id=dataset-001&dry_run=true"
    )
    assert dry_run.status_code == 200
    dry_payload = dry_run.json()
    assert dry_payload["deleted"] is False
    assert dry_payload["dry_run"] is True
    assert dry_payload["run_ids"] == {
        "preprocessing": ["preprocess-001"],
        "epoch": [],
        "erp": [],
    }
    assert registry_repository.dataset_directory("dataset-001").is_dir()
    assert output_dir.is_dir()
    assert run_repository.preprocessing_run_directory("preprocess-001").is_dir()

    deleted = client.delete(
        "/datasets/dataset-001/local-data?confirm_dataset_id=dataset-001"
    )
    assert deleted.status_code == 200
    payload = deleted.json()
    assert payload["deleted"] is True
    assert payload["dry_run"] is False
    assert any(path.endswith("dataset-001") for path in payload["deleted_paths"])
    assert registry_repository.get_dataset("dataset-001") is None
    assert not registry_repository.dataset_directory("dataset-001").exists()
    assert not output_dir.exists()
    assert run_repository.get_preprocessing_run("preprocess-001") is None


def test_delete_dataset_local_data_rejects_active_runs(tmp_path, monkeypatch):
    registry_repository = JsonRegistryRepository(tmp_path / "uploads")
    run_repository = JsonRunRepository(tmp_path / "runs")
    monkeypatch.setattr(api_main, "registry_repository", registry_repository)
    monkeypatch.setattr(api_main, "run_repository", run_repository)
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
    run_repository.save_preprocessing_run(
        PreprocessingRun(
            run_id="preprocess-001",
            dataset_id="dataset-001",
            config=PreprocessingConfig(),
            status=PreprocessingRunStatus.RUNNING,
        )
    )

    response = client.delete(
        "/datasets/dataset-001/local-data?confirm_dataset_id=dataset-001"
    )

    assert response.status_code == 409
    assert response.json()["detail"]["active_run_ids"] == ["preprocess-001"]
    assert registry_repository.get_dataset("dataset-001") is not None
