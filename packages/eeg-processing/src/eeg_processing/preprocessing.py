from pathlib import Path
from typing import Any, Callable
import warnings as python_warnings

from eeg_core.domain import PreprocessingConfig


class PreprocessingError(Exception):
    def __init__(self, message: str, processing_warnings: list[str] | None = None):
        super().__init__(message)
        self.processing_warnings = processing_warnings or []


CancelCheck = Callable[[], bool]


def preprocess_raw_eeg(
    input_path: Path,
    output_path: Path,
    config: PreprocessingConfig,
    should_cancel: CancelCheck | None = None,
) -> dict[str, Any]:
    manual_warnings: list[str] = []
    warning_records: list[python_warnings.WarningMessage] = []
    try:
        with python_warnings.catch_warnings(record=True) as warning_records:
            python_warnings.simplefilter("always")

            _check_cancelled(should_cancel, manual_warnings)
            raw = _read_raw(input_path)
            _check_cancelled(should_cancel, manual_warnings)
            input_sampling_rate = float(raw.info["sfreq"])
            input_duration = (
                raw.n_times / input_sampling_rate if input_sampling_rate else 0
            )

            if config.high_pass_hz is not None or config.low_pass_hz is not None:
                _check_cancelled(should_cancel, manual_warnings)
                raw.filter(
                    l_freq=config.high_pass_hz or None,
                    h_freq=config.low_pass_hz,
                    verbose=False,
                )
                _check_cancelled(should_cancel, manual_warnings)

            if config.notch_hz is not None:
                nyquist = float(raw.info["sfreq"]) / 2
                if config.notch_hz >= nyquist:
                    manual_warnings.append(
                        f"Skipped notch filter at {config.notch_hz:g} Hz because Nyquist is {nyquist:g} Hz."
                    )
                else:
                    _check_cancelled(should_cancel, manual_warnings)
                    raw.notch_filter(freqs=[config.notch_hz], verbose=False)
                    _check_cancelled(should_cancel, manual_warnings)

            if config.reference:
                reference = config.reference.strip().lower()
                if reference in {"average", "avg"}:
                    _check_cancelled(should_cancel, manual_warnings)
                    raw.set_eeg_reference("average", verbose=False)
                    _check_cancelled(should_cancel, manual_warnings)
                elif reference in {"none", "original"}:
                    manual_warnings.append("Reference unchanged.")
                else:
                    channels = [
                        channel.strip()
                        for channel in config.reference.split(",")
                        if channel.strip()
                    ]
                    if channels:
                        _check_cancelled(should_cancel, manual_warnings)
                        raw.set_eeg_reference(channels, verbose=False)
                        _check_cancelled(should_cancel, manual_warnings)

            if config.resample_hz is not None:
                _check_cancelled(should_cancel, manual_warnings)
                raw.resample(config.resample_hz, verbose=False)
                _check_cancelled(should_cancel, manual_warnings)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            _check_cancelled(should_cancel, manual_warnings)
            raw.save(output_path, overwrite=True, verbose=False)
            _check_cancelled(should_cancel, manual_warnings)
    except PreprocessingError as exc:
        raise PreprocessingError(
            str(exc),
            processing_warnings=_dedupe(
                manual_warnings
                + _format_warning_records(warning_records)
                + exc.processing_warnings
            ),
        ) from exc
    except Exception as exc:
        raise PreprocessingError(
            f"Preprocessing failed: {exc}",
            processing_warnings=_dedupe(
                manual_warnings + _format_warning_records(warning_records)
            ),
        ) from exc

    sampling_rate = float(raw.info["sfreq"])
    return {
        "channel_count": len(raw.ch_names),
        "sampling_rate_hz": sampling_rate,
        "duration_seconds": raw.n_times / sampling_rate if sampling_rate else 0,
        "file_format": "fif",
        "input_sampling_rate_hz": input_sampling_rate,
        "input_duration_seconds": input_duration,
        "mne_version": _mne_version(),
        "warnings": _dedupe(
            manual_warnings + _format_warning_records(warning_records)
        ),
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


def _mne_version() -> str:
    import mne

    return str(mne.__version__)


def _check_cancelled(
    should_cancel: CancelCheck | None,
    manual_warnings: list[str],
) -> None:
    if should_cancel and should_cancel():
        manual_warnings.append("Cancellation observed at preprocessing checkpoint.")
        raise PreprocessingError("Preprocessing cancelled.")


def _format_warning_records(
    warning_records: list[python_warnings.WarningMessage],
) -> list[str]:
    return [
        f"{warning.category.__name__}: {warning.message}"
        for warning in warning_records
    ]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped
