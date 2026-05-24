import pytest

from eeg_core.domain import EventColumnMapping
from eeg_io.event_logs import (
    EventLogNormalizationError,
    normalize_event_log,
    preview_event_log,
)


def test_preview_event_log_reads_csv_headers_and_rows(tmp_path):
    path = tmp_path / "psychopy.csv"
    path.write_text(
        "stim_onset,condition,key_resp.keys,key_resp.rt\n"
        "1.0,target,space,0.42\n"
        "2.0,standard,,\n",
        encoding="utf-8",
    )

    preview = preview_event_log(path)

    assert preview["delimiter"] == ","
    assert preview["columns"] == [
        "stim_onset",
        "condition",
        "key_resp.keys",
        "key_resp.rt",
    ]
    assert preview["row_count"] == 2
    assert preview["preview_rows"][0]["condition"] == "target"


def test_preview_event_log_reads_tsv(tmp_path):
    path = tmp_path / "events.tsv"
    path.write_text(
        "onset\tduration\ttrial_type\n"
        "0.5\t0.2\tstim/left\n",
        encoding="utf-8",
    )

    preview = preview_event_log(path)

    assert preview["delimiter"] == "\t"
    assert preview["columns"] == ["onset", "duration", "trial_type"]
    assert preview["row_count"] == 1


def test_normalize_event_log_applies_column_mapping(tmp_path):
    path = tmp_path / "psychopy.csv"
    path.write_text(
        "stim_onset,stim_duration,condition,key_resp.keys,key_resp.corr,key_resp.rt\n"
        "1.0,0.2,target,space,1,0.42\n"
        "2.0,,standard,,0,\n",
        encoding="utf-8",
    )

    event_log = normalize_event_log(
        dataset_id="dataset-001",
        event_log_id="event-log-001",
        file_id="file-001",
        path=path,
        mapping=EventColumnMapping(
            onset_seconds="stim_onset",
            duration_seconds="stim_duration",
            trial_type="condition",
            response="key_resp.keys",
            correct="key_resp.corr",
            reaction_time_seconds="key_resp.rt",
        ),
    )

    assert event_log.row_count == 2
    assert event_log.events[0].onset_seconds == 1.0
    assert event_log.events[0].duration_seconds == 0.2
    assert event_log.events[0].trial_type == "target"
    assert event_log.events[0].correct is True
    assert event_log.events[1].duration_seconds is None
    assert event_log.events[1].correct is False


def test_normalize_event_log_requires_onset_mapping(tmp_path):
    path = tmp_path / "events.tsv"
    path.write_text("onset\ttrial_type\n1.0\ttarget\n", encoding="utf-8")

    with pytest.raises(EventLogNormalizationError, match="onset_seconds"):
        normalize_event_log(
            dataset_id="dataset-001",
            event_log_id="event-log-001",
            file_id="file-001",
            path=path,
            mapping=EventColumnMapping(trial_type="trial_type"),
        )
