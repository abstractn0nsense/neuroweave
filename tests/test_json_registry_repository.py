import json

from eeg_core.domain import (
    Dataset,
    DatasetStatus,
    EventColumnMapping,
    Experiment,
    Participant,
    Project,
)
from eeg_io.registry import JsonRegistryRepository


def test_initialize_creates_upload_registry_structure(tmp_path):
    uploads_root = tmp_path / "data" / "raw" / "uploads"
    repository = JsonRegistryRepository(uploads_root)

    repository.initialize()

    assert (uploads_root / "projects.json").read_text(encoding="utf-8") == "[]\n"
    assert (uploads_root / "experiments.json").read_text(encoding="utf-8") == "[]\n"
    assert (uploads_root / "participants.json").read_text(encoding="utf-8") == "[]\n"
    assert (uploads_root / "datasets").is_dir()


def test_registry_persists_project_experiment_and_participant(tmp_path):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    project = Project(project_id="project-001", name="Memory EEG")
    experiment = Experiment(
        experiment_id="experiment-001",
        project_id=project.project_id,
        name="Oddball task",
        task_name="oddball",
        default_event_mapping=EventColumnMapping(
            onset_seconds="stim_onset",
            trial_type="condition",
            reaction_time_seconds="key_resp.rt",
        ),
    )
    participant = Participant(
        participant_id="participant-001",
        project_id=project.project_id,
        label="sub-001",
        group="control",
    )

    repository.save_project(project)
    repository.save_experiment(experiment)
    repository.save_participant(participant)

    assert repository.get_project("project-001") == project
    assert repository.list_experiments(project_id="project-001") == [experiment]
    assert repository.list_participants(project_id="project-001") == [participant]


def test_registry_persists_dataset_metadata_and_file_directories(tmp_path):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    dataset = Dataset(
        dataset_id="dataset-001",
        project_id="project-001",
        experiment_id="experiment-001",
        participant_id="participant-001",
        session_id="session-001",
        status=DatasetStatus.NEEDS_FILES,
    )

    repository.save_dataset(dataset)

    assert repository.get_dataset("dataset-001") == dataset
    assert repository.list_datasets(project_id="project-001") == [dataset]
    assert repository.eeg_directory("dataset-001").is_dir()
    assert repository.events_directory("dataset-001").is_dir()

    metadata = json.loads(
        repository.dataset_metadata_path("dataset-001").read_text(encoding="utf-8")
    )
    assert metadata["dataset_id"] == "dataset-001"
    assert metadata["status"] == "needs_files"


def test_registry_save_updates_existing_records(tmp_path):
    repository = JsonRegistryRepository(tmp_path / "uploads")

    repository.save_project(Project(project_id="project-001", name="Initial"))
    repository.save_project(Project(project_id="project-001", name="Updated"))

    assert repository.get_project("project-001") == Project(
        project_id="project-001",
        name="Updated",
    )
    assert len(repository.list_projects()) == 1
