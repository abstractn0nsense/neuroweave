from dataclasses import dataclass, field
from typing import Any

from eeg_core.domain import NormalizedEvent


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


def _condition_label(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value).lower()

    label = str(value).strip()
    if not label:
        return None
    return label
