from pathlib import Path
import sys

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


REPO_ROOT = Path(__file__).resolve().parents[2]
for package_src in ("packages/eeg-core/src", "packages/eeg-io/src"):
    sys.path.insert(0, str(REPO_ROOT / package_src))

from eeg_io.datasets import find_eeg_file_by_id, list_eeg_files  # noqa: E402
from eeg_io.readers import EegMetadataReadError, read_eeg_metadata  # noqa: E402


SAMPLE_DATASET_DIR = REPO_ROOT / "data" / "raw" / "samples"


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
