from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DATASET_DIR = REPO_ROOT / "data" / "raw" / "samples"
SUPPORTED_EEG_EXTENSIONS = {
    ".fif",
    ".edf",
    ".bdf",
    ".vhdr",
    ".set",
}


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
    SAMPLE_DATASET_DIR.mkdir(parents=True, exist_ok=True)
    samples = [
        SampleDataset(
            id=_dataset_id_from_path(path),
            filename=path.name,
            format=_dataset_format_from_path(path),
        )
        for path in sorted(SAMPLE_DATASET_DIR.iterdir())
        if _is_supported_eeg_file(path)
    ]
    return SampleDatasetsResponse(samples=samples)


@app.get("/datasets/samples/{dataset_id}/metadata", response_model=DatasetMetadata)
def get_sample_dataset_metadata(dataset_id: str) -> DatasetMetadata:
    path = _find_sample_dataset(dataset_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Sample dataset not found")

    raw = _read_raw_eeg(path)
    sampling_rate = float(raw.info["sfreq"])
    samples = int(raw.n_times)

    return DatasetMetadata(
        id=dataset_id,
        format=_dataset_format_from_path(path),
        channels=len(raw.ch_names),
        sampling_rate=sampling_rate,
        duration_seconds=samples / sampling_rate if sampling_rate else 0,
        channel_names=list(raw.ch_names),
    )


def _find_sample_dataset(dataset_id: str) -> Path | None:
    SAMPLE_DATASET_DIR.mkdir(parents=True, exist_ok=True)
    for path in SAMPLE_DATASET_DIR.iterdir():
        if _is_supported_eeg_file(path) and _dataset_id_from_path(path) == dataset_id:
            return path
    return None


def _is_supported_eeg_file(path: Path) -> bool:
    return path.is_file() and _dataset_format_from_path(path) in {
        extension.removeprefix(".") for extension in SUPPORTED_EEG_EXTENSIONS
    }


def _dataset_id_from_path(path: Path) -> str:
    if path.name.endswith(".fif.gz"):
        return path.name.removesuffix(".fif.gz")
    return path.stem


def _dataset_format_from_path(path: Path) -> str:
    if path.name.endswith(".fif.gz"):
        return "fif"
    return path.suffix.lower().removeprefix(".")


def _read_raw_eeg(path: Path):
    import mne

    readers = {
        "fif": mne.io.read_raw_fif,
        "edf": mne.io.read_raw_edf,
        "bdf": mne.io.read_raw_bdf,
        "vhdr": mne.io.read_raw_brainvision,
        "set": mne.io.read_raw_eeglab,
    }
    file_format = _dataset_format_from_path(path)
    reader = readers.get(file_format)
    if reader is None:
        raise HTTPException(status_code=415, detail="Unsupported EEG file format")

    try:
        return reader(path, preload=False, verbose=False)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not read EEG metadata: {exc}") from exc
