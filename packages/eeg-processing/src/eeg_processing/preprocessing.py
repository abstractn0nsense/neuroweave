from pathlib import Path
from typing import Any

from eeg_core.domain import PreprocessingConfig


class PreprocessingError(Exception):
    pass


def preprocess_raw_eeg(
    input_path: Path,
    output_path: Path,
    config: PreprocessingConfig,
) -> dict[str, Any]:
    raw = _read_raw(input_path)
    warnings: list[str] = []

    try:
        if config.high_pass_hz is not None or config.low_pass_hz is not None:
            raw.filter(
                l_freq=config.high_pass_hz,
                h_freq=config.low_pass_hz,
                verbose=False,
            )

        if config.notch_hz is not None:
            nyquist = float(raw.info["sfreq"]) / 2
            if config.notch_hz >= nyquist:
                warnings.append(
                    f"Skipped notch filter at {config.notch_hz:g} Hz because Nyquist is {nyquist:g} Hz."
                )
            else:
                raw.notch_filter(freqs=[config.notch_hz], verbose=False)

        if config.reference:
            reference = config.reference.strip().lower()
            if reference in {"average", "avg"}:
                raw.set_eeg_reference("average", verbose=False)
            elif reference in {"none", "original"}:
                warnings.append("Reference unchanged.")
            else:
                channels = [
                    channel.strip()
                    for channel in config.reference.split(",")
                    if channel.strip()
                ]
                if channels:
                    raw.set_eeg_reference(channels, verbose=False)

        if config.resample_hz is not None:
            raw.resample(config.resample_hz, verbose=False)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        raw.save(output_path, overwrite=True, verbose=False)
    except Exception as exc:
        raise PreprocessingError(f"Preprocessing failed: {exc}") from exc

    sampling_rate = float(raw.info["sfreq"])
    return {
        "channel_count": len(raw.ch_names),
        "sampling_rate_hz": sampling_rate,
        "duration_seconds": raw.n_times / sampling_rate if sampling_rate else 0,
        "file_format": "fif",
        "warnings": warnings,
    }


def _read_raw(path: Path):
    import mne

    readers = {
        ".fif": mne.io.read_raw_fif,
        ".edf": mne.io.read_raw_edf,
        ".bdf": mne.io.read_raw_bdf,
        ".vhdr": mne.io.read_raw_brainvision,
        ".set": mne.io.read_raw_eeglab,
    }
    reader = readers.get(path.suffix.lower())
    if reader is None:
        raise PreprocessingError(f"Unsupported EEG file format: {path.suffix}")

    try:
        return reader(path, preload=True, verbose=False)
    except Exception as exc:
        raise PreprocessingError(f"Could not read EEG data: {exc}") from exc
