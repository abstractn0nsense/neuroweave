from pathlib import Path
from multiprocessing import get_context
from queue import Empty, Queue
from threading import Lock, Thread
from dataclasses import replace
from datetime import UTC, datetime
from contextlib import asynccontextmanager
import hashlib
import json
import os
import shutil
import sys
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


REPO_ROOT = Path(__file__).resolve().parents[2]
for package_src in (
    "packages/eeg-core/src",
    "packages/eeg-io/src",
    "packages/eeg-processing/src",
):
    sys.path.insert(0, str(REPO_ROOT / package_src))

from eeg_core.domain import (  # noqa: E402
    Dataset as IngestionDataset,
    DatasetStatus,
    EventColumnMapping,
    EventLog,
    Experiment,
    Participant,
    PreprocessingConfig,
    PreprocessingRun,
    PreprocessingRunStatus,
    Project,
    Recording,
    UploadedFile as IngestionUploadedFile,
    UploadedFileKind,
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
    validate_ingestion_dataset,
)
from eeg_processing import PreprocessingError, run_preprocessing_job  # noqa: E402
from eeg_io.datasets import find_eeg_file_by_id, list_eeg_files  # noqa: E402
from eeg_io.event_logs import (  # noqa: E402
    EventLogNormalizationError,
    EventLogPreviewError,
    normalize_event_log,
    preview_event_log,
)
from eeg_io.registry import JsonRegistryRepository, JsonRunRepository  # noqa: E402
from eeg_io.readers import EegMetadataReadError, read_eeg_metadata  # noqa: E402


