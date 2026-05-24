from dataclasses import dataclass
from pathlib import Path
from typing import Any
import re
import warnings as python_warnings

from eeg_core.domain import ErpConfig


class ErpError(Exception):
    def __init__(self, message: str, processing_warnings: list[str] | None = None):
        super().__init__(message)
        self.processing_warnings = processing_warnings or []


@dataclass(frozen=True)
class ErpConditionArtifact:
    condition: str
    safe_condition: str
    evoked_path: str
    nave: int
    channel_count: int
    time_min_seconds: float
    time_max_seconds: float
    sampling_rate_hz: float
    channel_time_summary: dict[str, Any]


def generate_erps_from_epochs(
    epochs_path: Path,
    output_directory: Path,
    config: ErpConfig,
) -> dict[str, Any]:
    warning_records: list[python_warnings.WarningMessage] = []
    try:
        with python_warnings.catch_warnings(record=True) as warning_records:
            python_warnings.simplefilter("always")

            import mne

            epochs = mne.read_epochs(epochs_path, preload=True, verbose=False)
            picks = config.picks if config.picks else None
            if picks is not None:
                epochs = epochs.copy().pick(picks)

            conditions = _selected_conditions(
                available_conditions=sorted(epochs.event_id),
                requested_conditions=config.conditions,
            )
            output_directory.mkdir(parents=True, exist_ok=True)
            artifacts: list[ErpConditionArtifact] = []

            for condition in conditions:
                condition_epochs = epochs[condition]
                if len(condition_epochs) == 0:
                    raise ErpError(f"Condition has no retained epochs: {condition}")

                evoked = condition_epochs.average(method=config.method)
                safe_condition = safe_condition_filename(condition)
                evoked_path = output_directory / f"evoked_{safe_condition}.fif"
                evoked.save(evoked_path, overwrite=True, verbose=False)
                artifacts.append(
                    ErpConditionArtifact(
                        condition=condition,
                        safe_condition=safe_condition,
                        evoked_path=str(evoked_path),
                        nave=int(evoked.nave),
                        channel_count=len(evoked.ch_names),
                        time_min_seconds=float(evoked.times[0]),
                        time_max_seconds=float(evoked.times[-1]),
                        sampling_rate_hz=float(evoked.info["sfreq"]),
                        channel_time_summary=_channel_time_summary(evoked),
                    )
                )
    except ErpError as exc:
        raise ErpError(
            str(exc),
            processing_warnings=_dedupe(
                _format_warning_records(warning_records) + exc.processing_warnings
            ),
        ) from exc
    except Exception as exc:
        raise ErpError(
            f"ERP generation failed: {exc}",
            processing_warnings=_dedupe(_format_warning_records(warning_records)),
        ) from exc

    warnings = _dedupe(_format_warning_records(warning_records))
    condition_payloads = [
        {
            "condition": artifact.condition,
            "safe_condition": artifact.safe_condition,
            "evoked_path": artifact.evoked_path,
            "nave": artifact.nave,
            "channel_count": artifact.channel_count,
            "time_min_seconds": artifact.time_min_seconds,
            "time_max_seconds": artifact.time_max_seconds,
            "sampling_rate_hz": artifact.sampling_rate_hz,
            "channel_time_summary": artifact.channel_time_summary,
        }
        for artifact in artifacts
    ]
    return {
        "file_format": "fif",
        "mne_version": str(mne.__version__),
        "input_epoch_run_id": config.epoch_run_id,
        "input_epochs_path": str(epochs_path),
        "condition_count": len(condition_payloads),
        "evoked_count": len(condition_payloads),
        "conditions": condition_payloads,
        "warnings": warnings,
        "metadata": {
            "schema_version": 1,
            "input": {
                "epoch_run_id": config.epoch_run_id,
                "epochs_path": str(epochs_path),
            },
            "config": {
                "epoch_run_id": config.epoch_run_id,
                "conditions": config.conditions,
                "picks": config.picks,
                "method": config.method,
            },
            "conditions": condition_payloads,
            "warnings": warnings,
        },
    }


def safe_condition_filename(condition: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", condition.strip())
    safe = safe.strip("._-")
    return safe or "condition"


def _selected_conditions(
    available_conditions: list[str],
    requested_conditions: list[str] | None,
) -> list[str]:
    if not available_conditions:
        raise ErpError("Epochs contain no conditions.")

    conditions = (
        available_conditions
        if not requested_conditions
        else [condition for condition in requested_conditions if condition]
    )
    missing = sorted(set(conditions).difference(available_conditions))
    if missing:
        raise ErpError(f"Requested conditions are not available: {', '.join(missing)}")
    if not conditions:
        raise ErpError("At least one ERP condition is required.")
    return conditions


def _channel_time_summary(evoked: Any) -> dict[str, Any]:
    import numpy as np

    data_uv = evoked.data * 1e6
    times = evoked.times
    ch_names = evoked.ch_names

    positive_index = np.unravel_index(np.argmax(data_uv), data_uv.shape)
    negative_index = np.unravel_index(np.argmin(data_uv), data_uv.shape)
    gfp_uv = data_uv.std(axis=0)
    gfp_index = int(np.argmax(gfp_uv))

    return {
        "peak_positive": _peak_payload(
            channel_names=ch_names,
            times=times,
            data_uv=data_uv,
            index=positive_index,
        ),
        "peak_negative": _peak_payload(
            channel_names=ch_names,
            times=times,
            data_uv=data_uv,
            index=negative_index,
        ),
        "global_field_power_peak": {
            "time_seconds": float(times[gfp_index]),
            "amplitude_uv": float(gfp_uv[gfp_index]),
        },
    }


def _peak_payload(
    channel_names: list[str],
    times: Any,
    data_uv: Any,
    index: tuple[int, int],
) -> dict[str, str | float]:
    channel_index, time_index = int(index[0]), int(index[1])
    return {
        "channel": channel_names[channel_index],
        "time_seconds": float(times[time_index]),
        "amplitude_uv": float(data_uv[channel_index, time_index]),
    }


def _format_warning_records(
    warning_records: list[python_warnings.WarningMessage],
) -> list[str]:
    return [str(warning.message) for warning in warning_records]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped
