import json

from eeg_core.domain import (
    Dataset,
    DatasetStatus,
    EventColumnMapping,
    EventLog,
    Experiment,
    NormalizedEvent,
    Participant,
    Project,
    Recording,
    RecordingMetadata,
    UploadedFile,
    UploadedFileKind,
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


def test_registry_persists_uploaded_files_and_recording(tmp_path):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    dataset = Dataset(
        dataset_id="dataset-001",
        project_id="project-001",
        experiment_id="experiment-001",
        participant_id="participant-001",
        session_id="session-001",
    )
    uploaded_file = UploadedFile(
        file_id="file-001",
        dataset_id=dataset.dataset_id,
        kind=UploadedFileKind.EEG,
        original_filename="sample_raw.fif",
        stored_path=str(repository.eeg_directory(dataset.dataset_id) / "sample_raw.fif"),
        content_type="application/octet-stream",
        size_bytes=123,
        checksum_sha256="abc123",
    )
    recording = Recording(
        recording_id="recording-001",
        dataset_id=dataset.dataset_id,
        file_id=uploaded_file.file_id,
        metadata=RecordingMetadata(
            dataset_id=dataset.dataset_id,
            file_format="fif",
            channel_count=8,
            sampling_rate_hz=256,
            duration_seconds=4,
            channel_names=["Fp1", "Fp2"],
        ),
    )

    repository.save_dataset(dataset)
    repository.save_uploaded_file(uploaded_file)
    repository.save_recording(recording)

    assert repository.list_uploaded_files(dataset.dataset_id) == [uploaded_file]
    assert repository.get_recording(dataset.dataset_id) == recording
    assert repository.uploaded_files_path(dataset.dataset_id).is_file()
    assert repository.recording_path(dataset.dataset_id).is_file()


def test_registry_persists_event_preview(tmp_path):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    dataset_id = "dataset-001"
    preview = {
        "columns": ["onset", "trial_type"],
        "delimiter": "\t",
        "preview_rows": [{"onset": "0.5", "trial_type": "target"}],
        "row_count": 1,
    }

    repository.save_events_preview(dataset_id, preview)

    assert repository.get_events_preview(dataset_id) == preview
    assert repository.events_preview_path(dataset_id).is_file()


def test_registry_persists_normalized_event_log(tmp_path):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    event_log = EventLog(
        event_log_id="event-log-001",
        dataset_id="dataset-001",
        file_id="file-001",
        mapping=EventColumnMapping(
            onset_seconds="stim_onset",
            trial_type="condition",
        ),
        row_count=1,
        events=[
            NormalizedEvent(
                onset_seconds=1.0,
                source_row=1,
                trial_type="target",
            )
        ],
    )

    repository.save_event_log(event_log)

    assert repository.get_event_log("dataset-001") == event_log
    assert repository.event_log_path("dataset-001").is_file()
