from pathlib import Path

from eeg_core.domain import RecordingMetadata
from eeg_io.datasets import dataset_id_from_path, file_format_from_path


class EegMetadataReadError(Exception):
    pass


def read_eeg_metadata(path: Path, dataset_id: str | None = None) -> RecordingMetadata:
    raw = _read_raw_eeg(path)
    sampling_rate = float(raw.info["sfreq"])
    samples = int(raw.n_times)

    return RecordingMetadata(
        dataset_id=dataset_id or dataset_id_from_path(path),
        file_format=file_format_from_path(path),
        channel_count=len(raw.ch_names),
        sampling_rate_hz=sampling_rate,
        duration_seconds=samples / sampling_rate if sampling_rate else 0,
        channel_names=list(raw.ch_names),
    )


def _read_raw_eeg(path: Path):
    import mne

    readers = {
        "fif": mne.io.read_raw_fif,
        "edf": mne.io.read_raw_edf,
        "bdf": mne.io.read_raw_bdf,
        "vhdr": mne.io.read_raw_brainvision,
        "set": mne.io.read_raw_eeglab,
    }
    file_format = file_format_from_path(path)
    reader = readers.get(file_format)
    if reader is None:
        raise EegMetadataReadError(f"Unsupported EEG file format: {file_format}")

    try:
        return reader(path, preload=False, verbose=False)
    except Exception as exc:
        raise EegMetadataReadError(f"Could not read EEG metadata: {exc}") from exc
