from concurrent.futures import ThreadPoolExecutor
import json

from eeg_core.domain import (
    Dataset,
    DatasetStatus,
    EventColumnMapping,
    EventLog,
    Experiment,
    NormalizedEvent,
    Participant,
    PreprocessingConfig,
    PreprocessingRun,
    PreprocessingRunStatus,
    Project,
    Recording,
    RecordingMetadata,
    RunKind,
    UploadedFile,
    UploadedFileKind,
)
from eeg_io.registry import JsonRegistryRepository, JsonRunRepository


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


def test_registry_preserves_concurrent_project_writes(tmp_path):
    repository = JsonRegistryRepository(tmp_path / "uploads")

    def save_project(index: int) -> None:
        repository.save_project(
            Project(project_id=f"project-{index:03}", name=f"Project {index}")
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(save_project, range(24)))

    project_ids = [project.project_id for project in repository.list_projects()]
    assert project_ids == [f"project-{index:03}" for index in range(24)]


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


def test_registry_preserves_concurrent_uploaded_file_writes(tmp_path):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    dataset = Dataset(
        dataset_id="dataset-001",
        project_id="project-001",
        experiment_id="experiment-001",
        participant_id="participant-001",
        session_id="session-001",
    )
    repository.save_dataset(dataset)

    def save_uploaded_file(index: int) -> None:
        repository.save_uploaded_file(
            UploadedFile(
                file_id=f"file-{index:03}",
                dataset_id=dataset.dataset_id,
                kind=UploadedFileKind.EEG,
                original_filename=f"sample-{index:03}_raw.fif",
                stored_path=str(
                    repository.eeg_directory(dataset.dataset_id)
                    / f"sample-{index:03}_raw.fif"
                ),
            )
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(save_uploaded_file, range(24)))

    file_ids = [
        uploaded_file.file_id
        for uploaded_file in repository.list_uploaded_files(dataset.dataset_id)
    ]
    assert file_ids == [f"file-{index:03}" for index in range(24)]


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


def test_run_repository_persists_preprocessing_runs(tmp_path):
    repository = JsonRunRepository(tmp_path / "runs")
    run = PreprocessingRun(
        run_id="preprocess-001",
        dataset_id="dataset-001",
        config=PreprocessingConfig(
            high_pass_hz=1.0,
            low_pass_hz=40.0,
            notch_hz=50.0,
            resample_hz=128.0,
            reference="average",
        ),
        status=PreprocessingRunStatus.COMPLETED,
        started_at_utc="2026-05-24T00:00:00+00:00",
        finished_at_utc="2026-05-24T00:01:00+00:00",
        cancel_requested_at_utc="2026-05-24T00:00:30+00:00",
        output_path="data/processed/dataset-001/preprocess-001/raw_preprocessed.fif",
        output_metadata={"sampling_rate_hz": 128.0},
        warnings=["reference unchanged"],
    )

    repository.save_preprocessing_run(run)

    assert repository.get_preprocessing_run("preprocess-001") == run
    assert repository.list_preprocessing_runs(dataset_id="dataset-001") == [run]
    assert repository.preprocessing_run_path("preprocess-001").is_file()

    stored = json.loads(
        repository.preprocessing_run_path("preprocess-001").read_text(
            encoding="utf-8"
        )
    )
    assert stored["run_kind"] == RunKind.PREPROCESSING
    assert stored["schema_version"] == 1


def test_run_repository_loads_legacy_preprocessing_runs_without_schema_marker(
    tmp_path,
):
    repository = JsonRunRepository(tmp_path / "runs")
    path = repository.preprocessing_run_path("preprocess-legacy")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "run_id": "preprocess-legacy",
                "dataset_id": "dataset-001",
                "config": {"reference": "average"},
                "status": "completed",
                "output_metadata": {"legacy_key": "legacy-value"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    run = repository.get_preprocessing_run("preprocess-legacy")

    assert run is not None
    assert run.run_kind == RunKind.PREPROCESSING
    assert run.schema_version == 1
    assert run.output_metadata["legacy_key"] == "legacy-value"


def test_run_repository_skips_non_preprocessing_run_records(tmp_path):
    repository = JsonRunRepository(tmp_path / "runs")
    future_path = repository.preprocessing_run_path("epoch-001")
    future_path.parent.mkdir(parents=True, exist_ok=True)
    future_path.write_text(
        json.dumps(
            {
                "run_id": "epoch-001",
                "dataset_id": "dataset-001",
                "run_kind": "epoch",
                "schema_version": 1,
                "config": {},
                "status": "completed",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert repository.get_preprocessing_run("epoch-001") is None
    assert repository.list_preprocessing_runs() == []
