import pytest

from eeg_core.domain import NormalizedEvent
from eeg_processing.epoching import (
    EpochEventConversionError,
    normalized_events_to_mne_events,
)


def test_normalized_events_convert_to_mne_rows_and_sorted_event_ids():
    conversion = normalized_events_to_mne_events(
        events=[
            NormalizedEvent(
                onset_seconds=0.5,
                source_row=1,
                trial_type="standard",
            ),
            NormalizedEvent(
                onset_seconds=1.0,
                source_row=2,
                trial_type="target",
            ),
            NormalizedEvent(
                onset_seconds=1.5,
                source_row=3,
                trial_type="standard",
            ),
        ],
        condition_field="trial_type",
        sampling_rate_hz=100.0,
    )

    assert conversion.event_id == {"standard": 1, "target": 2}
    assert conversion.events == [
        [50, 0, 1],
        [100, 0, 2],
        [150, 0, 1],
    ]
    assert conversion.condition_counts == {"standard": 2, "target": 1}
    assert conversion.skipped.total == 0
    assert conversion.used_event_count == 3


def test_conversion_skips_missing_empty_and_negative_events():
    conversion = normalized_events_to_mne_events(
        events=[
            NormalizedEvent(
                onset_seconds=0.1,
                source_row=1,
                stimulus=" image-a ",
            ),
            NormalizedEvent(
                onset_seconds=0.2,
                source_row=2,
                stimulus="",
            ),
            NormalizedEvent(
                onset_seconds=0.3,
                source_row=3,
                stimulus=None,
            ),
            NormalizedEvent(
                onset_seconds=-0.1,
                source_row=4,
                stimulus="image-b",
            ),
        ],
        condition_field="stimulus",
        sampling_rate_hz=250.0,
    )

    assert conversion.event_id == {"image-a": 1}
    assert conversion.events == [[25, 0, 1]]
    assert conversion.condition_counts == {"image-a": 1}
    assert conversion.skipped.missing_condition == 2
    assert conversion.skipped.negative_onset == 1
    assert conversion.skipped.total == 3
    assert conversion.skipped.details == [
        {"source_row": 2, "reason": "missing_condition"},
        {"source_row": 3, "reason": "missing_condition"},
        {"source_row": 4, "reason": "negative_onset"},
    ]


def test_boolean_condition_labels_are_deterministic_lowercase_strings():
    conversion = normalized_events_to_mne_events(
        events=[
            NormalizedEvent(onset_seconds=0.1, source_row=1, correct=True),
            NormalizedEvent(onset_seconds=0.2, source_row=2, correct=False),
            NormalizedEvent(onset_seconds=0.3, source_row=3, correct=True),
        ],
        condition_field="correct",
        sampling_rate_hz=10.0,
    )

    assert conversion.event_id == {"false": 1, "true": 2}
    assert conversion.events == [
        [1, 0, 2],
        [2, 0, 1],
        [3, 0, 2],
    ]
    assert conversion.condition_counts == {"false": 1, "true": 2}


def test_conversion_rejects_unknown_condition_field():
    with pytest.raises(EpochEventConversionError, match="Unsupported condition field"):
        normalized_events_to_mne_events(
            events=[
                NormalizedEvent(
                    onset_seconds=0.1,
                    source_row=1,
                    trial_type="target",
                )
            ],
            condition_field="reaction_time_seconds",
            sampling_rate_hz=100.0,
        )


def test_conversion_rejects_invalid_sampling_rate():
    with pytest.raises(EpochEventConversionError, match="sampling_rate_hz"):
        normalized_events_to_mne_events(
            events=[
                NormalizedEvent(
                    onset_seconds=0.1,
                    source_row=1,
                    trial_type="target",
                )
            ],
            condition_field="trial_type",
            sampling_rate_hz=0.0,
        )


def test_conversion_rejects_no_valid_events():
    with pytest.raises(EpochEventConversionError, match="No valid events"):
        normalized_events_to_mne_events(
            events=[
                NormalizedEvent(onset_seconds=0.1, source_row=1),
                NormalizedEvent(onset_seconds=-0.1, source_row=2, trial_type="target"),
            ],
            condition_field="trial_type",
            sampling_rate_hz=100.0,
        )
