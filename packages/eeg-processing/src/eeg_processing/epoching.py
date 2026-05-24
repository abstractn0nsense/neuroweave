from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import warnings as python_warnings

from eeg_core.domain import EpochConfig, EventLog, NormalizedEvent


SUPPORTED_CONDITION_FIELDS = frozenset(
    {
        "trial_type",
        "stimulus",
        "response",
        "correct",
    }
)


class EpochEventConversionError(Exception):
    pass


class EpochingError(Exception):
    def __init__(self, message: str, processing_warnings: list[str] | None = None):
        super().__init__(message)
        self.processing_warnings = processing_warnings or []


@dataclass(frozen=True)
class SkippedEventSummary:
    missing_condition: int = 0
    negative_onset: int = 0
    details: list[dict[str, int | str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.missing_condition + self.negative_onset


@dataclass(frozen=True)
class MneEventConversion:
    events: list[list[int]]
    event_id: dict[str, int]
    condition_counts: dict[str, int]
    skipped: SkippedEventSummary

    @property
    def used_event_count(self) -> int:
        return len(self.events)


def normalized_events_to_mne_events(
    events: list[NormalizedEvent],
    condition_field: str,
    sampling_rate_hz: float,
) -> MneEventConversion:
    if condition_field not in SUPPORTED_CONDITION_FIELDS:
        raise EpochEventConversionError(
            f"Unsupported condition field: {condition_field}"
        )
    if sampling_rate_hz <= 0:
        raise EpochEventConversionError("sampling_rate_hz must be greater than 0.")

    valid_events: list[tuple[int, str]] = []
    skipped_details: list[dict[str, int | str]] = []
    missing_condition = 0
    negative_onset = 0

    for event in events:
        if event.onset_seconds < 0:
            negative_onset += 1
            skipped_details.append(
                {
                    "source_row": event.source_row,
                    "reason": "negative_onset",
                }
            )
            continue

        label = _condition_label(getattr(event, condition_field))
        if label is None:
            missing_condition += 1
            skipped_details.append(
                {
                    "source_row": event.source_row,
                    "reason": "missing_condition",
                }
            )
            continue

        sample_index = round(event.onset_seconds * sampling_rate_hz)
        valid_events.append((sample_index, label))

    if not valid_events:
        raise EpochEventConversionError(
            f"No valid events found for condition field: {condition_field}"
        )

    labels = sorted({label for _, label in valid_events})
    event_id = {label: index + 1 for index, label in enumerate(labels)}
    condition_counts = {label: 0 for label in labels}
    mne_events: list[list[int]] = []

    for sample_index, label in valid_events:
        condition_counts[label] += 1
        mne_events.append([sample_index, 0, event_id[label]])

    return MneEventConversion(
        events=mne_events,
        event_id=event_id,
        condition_counts=condition_counts,
        skipped=SkippedEventSummary(
            missing_condition=missing_condition,
            negative_onset=negative_onset,
            details=skipped_details,
        ),
    )


def epoch_preprocessed_eeg(
    input_path: Path,
    output_path: Path,
    event_log: EventLog,
    config: EpochConfig,
    preprocessing_run_id: str,
) -> dict[str, Any]:
    manual_warnings: list[str] = []
    warning_records: list[python_warnings.WarningMessage] = []
    try:
        with python_warnings.catch_warnings(record=True) as warning_records:
            python_warnings.simplefilter("always")

            import mne
            import numpy as np

            raw = mne.io.read_raw_fif(input_path, preload=True, verbose=False)
            sampling_rate = float(raw.info["sfreq"])
            input_duration = raw.n_times / sampling_rate if sampling_rate else 0
            conversion = normalized_events_to_mne_events(
                events=event_log.events,
                condition_field=config.condition_field,
                sampling_rate_hz=sampling_rate,
            )
            if conversion.skipped.total:
                manual_warnings.append(
                    f"{conversion.skipped.total} events were skipped before epoching."
                )

            mne_events = np.asarray(conversion.events, dtype=int)
            reject = (
                {"eeg": config.reject_eeg_uv * 1e-6}
                if config.reject_eeg_uv is not None
                else None
            )
            baseline = (
                None
                if config.baseline_start_seconds is None
                and config.baseline_end_seconds is None
                else (config.baseline_start_seconds, config.baseline_end_seconds)
            )

            epochs = mne.Epochs(
                raw,
                mne_events,
                event_id=conversion.event_id,
                tmin=config.tmin_seconds,
                tmax=config.tmax_seconds,
                baseline=baseline,
                reject=reject,
                preload=True,
                verbose=False,
            )
            if len(epochs) == 0:
                raise EpochingError("Epoching produced no retained epochs.")

            output_path.parent.mkdir(parents=True, exist_ok=True)
            epochs.save(output_path, overwrite=True, verbose=False)
    except EpochingError as exc:
        raise EpochingError(
            str(exc),
            processing_warnings=_dedupe(
                manual_warnings
                + _format_warning_records(warning_records)
                + exc.processing_warnings
            ),
        ) from exc
    except EpochEventConversionError as exc:
        raise EpochingError(
            str(exc),
            processing_warnings=_dedupe(
                manual_warnings + _format_warning_records(warning_records)
            ),
        ) from exc
    except Exception as exc:
        raise EpochingError(
            f"Epoching failed: {exc}",
            processing_warnings=_dedupe(
                manual_warnings + _format_warning_records(warning_records)
            ),
        ) from exc

    warnings = _dedupe(manual_warnings + _format_warning_records(warning_records))
    retained_counts = _retained_condition_counts(
        epochs.events.tolist(),
        conversion.event_id,
    )
    dropped_counts = _dropped_condition_counts(
        events=conversion.events,
        event_id=conversion.event_id,
        drop_log=epochs.drop_log,
    )
    drop_reason_counts = _drop_reason_counts(epochs.drop_log)
    dropped_epoch_count = sum(1 for reasons in epochs.drop_log if reasons)
    retained_epoch_count = len(epochs)
    samples_per_epoch = int(epochs.get_data(copy=False).shape[-1])
    condition_counts = {
        "candidate": conversion.condition_counts,
        "retained": retained_counts,
        "dropped": dropped_counts,
    }
    summary = {
        "input": {
            "preprocessing_run_id": preprocessing_run_id,
            "path": str(input_path),
            "sampling_rate_hz": sampling_rate,
            "duration_seconds": input_duration,
            "channel_count": len(raw.ch_names),
        },
        "config": _config_summary(config),
        "events": {
            "total": len(event_log.events),
            "used": conversion.used_event_count,
            "skipped": conversion.skipped.total,
            "event_id": conversion.event_id,
            "skipped_summary": {
                "missing_condition": conversion.skipped.missing_condition,
                "negative_onset": conversion.skipped.negative_onset,
            },
        },
        "epochs": {
            "created": conversion.used_event_count,
            "retained": retained_epoch_count,
            "dropped": dropped_epoch_count,
            "samples_per_epoch": samples_per_epoch,
        },
        "timing": {
            "tmin_seconds": config.tmin_seconds,
            "tmax_seconds": config.tmax_seconds,
            "duration_seconds": config.tmax_seconds - config.tmin_seconds,
            "baseline": _baseline_summary(config),
        },
        "conditions": condition_counts,
        "drop_reasons": drop_reason_counts,
        "warnings": warnings,
    }
    return {
        "channel_count": len(raw.ch_names),
        "sampling_rate_hz": sampling_rate,
        "duration_seconds": input_duration,
        "file_format": "fif",
        "mne_version": str(mne.__version__),
        "input_preprocessing_run_id": preprocessing_run_id,
        "event_count_total": len(event_log.events),
        "event_count_used": conversion.used_event_count,
        "event_count_skipped": conversion.skipped.total,
        "condition_count": len(conversion.event_id),
        "epoch_count": retained_epoch_count,
        "dropped_epoch_count": dropped_epoch_count,
        "event_id": conversion.event_id,
        "condition_counts": condition_counts,
        "warnings": warnings,
        "diagnostics": {
            "epoch_summary": summary,
            "condition_counts": condition_counts,
            "drop_log": _drop_log_entries(
                events=conversion.events,
                event_id=conversion.event_id,
                drop_log=epochs.drop_log,
            ),
        },
    }


def _condition_label(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value).lower()

    label = str(value).strip()
    if not label:
        return None
    return label


def _config_summary(config: EpochConfig) -> dict[str, Any]:
    return {
        "preprocessing_run_id": config.preprocessing_run_id,
        "condition_field": config.condition_field,
        "tmin_seconds": config.tmin_seconds,
        "tmax_seconds": config.tmax_seconds,
        "baseline_start_seconds": config.baseline_start_seconds,
        "baseline_end_seconds": config.baseline_end_seconds,
        "reject_eeg_uv": config.reject_eeg_uv,
    }


def _baseline_summary(config: EpochConfig) -> dict[str, float | None]:
    return {
        "start_seconds": config.baseline_start_seconds,
        "end_seconds": config.baseline_end_seconds,
    }


def _retained_condition_counts(
    retained_events: list[list[int]],
    event_id: dict[str, int],
) -> dict[str, int]:
    labels_by_id = {identifier: label for label, identifier in event_id.items()}
    counts = {label: 0 for label in event_id}
    for event in retained_events:
        label = labels_by_id.get(event[2])
        if label is not None:
            counts[label] += 1
    return counts


def _dropped_condition_counts(
    events: list[list[int]],
    event_id: dict[str, int],
    drop_log: tuple[tuple[str, ...], ...],
) -> dict[str, int]:
    labels_by_id = {identifier: label for label, identifier in event_id.items()}
    counts = {label: 0 for label in event_id}
    for event, reasons in zip(events, drop_log):
        if not reasons:
            continue
        label = labels_by_id.get(event[2])
        if label is not None:
            counts[label] += 1
    return counts


def _drop_reason_counts(drop_log: tuple[tuple[str, ...], ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for reasons in drop_log:
        for reason in reasons:
            counts[str(reason)] = counts.get(str(reason), 0) + 1
    return counts


def _drop_log_entries(
    events: list[list[int]],
    event_id: dict[str, int],
    drop_log: tuple[tuple[str, ...], ...],
) -> list[dict[str, Any]]:
    labels_by_id = {identifier: label for label, identifier in event_id.items()}
    entries: list[dict[str, Any]] = []
    for index, (event, reasons) in enumerate(zip(events, drop_log)):
        if not reasons:
            continue
        entries.append(
            {
                "event_index": index,
                "sample": event[0],
                "event_code": event[2],
                "condition": labels_by_id.get(event[2]),
                "reasons": [str(reason) for reason in reasons],
            }
        )
    return entries


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
