import pytest

from eeg_core.domain import EventColumnMapping, EventRowFilter, EventRowFilterCondition
from eeg_io.event_logs import (
    EVENT_MAPPING_PRESETS,
    EventLogNormalizationError,
    event_mapping_preset,
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
    assert event_log.events[0].source_columns == {
        "stim_onset": "1.0",
        "stim_duration": "0.2",
        "condition": "target",
        "key_resp.keys": "space",
        "key_resp.corr": "1",
        "key_resp.rt": "0.42",
    }
    assert event_log.events[1].duration_seconds is None
    assert event_log.events[1].correct is False


def test_normalize_event_log_treats_null_tokens_as_none(tmp_path):
    path = tmp_path / "events.tsv"
    path.write_text(
        "onset\tduration\ttrial_type\tstimulus\tresponse\tcorrect\trt\n"
        "1.0\tn/a\tNA\tN/A\t\tNULL\tnull\n"
        "2.0\t0.1\t target \tstimulus-a\tspace\ttrue\t0.42\n",
        encoding="utf-8",
    )

    event_log = normalize_event_log(
        dataset_id="dataset-001",
        event_log_id="event-log-001",
        file_id="file-001",
        path=path,
        mapping=EventColumnMapping(
            onset_seconds="onset",
            duration_seconds="duration",
            trial_type="trial_type",
            stimulus="stimulus",
            response="response",
            correct="correct",
            reaction_time_seconds="rt",
        ),
    )

    first_event = event_log.events[0]
    assert first_event.duration_seconds is None
    assert first_event.trial_type is None
    assert first_event.stimulus is None
    assert first_event.response is None
    assert first_event.correct is None
    assert first_event.reaction_time_seconds is None
    assert first_event.source_columns == {
        "onset": "1.0",
        "duration": None,
        "trial_type": None,
        "stimulus": None,
        "response": None,
        "correct": None,
        "rt": None,
    }

    second_event = event_log.events[1]
    assert second_event.duration_seconds == 0.1
    assert second_event.trial_type == "target"
    assert second_event.stimulus == "stimulus-a"
    assert second_event.response == "space"
    assert second_event.correct is True
    assert second_event.reaction_time_seconds == 0.42


def test_normalize_event_log_applies_include_and_exclude_row_filter(tmp_path):
    path = tmp_path / "events.tsv"
    path.write_text(
        "onset\ttrial_type\tstatus\n"
        "1.0\ttarget\tkeep\n"
        "2.0\tstandard\tkeep\n"
        "3.0\ttarget\treject\n"
        "4.0\ttarget\tkeep\n",
        encoding="utf-8",
    )

    event_log = normalize_event_log(
        dataset_id="dataset-001",
        event_log_id="event-log-001",
        file_id="file-001",
        path=path,
        mapping=EventColumnMapping(
            onset_seconds="onset",
            trial_type="trial_type",
        ),
        row_filter=EventRowFilter(
            include=[
                EventRowFilterCondition(column="trial_type", equals="target"),
            ],
            exclude=[
                EventRowFilterCondition(column="status", equals="reject"),
            ],
        ),
    )

    assert event_log.row_count == 4
    assert event_log.filter_count == 2
    assert [event.source_row for event in event_log.events] == [1, 4]
    assert [event.onset_seconds for event in event_log.events] == [1.0, 4.0]
    assert event_log.events[0].source_columns == {
        "onset": "1.0",
        "trial_type": "target",
        "status": "keep",
    }


def test_normalize_event_log_derives_bids_condition_from_value_fallback(tmp_path):
    path = tmp_path / "events.tsv"
    path.write_text(
        "onset\tduration\ttrial_type\tvalue\tstatus\n"
        "1.0\t0.1\tn/a\t111\tkeep\n"
        "2.0\t0.2\tstandard\t222\tkeep\n"
        "3.0\t0.3\tNA\t333\treject\n",
        encoding="utf-8",
    )

    event_log = normalize_event_log(
        dataset_id="dataset-001",
        event_log_id="event-log-001",
        file_id="file-001",
        path=path,
        mapping=event_mapping_preset("bids_events"),
        row_filter=EventRowFilter(
            exclude=[EventRowFilterCondition(column="status", equals="reject")],
        ),
    )

    assert event_log.row_count == 3
    assert event_log.filter_count == 1
    assert [event.source_row for event in event_log.events] == [1, 2]
    assert [event.trial_type for event in event_log.events] == ["111", "standard"]
    assert event_log.events[0].source_columns == {
        "onset": "1.0",
        "duration": "0.1",
        "trial_type": None,
        "value": "111",
        "status": "keep",
    }


def test_normalize_event_log_accepts_configured_condition_column(tmp_path):
    path = tmp_path / "events.tsv"
    path.write_text(
        "onset\ttrial_type\tvalue\tstim_file\n"
        "1.0\tignored\t111\tface-a.png\n"
        "2.0\tstandard\t222\tN/A\n",
        encoding="utf-8",
    )

    event_log = normalize_event_log(
        dataset_id="dataset-001",
        event_log_id="event-log-001",
        file_id="file-001",
        path=path,
        mapping=EventColumnMapping(onset_seconds="onset", trial_type="trial_type"),
        condition_column="stim_file",
    )

    assert event_log.condition_column == "stim_file"
    assert [event.trial_type for event in event_log.events] == ["face-a.png", None]
    assert event_log.events[0].source_columns == {
        "onset": "1.0",
        "trial_type": "ignored",
        "stim_file": "face-a.png",
    }


def test_normalize_event_log_rejects_unknown_condition_column(tmp_path):
    path = tmp_path / "events.tsv"
    path.write_text("onset\ttrial_type\n1.0\ttarget\n", encoding="utf-8")

    with pytest.raises(EventLogNormalizationError, match="Condition column"):
        normalize_event_log(
            dataset_id="dataset-001",
            event_log_id="event-log-001",
            file_id="file-001",
            path=path,
            mapping=EventColumnMapping(onset_seconds="onset"),
            condition_column="missing",
        )


def test_normalize_event_log_rejects_unknown_row_filter_column(tmp_path):
    path = tmp_path / "events.tsv"
    path.write_text("onset\ttrial_type\n1.0\ttarget\n", encoding="utf-8")

    with pytest.raises(EventLogNormalizationError, match="missing"):
        normalize_event_log(
            dataset_id="dataset-001",
            event_log_id="event-log-001",
            file_id="file-001",
            path=path,
            mapping=EventColumnMapping(onset_seconds="onset"),
            row_filter=EventRowFilter(
                include=[EventRowFilterCondition(column="missing", equals="target")],
            ),
        )


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


def test_event_mapping_presets_are_defined():
    assert set(EVENT_MAPPING_PRESETS) == {
        "psychopy",
        "bids_events",
        "eeglab_annotations",
    }
    assert event_mapping_preset("psychopy") == EventColumnMapping(
        onset_seconds="stim_onset",
        duration_seconds="stim_duration",
        trial_type="condition",
        response="key_resp.keys",
        correct="key_resp.corr",
        reaction_time_seconds="key_resp.rt",
    )
    assert event_mapping_preset("bids_events") == EventColumnMapping(
        onset_seconds="onset",
        duration_seconds="duration",
        trial_type="trial_type",
        stimulus="stimulus",
        response="response",
        correct="correct",
        reaction_time_seconds="response_time",
    )
    assert event_mapping_preset("eeglab_annotations") == EventColumnMapping(
        onset_seconds="onset",
        duration_seconds="duration",
        trial_type="type",
    )
