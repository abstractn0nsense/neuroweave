from dataclasses import dataclass
from pathlib import Path


SUPPORTED_EEG_FORMATS = {"fif", "edf", "bdf", "vhdr", "set"}


@dataclass(frozen=True)
class EegFile:
    dataset_id: str
    path: Path
    file_format: str

    @property
    def filename(self) -> str:
        return self.path.name


def list_eeg_files(directory: Path) -> list[EegFile]:
    directory.mkdir(parents=True, exist_ok=True)
    return [
        EegFile(
            dataset_id=dataset_id_from_path(path),
            path=path,
            file_format=file_format_from_path(path),
        )
        for path in sorted(directory.iterdir())
        if is_supported_eeg_file(path)
    ]


def find_eeg_file_by_id(directory: Path, dataset_id: str) -> EegFile | None:
    for eeg_file in list_eeg_files(directory):
        if eeg_file.dataset_id == dataset_id:
            return eeg_file
    return None


def is_supported_eeg_file(path: Path) -> bool:
    return path.is_file() and file_format_from_path(path) in SUPPORTED_EEG_FORMATS


def dataset_id_from_path(path: Path) -> str:
    if path.name.endswith(".fif.gz"):
        return path.name.removesuffix(".fif.gz")
    return path.stem


def file_format_from_path(path: Path) -> str:
    if path.name.endswith(".fif.gz"):
        return "fif"
    return path.suffix.lower().removeprefix(".")

