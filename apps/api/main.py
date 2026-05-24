from pathlib import Path
import sys
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


REPO_ROOT = Path(__file__).resolve().parents[2]
for package_src in ("packages/eeg-core/src", "packages/eeg-io/src"):
    sys.path.insert(0, str(REPO_ROOT / package_src))

from eeg_core.domain import (  # noqa: E402
    Dataset as IngestionDataset,
    DatasetStatus,
    EventColumnMapping,
    Experiment,
    Participant,
    Project,
)
from eeg_io.datasets import find_eeg_file_by_id, list_eeg_files  # noqa: E402
from eeg_io.registry import JsonRegistryRepository  # noqa: E402
from eeg_io.readers import EegMetadataReadError, read_eeg_metadata  # noqa: E402


SAMPLE_DATASET_DIR = REPO_ROOT / "data" / "raw" / "samples"
UPLOADS_DIR = REPO_ROOT / "data" / "raw" / "uploads"
registry_repository = JsonRegistryRepository(UPLOADS_DIR)


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


class EventColumnMappingPayload(BaseModel):
    onset_seconds: str | None = None
    duration_seconds: str | None = None
    trial_type: str | None = None
    stimulus: str | None = None
    response: str | None = None
    correct: str | None = None
    reaction_time_seconds: str | None = None


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


app = FastAPI(title="NeuroWeave API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"
