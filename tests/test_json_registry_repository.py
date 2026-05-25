from concurrent.futures import ThreadPoolExecutor
import json

from eeg_core.domain import (
    ChannelMetadata,
    Dataset,
    DatasetStatus,
    DiagnosticWarning,
    EpochConfig,
    EpochRun,
    EpochRunStatus,
    ErpConfig,
    ErpRun,
    ErpRunStatus,
    EventColumnMapping,
    EventLog,
    EventRowFilter,
    EventRowFilterCondition,
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
    ValidationSeverity,
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
    assert repository.metadata_directory("dataset-001").is_dir()

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

    stored = json.loads(
        repository.recording_path(dataset.dataset_id).read_text(encoding="utf-8")
    )
    assert stored["metadata"]["channel_details"] == []
    assert stored["metadata"]["line_frequency_hz"] is None
    assert stored["metadata"]["reference"] is None


def test_registry_loads_legacy_recording_metadata_without_sidecar_fields(tmp_path):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    recording_path = repository.recording_path("dataset-001")
    recording_path.parent.mkdir(parents=True, exist_ok=True)
    recording_path.write_text(
        json.dumps(
            {
                "recording_id": "recording-legacy",
                "dataset_id": "dataset-001",
                "file_id": "file-001",
                "metadata": {
                    "dataset_id": "dataset-001",
                    "file_format": "fif",
                    "channel_count": 2,
                    "sampling_rate_hz": 256.0,
                    "duration_seconds": 4.0,
                    "channel_names": ["Fp1", "Fp2"],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    recording = repository.get_recording("dataset-001")

    assert recording is not None
    assert recording.metadata.channel_details == []
    assert recording.metadata.line_frequency_hz is None
    assert recording.metadata.reference is None


def test_registry_loads_recording_metadata_with_sidecar_fields(tmp_path):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    recording_path = repository.recording_path("dataset-001")
    recording_path.parent.mkdir(parents=True, exist_ok=True)
    recording_path.write_text(
        json.dumps(
            {
                "recording_id": "recording-001",
                "dataset_id": "dataset-001",
                "file_id": "file-001",
                "metadata": {
                    "dataset_id": "dataset-001",
                    "file_format": "fif",
                    "channel_count": 2,
                    "sampling_rate_hz": 256.0,
                    "duration_seconds": 4.0,
                    "channel_names": ["Fp1", "Fp2"],
                    "channel_details": [
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
                    ],
                    "line_frequency_hz": 60,
                    "reference": "Cz",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    recording = repository.get_recording("dataset-001")

    assert recording is not None
    assert recording.metadata.channel_details == [
        ChannelMetadata(
            name="Fp1",
            type="EEG",
            units="uV",
            status="good",
            status_description=None,
        ),
        ChannelMetadata(
            name="Fp2",
            type="EEG",
            units="uV",
            status="bad",
            status_description="noisy electrode",
        ),
    ]
    assert recording.metadata.line_frequency_hz == 60.0
    assert recording.metadata.reference == "Cz"


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


def test_registry_persists_filtered_event_log_metadata(tmp_path):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    event_log = EventLog(
        event_log_id="event-log-001",
        dataset_id="dataset-001",
        file_id="file-001",
        mapping=EventColumnMapping(onset_seconds="onset", trial_type="trial_type"),
        row_count=3,
        filter_count=2,
        row_filter=EventRowFilter(
            include=[EventRowFilterCondition(column="trial_type", equals="target")],
            exclude=[EventRowFilterCondition(column="status", equals="reject")],
        ),
        provenance={
            "schema_version": 1,
            "preset": "bids_events",
            "mapping_snapshot": {"onset_seconds": "onset"},
            "row_filter_snapshot": {
                "include": [{"column": "trial_type", "equals": "target"}],
                "exclude": [{"column": "status", "equals": "reject"}],
            },
        },
        events=[NormalizedEvent(onset_seconds=1.0, source_row=1, trial_type="target")],
    )

    repository.save_event_log(event_log)

    assert repository.get_event_log("dataset-001") == event_log


def test_registry_loads_legacy_event_log_without_filter_metadata(tmp_path):
    repository = JsonRegistryRepository(tmp_path / "uploads")
    repository.save_dataset_files_directory("dataset-001")
    repository.event_log_path("dataset-001").write_text(
        json.dumps(
            {
                "event_log_id": "event-log-001",
                "dataset_id": "dataset-001",
                "file_id": "file-001",
                "mapping": {"onset_seconds": "onset"},
                "row_count": 1,
                "events": [{"onset_seconds": 1.0, "source_row": 1}],
            }
        ),
        encoding="utf-8",
    )

    event_log = repository.get_event_log("dataset-001")

    assert event_log is not None
    assert event_log.filter_count == 0
    assert event_log.row_filter is None
    assert event_log.provenance == {}


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
        output_path="data/processed/dataset-001/preprocess-001/raw_preprocessed_raw.fif",
        output_metadata={"sampling_rate_hz": 128.0},
        warnings=["reference unchanged"],
        diagnostics={
            "warnings": [
                DiagnosticWarning(
                    severity=ValidationSeverity.WARNING,
                    source="preprocessing",
                    code="reference_unchanged",
                    impact="The original EEG reference was preserved.",
                    suggested_action="Confirm that this matches the analysis plan.",
                )
            ]
        },
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
    assert stored["diagnostics"]["warnings"][0]["code"] == "reference_unchanged"


def test_run_repository_persists_epoch_runs(tmp_path):
    repository = JsonRunRepository(tmp_path / "runs")
    run = EpochRun(
        run_id="epoch-001",
        dataset_id="dataset-001",
        config=EpochConfig(
            preprocessing_run_id="preprocess-001",
            condition_field="trial_type",
            tmin_seconds=-0.2,
            tmax_seconds=0.8,
            baseline_start_seconds=-0.2,
            baseline_end_seconds=0.0,
            reject_eeg_uv=150.0,
        ),
        status=EpochRunStatus.COMPLETED,
        started_at_utc="2026-05-25T00:00:00+00:00",
        finished_at_utc="2026-05-25T00:01:00+00:00",
        cancel_requested_at_utc="2026-05-25T00:00:30+00:00",
        output_path="data/epochs/dataset-001/epoch-001/epochs-epo.fif",
        output_metadata={
            "artifact_root": "data/epochs/dataset-001/epoch-001",
            "condition_count": 2,
        },
        warnings=["some events were skipped"],
    )

    repository.save_epoch_run(run)

    assert repository.get_epoch_run("epoch-001") == run
    assert repository.list_epoch_runs(dataset_id="dataset-001") == [run]
    assert repository.list_preprocessing_runs(dataset_id="dataset-001") == []
    assert repository.epoch_run_path("epoch-001").is_file()

    stored = json.loads(
        repository.epoch_run_path("epoch-001").read_text(encoding="utf-8")
    )
    assert stored["run_kind"] == RunKind.EPOCH
    assert stored["schema_version"] == 1
    assert stored["config"]["preprocessing_run_id"] == "preprocess-001"
    assert stored["config"]["condition_field"] == "trial_type"


def test_run_repository_persists_erp_runs(tmp_path):
    repository = JsonRunRepository(tmp_path / "runs")
    run = ErpRun(
        run_id="erp-001",
        dataset_id="dataset-001",
        config=ErpConfig(
            epoch_run_id="epoch-001",
            conditions=["target", "standard"],
            picks=["Fp1", "Fp2"],
            plot_mode="channel",
            plot_channel="Fp1",
        ),
        status=ErpRunStatus.COMPLETED,
        started_at_utc="2026-05-25T00:00:00+00:00",
        finished_at_utc="2026-05-25T00:01:00+00:00",
        output_path="data/erp/dataset-001/erp-001/erp_metadata.json",
        output_metadata={
            "artifact_root": "data/erp/dataset-001/erp-001",
            "evoked_count": 2,
        },
        warnings=["mne filename warning"],
    )

    repository.save_erp_run(run)

    assert repository.get_erp_run("erp-001") == run
    assert repository.list_erp_runs(dataset_id="dataset-001") == [run]
    assert repository.list_preprocessing_runs(dataset_id="dataset-001") == []
    assert repository.list_epoch_runs(dataset_id="dataset-001") == []
    assert repository.erp_run_path("erp-001").is_file()

    stored = json.loads(repository.erp_run_path("erp-001").read_text(encoding="utf-8"))
    assert stored["run_kind"] == RunKind.ERP
    assert stored["schema_version"] == 1
    assert stored["config"]["epoch_run_id"] == "epoch-001"
    assert stored["config"]["conditions"] == ["target", "standard"]
    assert stored["config"]["plot_mode"] == "channel"
    assert stored["config"]["plot_channel"] == "Fp1"


def test_run_repository_lists_epoch_runs_by_dataset(tmp_path):
    repository = JsonRunRepository(tmp_path / "runs")
    first = EpochRun(
        run_id="epoch-001",
        dataset_id="dataset-001",
        config=EpochConfig(
            preprocessing_run_id="preprocess-001",
            condition_field="trial_type",
            tmin_seconds=-0.2,
            tmax_seconds=0.8,
        ),
    )
    second = EpochRun(
        run_id="epoch-002",
        dataset_id="dataset-002",
        config=EpochConfig(
            preprocessing_run_id="preprocess-002",
            condition_field="stimulus",
            tmin_seconds=-0.1,
            tmax_seconds=0.5,
        ),
    )

    repository.save_epoch_run(second)
    repository.save_epoch_run(first)

    assert repository.list_epoch_runs(dataset_id="dataset-001") == [first]
    assert repository.list_epoch_runs(dataset_id="dataset-002") == [second]
    assert repository.list_epoch_runs() == [first, second]


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
    assert run.warnings == []
    assert run.diagnostics == {}


def test_run_repository_loads_old_epoch_and_erp_runs_without_diagnostics(
    tmp_path,
):
    repository = JsonRunRepository(tmp_path / "runs")
    epoch_path = repository.epoch_run_path("epoch-legacy")
    epoch_path.parent.mkdir(parents=True, exist_ok=True)
    epoch_path.write_text(
        json.dumps(
            {
                "run_id": "epoch-legacy",
                "dataset_id": "dataset-001",
                "run_kind": "epoch",
                "schema_version": 1,
                "config": {
                    "preprocessing_run_id": "preprocess-001",
                    "condition_field": "trial_type",
                    "tmin_seconds": -0.2,
                    "tmax_seconds": 0.8,
                },
                "status": "completed",
                "warnings": ["some events were skipped"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    erp_path = repository.erp_run_path("erp-legacy")
    erp_path.parent.mkdir(parents=True, exist_ok=True)
    erp_path.write_text(
        json.dumps(
            {
                "run_id": "erp-legacy",
                "dataset_id": "dataset-001",
                "run_kind": "erp",
                "schema_version": 1,
                "config": {
                    "epoch_run_id": "epoch-legacy",
                    "method": "mean",
                    "plot_mode": "gfp",
                },
                "status": "completed",
                "warnings": ["plot fallback"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    epoch_run = repository.get_epoch_run("epoch-legacy")
    erp_run = repository.get_erp_run("erp-legacy")

    assert epoch_run is not None
    assert epoch_run.warnings == ["some events were skipped"]
    assert epoch_run.diagnostics == {}
    assert erp_run is not None
    assert erp_run.warnings == ["plot fallback"]
    assert erp_run.diagnostics == {}


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