def _path_from_env(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    if not value:
        return default
    return Path(value).expanduser().resolve()


SAMPLE_DATASET_DIR = _path_from_env(
    "NEUROWEAVE_SAMPLE_DATASET_DIR",
    REPO_ROOT / "data" / "raw" / "samples",
)
UPLOADS_DIR = _path_from_env(
    "NEUROWEAVE_UPLOADS_DIR",
    REPO_ROOT / "data" / "raw" / "uploads",
)
RUNS_DIR = _path_from_env("NEUROWEAVE_RUNS_DIR", REPO_ROOT / "data" / "runs")
PROCESSED_DIR = _path_from_env(
    "NEUROWEAVE_PROCESSED_DIR",
    REPO_ROOT / "data" / "processed",
)
registry_repository = JsonRegistryRepository(UPLOADS_DIR)
run_repository = JsonRunRepository(RUNS_DIR)


class LocalPreprocessingWorker:
    def __init__(self) -> None:
        self._queue: Queue[str] = Queue()
        self._queued_run_ids: set[str] = set()
        self._lock = Lock()
        self._thread: Thread | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = Thread(
                target=self._run_loop,
                name="neuroweave-preprocessing-worker",
                daemon=True,
            )
            self._thread.start()

    def enqueue(self, run_id: str) -> None:
        self.start()
        with self._lock:
            if run_id in self._queued_run_ids:
                return
            self._queued_run_ids.add(run_id)
            self._queue.put(run_id)

    def recover(self) -> None:
        for run in run_repository.list_preprocessing_runs():
            if run.status in {
                PreprocessingRunStatus.PENDING,
                PreprocessingRunStatus.RUNNING,
            }:
                self.enqueue(run.run_id)

    def _run_loop(self) -> None:
        while True:
            run_id = self._queue.get()
            try:
                _execute_preprocessing_run(run_id)
            finally:
                with self._lock:
                    self._queued_run_ids.discard(run_id)
                self._queue.task_done()


preprocessing_worker = LocalPreprocessingWorker()


class HealthResponse(BaseModel):
    status: str
    service: str


class SampleDataset(BaseModel):
    id: str
    filename: str
    format: str


class SampleDatasetsResponse(BaseModel):
    samples: list[SampleDataset]


class DatasetMetadata(BaseModel):
    id: str
    format: str
    channels: int
    sampling_rate: float
    duration_seconds: float
    channel_names: list[str]


class CreateDatasetRequest(BaseModel):
    dataset_id: str | None = None
    project_id: str
    experiment_id: str
    participant_id: str | None = None
    participant_label: str
    participant_group: str | None = None
    session_id: str | None = None
    session_label: str
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class DatasetResponse(BaseModel):
    dataset_id: str
    project_id: str
    experiment_id: str
    participant_id: str
    session_id: str
    status: str
    recording_id: str | None
    event_log_id: str | None
    metadata: dict[str, str | int | float | bool | None]


class DatasetsResponse(BaseModel):
    datasets: list[DatasetResponse]


class UploadedFileResponse(BaseModel):
    file_id: str
    dataset_id: str
    kind: str
    original_filename: str
    stored_path: str
    content_type: str | None
    size_bytes: int | None
    checksum_sha256: str | None


class RecordingResponse(BaseModel):
    recording_id: str
    dataset_id: str
    file_id: str
    metadata: DatasetMetadata


class EegUploadResponse(BaseModel):
    dataset: DatasetResponse
    uploaded_file: UploadedFileResponse
    recording: RecordingResponse


class EventLogPreviewResponse(BaseModel):
    columns: list[str]
    delimiter: str
    preview_rows: list[dict[str, str | None]]
    row_count: int


class EventUploadResponse(BaseModel):
    dataset: DatasetResponse
    uploaded_file: UploadedFileResponse
    preview: EventLogPreviewResponse


class EventColumnMappingPayload(BaseModel):
    onset_seconds: str | None = None
    duration_seconds: str | None = None
    trial_type: str | None = None
    stimulus: str | None = None
    response: str | None = None
    correct: str | None = None
    reaction_time_seconds: str | None = None


class NormalizedEventResponse(BaseModel):
    onset_seconds: float
    source_row: int
    duration_seconds: float | None
    trial_type: str | None
    stimulus: str | None
    response: str | None
    correct: bool | None
    reaction_time_seconds: float | None


class EventLogResponse(BaseModel):
    event_log_id: str
    dataset_id: str
    file_id: str
    mapping: EventColumnMappingPayload
    row_count: int
    events: list[NormalizedEventResponse]


class ValidationIssueResponse(BaseModel):
    severity: str
    code: str
    message: str
    field: str | None


class ValidationReportResponse(BaseModel):
    dataset_id: str
    status: str
    valid: bool
    errors: list[ValidationIssueResponse]
    warnings: list[ValidationIssueResponse]
    issues: list[ValidationIssueResponse]


class EventMappingRequest(BaseModel):
    mapping: EventColumnMappingPayload | None = None


class PreprocessingConfigPayload(BaseModel):
    high_pass_hz: float | None = Field(default=None, ge=0)
    low_pass_hz: float | None = Field(default=None, gt=0)
    notch_hz: float | None = Field(default=None, gt=0)
    resample_hz: float | None = Field(default=None, gt=0)
    reference: str | None = None


class PreprocessingRunResponse(BaseModel):
    run_id: str
    dataset_id: str
    config: PreprocessingConfigPayload
    status: str
    started_at_utc: str | None
    finished_at_utc: str | None
    cancel_requested_at_utc: str | None
    output_path: str | None
    output_metadata: dict[str, str | int | float | bool | None]
    warnings: list[str]
    errors: list[str]


class PreprocessingRunsResponse(BaseModel):
    runs: list[PreprocessingRunResponse]


class CreateProjectRequest(BaseModel):
    project_id: str | None = None
    name: str
    description: str | None = None
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ProjectResponse(BaseModel):
    project_id: str
    name: str
    description: str | None
    metadata: dict[str, str | int | float | bool | None]


class ProjectsResponse(BaseModel):
    projects: list[ProjectResponse]


class CreateExperimentRequest(BaseModel):
    experiment_id: str | None = None
    name: str
    task_name: str | None = None
    default_event_mapping: EventColumnMappingPayload = Field(
        default_factory=EventColumnMappingPayload
    )
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ExperimentResponse(BaseModel):
    experiment_id: str
    project_id: str
    name: str
    task_name: str | None
    default_event_mapping: EventColumnMappingPayload
    metadata: dict[str, str | int | float | bool | None]


class ExperimentsResponse(BaseModel):
    experiments: list[ExperimentResponse]


@asynccontextmanager
async def lifespan(app: FastAPI):
    preprocessing_worker.start()
    preprocessing_worker.recover()
    yield


app = FastAPI(title="NeuroWeave API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="neuroweave-api")


@app.post(
    "/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_project(request: CreateProjectRequest) -> ProjectResponse:
    project = Project(
        project_id=request.project_id or _new_id("project"),
        name=request.name,
        description=request.description,
        metadata=request.metadata,
    )
    registry_repository.save_project(project)
    return _project_response(project)


@app.get("/projects", response_model=ProjectsResponse)
def list_projects() -> ProjectsResponse:
    return ProjectsResponse(
        projects=[
            _project_response(project)
            for project in registry_repository.list_projects()
        ]
    )


@app.post(
    "/projects/{project_id}/experiments",
    response_model=ExperimentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_experiment(
    project_id: str,
    request: CreateExperimentRequest,
) -> ExperimentResponse:
    if registry_repository.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    experiment = Experiment(
        experiment_id=request.experiment_id or _new_id("experiment"),
        project_id=project_id,
        name=request.name,
        task_name=request.task_name,
        default_event_mapping=EventColumnMapping(
            **request.default_event_mapping.model_dump()
        ),
        metadata=request.metadata,
    )
    registry_repository.save_experiment(experiment)
    return _experiment_response(experiment)


@app.get(
    "/projects/{project_id}/experiments",
    response_model=ExperimentsResponse,
)
def list_experiments(project_id: str) -> ExperimentsResponse:
    if registry_repository.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return ExperimentsResponse(
        experiments=[
            _experiment_response(experiment)
            for experiment in registry_repository.list_experiments(
                project_id=project_id
            )
        ]
    )


@app.post(
    "/datasets",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_dataset(request: CreateDatasetRequest) -> DatasetResponse:
    project = registry_repository.get_project(request.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    experiment = registry_repository.get_experiment(request.experiment_id)
    if experiment is None or experiment.project_id != request.project_id:
        raise HTTPException(status_code=404, detail="Experiment not found")

    participant_id = request.participant_id or _new_id("participant")
    participant = Participant(
        participant_id=participant_id,
        project_id=request.project_id,
        label=request.participant_label,
        group=request.participant_group,
    )
    registry_repository.save_participant(participant)

    dataset = IngestionDataset(
        dataset_id=request.dataset_id or _new_id("dataset"),
        project_id=request.project_id,
        experiment_id=request.experiment_id,
        participant_id=participant_id,
        session_id=request.session_id or _new_id("session"),
        status=DatasetStatus.NEEDS_FILES,
        metadata={
            **request.metadata,
            "participant_label": request.participant_label,
            "session_label": request.session_label,
        },
    )
    registry_repository.save_dataset(dataset)
    return _dataset_response(dataset)


@app.get("/datasets", response_model=DatasetsResponse)
def list_datasets(project_id: str | None = None) -> DatasetsResponse:
    return DatasetsResponse(
        datasets=[
            _dataset_response(dataset)
            for dataset in registry_repository.list_datasets(project_id=project_id)
        ]
    )


@app.get("/datasets/samples", response_model=SampleDatasetsResponse)
def list_sample_datasets() -> SampleDatasetsResponse:
    samples = [
        SampleDataset(
            id=eeg_file.dataset_id,
            filename=eeg_file.filename,
            format=eeg_file.file_format,
        )
        for eeg_file in list_eeg_files(SAMPLE_DATASET_DIR)
    ]
    return SampleDatasetsResponse(samples=samples)


@app.get("/datasets/samples/{dataset_id}/metadata", response_model=DatasetMetadata)
def get_sample_dataset_metadata(dataset_id: str) -> DatasetMetadata:
    eeg_file = find_eeg_file_by_id(SAMPLE_DATASET_DIR, dataset_id)
    if eeg_file is None:
        raise HTTPException(status_code=404, detail="Sample dataset not found")

    try:
        metadata = read_eeg_metadata(eeg_file.path, dataset_id=eeg_file.dataset_id)
    except EegMetadataReadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return DatasetMetadata(
        id=metadata.dataset_id,
        format=metadata.file_format,
        channels=metadata.channel_count,
        sampling_rate=metadata.sampling_rate_hz,
        duration_seconds=metadata.duration_seconds,
        channel_names=metadata.channel_names,
    )


@app.post(
    "/datasets/{dataset_id}/files/eeg",
    response_model=EegUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_dataset_eeg_file(
    dataset_id: str,
    file: UploadFile = File(...),
) -> EegUploadResponse:
    dataset = registry_repository.get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    stored_path = _store_upload_file(
        file=file,
        destination_directory=registry_repository.eeg_directory(dataset_id),
    )

    try:
        metadata = read_eeg_metadata(stored_path, dataset_id=dataset_id)
    except EegMetadataReadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    uploaded_file = IngestionUploadedFile(
        file_id=_new_id("file"),
        dataset_id=dataset_id,
        kind=UploadedFileKind.EEG,
        original_filename=file.filename or stored_path.name,
        stored_path=str(stored_path),
        content_type=file.content_type,
        size_bytes=stored_path.stat().st_size,
        checksum_sha256=_sha256_file(stored_path),
    )
    registry_repository.save_uploaded_file(uploaded_file)

    recording = Recording(
        recording_id=_new_id("recording"),
        dataset_id=dataset_id,
        file_id=uploaded_file.file_id,
        metadata=metadata,
    )
    registry_repository.save_recording(recording)

    updated_dataset = replace(
        dataset,
        status=DatasetStatus.NEEDS_MAPPING,
        recording_id=recording.recording_id,
    )
    registry_repository.update_dataset(updated_dataset)

    return EegUploadResponse(
        dataset=_dataset_response(updated_dataset),
        uploaded_file=_uploaded_file_response(uploaded_file),
        recording=_recording_response(recording),
    )


@app.post(
    "/datasets/{dataset_id}/files/events",
    response_model=EventUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_dataset_events_file(
    dataset_id: str,
    file: UploadFile = File(...),
) -> EventUploadResponse:
    dataset = registry_repository.get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    stored_path = _store_upload_file(
        file=file,
        destination_directory=registry_repository.events_directory(dataset_id),
    )

    try:
        preview = preview_event_log(stored_path)
    except EventLogPreviewError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    uploaded_file = IngestionUploadedFile(
        file_id=_new_id("file"),
        dataset_id=dataset_id,
        kind=UploadedFileKind.EVENTS,
        original_filename=file.filename or stored_path.name,
        stored_path=str(stored_path),
        content_type=file.content_type,
        size_bytes=stored_path.stat().st_size,
        checksum_sha256=_sha256_file(stored_path),
    )
    registry_repository.save_uploaded_file(uploaded_file)
    registry_repository.save_events_preview(dataset_id, preview)

    updated_dataset = replace(
        dataset,
        status=DatasetStatus.NEEDS_MAPPING,
        event_log_id=uploaded_file.file_id,
    )
    registry_repository.update_dataset(updated_dataset)

    return EventUploadResponse(
        dataset=_dataset_response(updated_dataset),
        uploaded_file=_uploaded_file_response(uploaded_file),
        preview=EventLogPreviewResponse(**preview),
    )


@app.post(
    "/datasets/{dataset_id}/events/mapping",
    response_model=EventLogResponse,
)
def map_dataset_events(
    dataset_id: str,
    request: EventMappingRequest,
) -> EventLogResponse:
    dataset = registry_repository.get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if not dataset.event_log_id:
        raise HTTPException(status_code=404, detail="Event file not found")

    uploaded_file = _find_uploaded_file(dataset_id, dataset.event_log_id)
    if uploaded_file is None or uploaded_file.kind != UploadedFileKind.EVENTS:
        raise HTTPException(status_code=404, detail="Event file not found")

    mapping = _resolve_event_mapping(dataset, request.mapping)
    try:
        event_log = normalize_event_log(
            dataset_id=dataset_id,
            event_log_id=dataset.event_log_id,
            file_id=uploaded_file.file_id,
            path=Path(uploaded_file.stored_path),
            mapping=mapping,
        )
    except (EventLogPreviewError, EventLogNormalizationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    registry_repository.save_event_log(event_log)
    return _event_log_response(event_log)


@app.get("/datasets/{dataset_id}/events", response_model=EventLogResponse)
def get_dataset_events(dataset_id: str) -> EventLogResponse:
    if registry_repository.get_dataset(dataset_id) is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    event_log = registry_repository.get_event_log(dataset_id)
    if event_log is None:
        raise HTTPException(status_code=404, detail="Event log not found")

    return _event_log_response(event_log)


@app.get(
    "/datasets/{dataset_id}/validation",
    response_model=ValidationReportResponse,
)
def get_dataset_validation(dataset_id: str) -> ValidationReportResponse:
    dataset = registry_repository.get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    report = _validate_dataset(dataset)
    updated_dataset = replace(dataset, status=report.status)
    registry_repository.update_dataset(updated_dataset)
    return _validation_report_response(report)


@app.post(
    "/datasets/{dataset_id}/preprocessing-runs",
    response_model=PreprocessingRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_preprocessing_run(
    dataset_id: str,
    config_payload: PreprocessingConfigPayload,
) -> PreprocessingRunResponse:
    dataset = registry_repository.get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    report = _validate_dataset(dataset)
    if not report.valid:
        updated_dataset = replace(dataset, status=report.status)
        registry_repository.update_dataset(updated_dataset)
        raise HTTPException(
            status_code=409,
            detail="Dataset must be valid before preprocessing.",
        )

    recording = registry_repository.get_recording(dataset_id)
    if recording is None:
        raise HTTPException(status_code=409, detail="Recording not found")

    uploaded_file = _find_uploaded_file(dataset_id, recording.file_id)
    if uploaded_file is None or uploaded_file.kind != UploadedFileKind.EEG:
        raise HTTPException(status_code=409, detail="EEG file not found")

    config = PreprocessingConfig(**config_payload.model_dump())
    config_errors = _validate_preprocessing_config(config, recording)
    if config_errors:
        raise HTTPException(status_code=422, detail=config_errors)

    run_id = _new_id("preprocess")
    output_path = PROCESSED_DIR / dataset_id / run_id / "raw_preprocessed.fif"

    run = PreprocessingRun(
        run_id=run_id,
        dataset_id=dataset_id,
        config=config,
        status=PreprocessingRunStatus.PENDING,
        output_path=str(output_path),
        output_metadata=_preprocessing_input_provenance(
            uploaded_file=uploaded_file,
            recording=recording,
        ),
    )
    run_repository.save_preprocessing_run(run)
    preprocessing_worker.enqueue(run_id)
    return _preprocessing_run_response(run)


@app.get(
    "/preprocessing-runs/{run_id}",
    response_model=PreprocessingRunResponse,
)
def get_preprocessing_run(run_id: str) -> PreprocessingRunResponse:
    run = run_repository.get_preprocessing_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Preprocessing run not found")

    return _preprocessing_run_response(run)


@app.post(
    "/preprocessing-runs/{run_id}/cancel",
    response_model=PreprocessingRunResponse,
)
def cancel_preprocessing_run(run_id: str) -> PreprocessingRunResponse:
    run = run_repository.get_preprocessing_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Preprocessing run not found")

    if run.status == PreprocessingRunStatus.PENDING:
        cancelled_at = _utc_now_iso()
        cancelled_run = replace(
            run,
            status=PreprocessingRunStatus.CANCELLED,
            finished_at_utc=cancelled_at,
            cancel_requested_at_utc=run.cancel_requested_at_utc or cancelled_at,
            warnings=[*run.warnings, "Run cancelled before preprocessing started."],
        )
        run_repository.save_preprocessing_run(cancelled_run)
        return _preprocessing_run_response(cancelled_run)

    if run.status == PreprocessingRunStatus.RUNNING:
        cancelling_run = replace(
            run,
            status=PreprocessingRunStatus.CANCELLING,
            cancel_requested_at_utc=run.cancel_requested_at_utc or _utc_now_iso(),
            warnings=[
                *run.warnings,
                "Cancellation requested; preprocessing will stop at the next checkpoint.",
            ],
        )
        run_repository.save_preprocessing_run(cancelling_run)
        return _preprocessing_run_response(cancelling_run)

    return _preprocessing_run_response(run)


@app.get(
    "/datasets/{dataset_id}/preprocessing-runs",
    response_model=PreprocessingRunsResponse,
)
def list_dataset_preprocessing_runs(dataset_id: str) -> PreprocessingRunsResponse:
    if registry_repository.get_dataset(dataset_id) is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return PreprocessingRunsResponse(
        runs=[
            _preprocessing_run_response(run)
            for run in run_repository.list_preprocessing_runs(dataset_id=dataset_id)
        ]
    )


@app.get("/datasets/{dataset_id}", response_model=DatasetResponse)
def get_dataset(dataset_id: str) -> DatasetResponse:
    dataset = registry_repository.get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return _dataset_response(dataset)


def _project_response(project: Project) -> ProjectResponse:
    return ProjectResponse(
        project_id=project.project_id,
        name=project.name,
        description=project.description,
        metadata=project.metadata,
    )


def _experiment_response(experiment: Experiment) -> ExperimentResponse:
    return ExperimentResponse(
        experiment_id=experiment.experiment_id,
        project_id=experiment.project_id,
        name=experiment.name,
        task_name=experiment.task_name,
        default_event_mapping=EventColumnMappingPayload(
            **experiment.default_event_mapping.__dict__
        ),
        metadata=experiment.metadata,
    )


def _dataset_response(dataset: IngestionDataset) -> DatasetResponse:
    return DatasetResponse(
        dataset_id=dataset.dataset_id,
        project_id=dataset.project_id,
        experiment_id=dataset.experiment_id,
        participant_id=dataset.participant_id,
        session_id=dataset.session_id,
        status=dataset.status.value,
        recording_id=dataset.recording_id,
        event_log_id=dataset.event_log_id,
        metadata=dataset.metadata,
    )


def _uploaded_file_response(uploaded_file: IngestionUploadedFile) -> UploadedFileResponse:
    return UploadedFileResponse(
        file_id=uploaded_file.file_id,
        dataset_id=uploaded_file.dataset_id,
        kind=uploaded_file.kind.value,
        original_filename=uploaded_file.original_filename,
        stored_path=uploaded_file.stored_path,
        content_type=uploaded_file.content_type,
        size_bytes=uploaded_file.size_bytes,
        checksum_sha256=uploaded_file.checksum_sha256,
    )


def _recording_response(recording: Recording) -> RecordingResponse:
    return RecordingResponse(
        recording_id=recording.recording_id,
        dataset_id=recording.dataset_id,
        file_id=recording.file_id,
        metadata=DatasetMetadata(
            id=recording.metadata.dataset_id,
            format=recording.metadata.file_format,
            channels=recording.metadata.channel_count,
            sampling_rate=recording.metadata.sampling_rate_hz,
            duration_seconds=recording.metadata.duration_seconds,
            channel_names=recording.metadata.channel_names,
        ),
    )


def _event_log_response(event_log: EventLog) -> EventLogResponse:
    return EventLogResponse(
        event_log_id=event_log.event_log_id,
        dataset_id=event_log.dataset_id,
        file_id=event_log.file_id,
        mapping=EventColumnMappingPayload(**event_log.mapping.__dict__),
        row_count=event_log.row_count,
        events=[
            NormalizedEventResponse(
                onset_seconds=event.onset_seconds,
                source_row=event.source_row,
                duration_seconds=event.duration_seconds,
                trial_type=event.trial_type,
                stimulus=event.stimulus,
                response=event.response,
                correct=event.correct,
                reaction_time_seconds=event.reaction_time_seconds,
            )
            for event in event_log.events
        ],
    )


def _validation_report_response(report: ValidationReport) -> ValidationReportResponse:
    issues = [_validation_issue_response(issue) for issue in report.issues]
    return ValidationReportResponse(
        dataset_id=report.dataset_id,
        status=report.status.value,
        valid=report.valid,
        errors=[
            issue
            for issue in issues
            if issue.severity == ValidationSeverity.ERROR.value
        ],
        warnings=[
            issue
            for issue in issues
            if issue.severity == ValidationSeverity.WARNING.value
        ],
        issues=issues,
    )


def _preprocessing_run_response(run: PreprocessingRun) -> PreprocessingRunResponse:
    return PreprocessingRunResponse(
        run_id=run.run_id,
        dataset_id=run.dataset_id,
        config=PreprocessingConfigPayload(**run.config.__dict__),
        status=run.status.value,
        started_at_utc=run.started_at_utc,
        finished_at_utc=run.finished_at_utc,
        cancel_requested_at_utc=run.cancel_requested_at_utc,
        output_path=run.output_path,
        output_metadata=run.output_metadata,
        warnings=run.warnings,
        errors=run.errors,
    )


def _preprocessing_input_provenance(
    uploaded_file: IngestionUploadedFile,
    recording: Recording,
) -> dict[str, str | int | float | bool | None]:
    return {
        "input_file_id": uploaded_file.file_id,
        "input_original_filename": uploaded_file.original_filename,
        "input_path": uploaded_file.stored_path,
        "input_size_bytes": uploaded_file.size_bytes,
        "input_checksum_sha256": uploaded_file.checksum_sha256,
        "input_file_format": recording.metadata.file_format,
        "input_channel_count": recording.metadata.channel_count,
        "input_sampling_rate_hz": recording.metadata.sampling_rate_hz,
        "input_duration_seconds": recording.metadata.duration_seconds,
        "input_channel_names": ",".join(recording.metadata.channel_names),
    }


def _preprocessing_completed_provenance(
    run: PreprocessingRun,
    output_path: Path,
    processing_metadata: dict,
) -> dict[str, str | int | float | bool | None]:
    diagnostics_metadata = _write_preprocessing_diagnostics(
        output_directory=output_path.parent,
        processing_metadata=processing_metadata,
    )
    return {
        **run.output_metadata,
        "output_path": str(output_path),
        "output_size_bytes": output_path.stat().st_size,
        "output_checksum_sha256": _sha256_file(output_path),
        "output_file_format": processing_metadata["file_format"],
        "output_channel_count": processing_metadata["channel_count"],
        "output_sampling_rate_hz": processing_metadata["sampling_rate_hz"],
        "output_duration_seconds": processing_metadata["duration_seconds"],
        "mne_version": processing_metadata["mne_version"],
        **diagnostics_metadata,
    }


def _write_preprocessing_diagnostics(
    output_directory: Path,
    processing_metadata: dict,
) -> dict[str, str | int | float | bool | None]:
    diagnostics = processing_metadata.get("diagnostics")
    if not isinstance(diagnostics, dict):
        return {
            "diagnostics_available": False,
            "diagnostics_file_count": 0,
        }

    output_directory.mkdir(parents=True, exist_ok=True)
    files = {
        "preprocessing_summary": output_directory / "preprocessing_summary.json",
        "filter_report": output_directory / "filter_report.json",
        "artifact_summary": output_directory / "artifact_summary.json",
    }
    written_paths: dict[str, Path] = {}
    for key, path in files.items():
        payload = diagnostics.get(key)
        if isinstance(payload, dict):
            _write_json_file(path, payload)
            written_paths[key] = path

    artifact_summary = diagnostics.get("artifact_summary")
    output_artifacts = (
        artifact_summary.get("output", {})
        if isinstance(artifact_summary, dict)
        else {}
    )
    return {
        "diagnostics_available": bool(written_paths),
        "diagnostics_file_count": len(written_paths),
        "diagnostics_directory": str(output_directory),
        "preprocessing_summary_path": str(written_paths.get("preprocessing_summary"))
        if "preprocessing_summary" in written_paths
        else None,
        "filter_report_path": str(written_paths.get("filter_report"))
        if "filter_report" in written_paths
        else None,
        "artifact_summary_path": str(written_paths.get("artifact_summary"))
        if "artifact_summary" in written_paths
        else None,
        "artifact_bad_channel_count": output_artifacts.get("bad_channel_count")
        if isinstance(output_artifacts, dict)
        else None,
        "artifact_annotation_count": output_artifacts.get("annotation_count")
        if isinstance(output_artifacts, dict)
        else None,
    }


def _write_json_file(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _validation_issue_response(issue: ValidationIssue) -> ValidationIssueResponse:
    return ValidationIssueResponse(
        severity=issue.severity.value,
        code=issue.code,
        message=issue.message,
        field=issue.field,
    )


def _validate_dataset(dataset: IngestionDataset) -> ValidationReport:
    recording = registry_repository.get_recording(dataset.dataset_id)
    event_log = registry_repository.get_event_log(dataset.dataset_id)
    return validate_ingestion_dataset(
        dataset=dataset,
        recording=recording,
        event_log=event_log,
    )


def _execute_preprocessing_run(run_id: str) -> None:
    run = run_repository.get_preprocessing_run(run_id)
    if run is None:
        return
    if run.status == PreprocessingRunStatus.CANCELLED:
        return
    if run.status in {
        PreprocessingRunStatus.COMPLETED,
        PreprocessingRunStatus.FAILED,
    }:
        return
    if run.status == PreprocessingRunStatus.CANCELLING:
        cancelled_run = replace(
            run,
            status=PreprocessingRunStatus.CANCELLED,
            finished_at_utc=_utc_now_iso(),
            cancel_requested_at_utc=run.cancel_requested_at_utc,
        )
        run_repository.save_preprocessing_run(cancelled_run)
        return

    input_path = run.output_metadata.get("input_path")
    output_path = run.output_path
    if not isinstance(input_path, str) or not output_path:
        failed_run = replace(
            run,
            status=PreprocessingRunStatus.FAILED,
            finished_at_utc=_utc_now_iso(),
            errors=["Preprocessing run is missing input or output paths."],
        )
        run_repository.save_preprocessing_run(failed_run)
        return

    running_run = replace(
        run,
        status=PreprocessingRunStatus.RUNNING,
        started_at_utc=_utc_now_iso(),
    )
    run_repository.save_preprocessing_run(running_run)

    try:
        metadata = _run_preprocessing_subprocess(
            run_id=run_id,
            input_path=input_path,
            output_path=output_path,
            config=run.config,
        )
        output_file_path = Path(output_path)
        completed_run = replace(
            running_run,
            status=PreprocessingRunStatus.COMPLETED,
            finished_at_utc=_utc_now_iso(),
            output_metadata=_preprocessing_completed_provenance(
                run=running_run,
                output_path=output_file_path,
                processing_metadata=metadata,
            ),
            warnings=[str(warning) for warning in metadata.get("warnings", [])],
        )
        current_run = run_repository.get_preprocessing_run(run_id)
        if current_run and current_run.status == PreprocessingRunStatus.CANCELLING:
            cancelled_run = replace(
                completed_run,
                status=PreprocessingRunStatus.CANCELLED,
                finished_at_utc=_utc_now_iso(),
                cancel_requested_at_utc=current_run.cancel_requested_at_utc,
                warnings=_dedupe_strings(
                    [
                        *current_run.warnings,
                        *completed_run.warnings,
                        "Run cancelled after preprocessing completed; output was retained.",
                    ]
                ),
            )
            run_repository.save_preprocessing_run(cancelled_run)
        else:
            run_repository.save_preprocessing_run(completed_run)
    except PreprocessingError as exc:
        current_run = run_repository.get_preprocessing_run(run_id)
        current_warnings = current_run.warnings if current_run else []
        next_status = (
            PreprocessingRunStatus.CANCELLED
            if current_run and current_run.status == PreprocessingRunStatus.CANCELLING
            else PreprocessingRunStatus.FAILED
        )
        failed_run = replace(
            running_run,
            status=next_status,
            finished_at_utc=_utc_now_iso(),
            cancel_requested_at_utc=(
                current_run.cancel_requested_at_utc if current_run else None
            ),
            warnings=_dedupe_strings([*current_warnings, *exc.processing_warnings]),
            errors=[str(exc)],
        )
        run_repository.save_preprocessing_run(failed_run)


def _run_preprocessing_subprocess(
    run_id: str,
    input_path: str,
    output_path: str,
    config: PreprocessingConfig,
) -> dict:
    context = get_context("spawn")
    result_queue = context.Queue()
    process = context.Process(
        target=run_preprocessing_job,
        args=(input_path, output_path, config, result_queue),
    )
    process.start()

    while process.is_alive():
        process.join(timeout=0.1)
        if _is_cancellation_requested(run_id):
            process.terminate()
            process.join(timeout=5)
            if process.is_alive():
                process.kill()
                process.join()
            raise PreprocessingError(
                "Preprocessing cancelled.",
                processing_warnings=[
                    "Cancellation terminated preprocessing subprocess."
                ],
            )

    try:
        result = result_queue.get_nowait()
    except Empty as exc:
        if process.exitcode == 0:
            raise PreprocessingError(
                "Preprocessing subprocess exited without a result."
            ) from exc
        raise PreprocessingError(
            f"Preprocessing subprocess exited with code {process.exitcode}."
        ) from exc

    if result.get("status") == "completed":
        metadata = result.get("metadata")
        if isinstance(metadata, dict):
            return metadata
        raise PreprocessingError("Preprocessing subprocess returned invalid metadata.")

    raise PreprocessingError(
        str(result.get("error") or "Preprocessing subprocess failed."),
        processing_warnings=[
            str(warning) for warning in result.get("warnings", [])
        ],
    )


def _is_cancellation_requested(run_id: str) -> bool:
    run = run_repository.get_preprocessing_run(run_id)
    return run is not None and run.status in {
        PreprocessingRunStatus.CANCELLING,
        PreprocessingRunStatus.CANCELLED,
    }


def _validate_preprocessing_config(
    config: PreprocessingConfig,
    recording: Recording,
) -> list[str]:
    errors: list[str] = []
    sampling_rate = recording.metadata.sampling_rate_hz
    nyquist = sampling_rate / 2

    if (
        config.high_pass_hz is not None
        and config.low_pass_hz is not None
        and config.high_pass_hz >= config.low_pass_hz
    ):
        errors.append("high_pass_hz must be lower than low_pass_hz.")

    for field_name, value in (
        ("high_pass_hz", config.high_pass_hz),
        ("low_pass_hz", config.low_pass_hz),
        ("notch_hz", config.notch_hz),
    ):
        if value is not None and value >= nyquist:
            errors.append(
                f"{field_name} must be lower than the Nyquist frequency ({nyquist:g} Hz)."
            )

    if config.resample_hz is not None and config.resample_hz > sampling_rate:
        errors.append(
            f"resample_hz must not exceed the input sampling rate ({sampling_rate:g} Hz)."
        )

    if config.reference:
        reference = config.reference.strip().lower()
        if reference not in {"average", "avg", "none", "original"}:
            channel_names = set(recording.metadata.channel_names)
            requested_channels = [
                channel.strip()
                for channel in config.reference.split(",")
                if channel.strip()
            ]
            if not requested_channels:
                errors.append("reference must be average, none, or existing channel names.")
            else:
                missing_channels = [
                    channel
                    for channel in requested_channels
                    if channel not in channel_names
                ]
                if missing_channels:
                    errors.append(
                        "reference contains unknown channels: "
                        + ", ".join(missing_channels)
                    )

    return errors


def _find_uploaded_file(
    dataset_id: str,
    file_id: str,
) -> IngestionUploadedFile | None:
    for uploaded_file in registry_repository.list_uploaded_files(dataset_id):
        if uploaded_file.file_id == file_id:
            return uploaded_file
    return None


def _resolve_event_mapping(
    dataset: IngestionDataset,
    request_mapping: EventColumnMappingPayload | None,
) -> EventColumnMapping:
    if request_mapping is not None:
        return EventColumnMapping(**request_mapping.model_dump())

    experiment = registry_repository.get_experiment(dataset.experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return experiment.default_event_mapping


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def _store_upload_file(file: UploadFile, destination_directory: Path) -> Path:
    destination_directory.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename(file.filename or "uploaded_eeg")
    destination = _available_upload_path(destination_directory / filename)
    with destination.open("wb") as destination_file:
        shutil.copyfileobj(file.file, destination_file)
    return destination


def _safe_filename(filename: str) -> str:
    return Path(filename).name.replace("\x00", "") or "uploaded_eeg"


def _available_upload_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for index in range(1, 10_000):
        candidate = parent / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise HTTPException(status_code=409, detail="Could not allocate upload filename")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
