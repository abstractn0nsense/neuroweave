from dataclasses import replace

from apps.api import main as api_main
from eeg_core.domain import (
    Dataset,
    DatasetStatus,
    EpochConfig,
    EventColumnMapping,
    EventLog,
    NormalizedEvent,
    PreprocessingConfig,
    PreprocessingRun,
    PreprocessingRunStatus,
    Recording,
    RecordingMetadata,
)


def _epoch_config(**overrides) -> EpochConfig:
    values = {
        "preprocessing_run_id": "preprocess-001",
        "condition_field": "trial_type",
        "tmin_seconds": -0.2,
        "tmax_seconds": 0.8,
        "baseline_start_seconds": -0.2,
        "baseline_end_seconds": 0.0,
        "reject_eeg_uv": 150.0,
    }
    values.update(overrides)
    return EpochConfig(**values)


def _dataset(status: DatasetStatus = DatasetStatus.VALID) -> Dataset:
    return Dataset(
        dataset_id="dataset-001",
        project_id="project-001",
        experiment_id="experiment-001",
        participant_id="participant-001",
        session_id="session-001",
        status=status,
    )


def _event_log(events: list[NormalizedEvent] | None = None) -> EventLog:
    return EventLog(
        event_log_id="event-log-001",
        dataset_id="dataset-001",
        file_id="file-001",
        mapping=EventColumnMapping(onset_seconds="onset", trial_type="condition"),
        row_count=len(events or []),
        events=events
        if events is not None
        else [
            NormalizedEvent(
                onset_seconds=1.0,
                source_row=1,
                trial_type="standard",
            ),
            NormalizedEvent(
                onset_seconds=2.0,
                source_row=2,
                trial_type="target",
            ),
        ],
    )


def _recording() -> Recording:
    return Recording(
        recording_id="recording-001",
        dataset_id="dataset-001",
        file_id="file-001",
        metadata=RecordingMetadata(
            dataset_id="dataset-001",
            file_format="fif",
            channel_count=8,
            sampling_rate_hz=256.0,
            duration_seconds=4.0,
            channel_names=["Fp1", "Fp2"],
        ),
    )


def _preprocessing_run(output_path, **overrides) -> PreprocessingRun:
    values = {
        "run_id": "preprocess-001",
        "dataset_id": "dataset-001",
        "config": PreprocessingConfig(reference="average"),
        "status": PreprocessingRunStatus.COMPLETED,
        "output_path": str(output_path),
        "output_metadata": {
            "output_sampling_rate_hz": 128.0,
            "output_duration_seconds": 4.0,
        },
    }
    values.update(overrides)
    return PreprocessingRun(**values)


def _validate(config, preprocessing_run, event_log=None, recording=None):
    return api_main._validate_epoch_config(
        config=config,
        dataset=_dataset(),
        preprocessing_run=preprocessing_run,
        event_log=event_log if event_log is not None else _event_log(),
        recording=recording if recording is not None else _recording(),
    )


def test_epoch_config_validation_accepts_valid_config(tmp_path):
    output_path = tmp_path / "raw_preprocessed.fif"
    output_path.write_bytes(b"placeholder")

    errors, warnings = _validate(
        _epoch_config(),
        _preprocessing_run(output_path),
    )

    assert errors == []
    assert warnings == []


def test_epoch_config_validation_rejects_dataset_and_input_run_errors(tmp_path):
    missing_path = tmp_path / "missing_raw_preprocessed.fif"

    errors, warnings = api_main._validate_epoch_config(
        config=_epoch_config(),
        dataset=_dataset(status=DatasetStatus.INVALID),
        preprocessing_run=_preprocessing_run(
            missing_path,
            dataset_id="other-dataset",
            status=PreprocessingRunStatus.RUNNING,
        ),
        event_log=_event_log(),
        recording=_recording(),
    )

    assert warnings == []
    assert "Dataset must be valid before epoching." in errors
    assert "Preprocessing run must belong to the selected dataset." in errors
    assert "Preprocessing run must be completed before epoching." in errors
    assert "Preprocessing output file was not found." in errors


def test_epoch_config_validation_rejects_invalid_window_and_baseline(tmp_path):
    output_path = tmp_path / "raw_preprocessed.fif"
    output_path.write_bytes(b"placeholder")

    errors, _ = _validate(
        _epoch_config(
            tmin_seconds=0.8,
            tmax_seconds=0.0,
            baseline_start_seconds=-0.2,
            baseline_end_seconds=1.0,
        ),
        _preprocessing_run(output_path),
    )

    assert "tmin_seconds must be lower than tmax_seconds." in errors
    assert "tmax_seconds must be greater than 0." in errors
    assert "Baseline range must be inside the epoch time window." in errors


def test_epoch_config_validation_rejects_partial_and_reversed_baseline(tmp_path):
    output_path = tmp_path / "raw_preprocessed.fif"
    output_path.write_bytes(b"placeholder")

    partial_errors, _ = _validate(
        _epoch_config(baseline_start_seconds=-0.2, baseline_end_seconds=None),
        _preprocessing_run(output_path),
    )
    reversed_errors, _ = _validate(
        _epoch_config(baseline_start_seconds=0.1, baseline_end_seconds=0.0),
        _preprocessing_run(output_path),
    )

    assert partial_errors == [
        "baseline_start_seconds and baseline_end_seconds must both be set or both be null."
    ]
    assert (
        "baseline_start_seconds must be lower than or equal to baseline_end_seconds."
        in reversed_errors
    )


def test_epoch_config_validation_rejects_unknown_condition_and_threshold(tmp_path):
    output_path = tmp_path / "raw_preprocessed.fif"
    output_path.write_bytes(b"placeholder")

    errors, _ = _validate(
        _epoch_config(condition_field="reaction_time_seconds", reject_eeg_uv=0.0),
        _preprocessing_run(output_path),
    )

    assert "Unsupported condition field: reaction_time_seconds." in errors
    assert "reject_eeg_uv must be greater than 0." in errors


def test_epoch_config_validation_rejects_no_usable_condition_values(tmp_path):
    output_path = tmp_path / "raw_preprocessed.fif"
    output_path.write_bytes(b"placeholder")

    errors, warnings = _validate(
        _epoch_config(condition_field="trial_type"),
        _preprocessing_run(output_path),
        event_log=_event_log(
            [
                NormalizedEvent(onset_seconds=1.0, source_row=1),
                NormalizedEvent(onset_seconds=2.0, source_row=2, trial_type=""),
            ]
        ),
    )

    assert errors == ["No usable events found for condition field: trial_type."]
    assert warnings == []


def test_epoch_config_validation_rejects_all_events_out_of_bounds(tmp_path):
    output_path = tmp_path / "raw_preprocessed.fif"
    output_path.write_bytes(b"placeholder")

    errors, warnings = _validate(
        _epoch_config(tmin_seconds=-0.2, tmax_seconds=0.8),
        _preprocessing_run(output_path),
        event_log=_event_log(
            [
                NormalizedEvent(
                    onset_seconds=3.6,
                    source_row=1,
                    trial_type="target",
                )
            ]
        ),
    )

    assert errors == ["All candidate epoch windows are outside the recording bounds."]
    assert warnings == []


def test_epoch_config_validation_warns_for_partial_out_of_bounds_events(tmp_path):
    output_path = tmp_path / "raw_preprocessed.fif"
    output_path.write_bytes(b"placeholder")

    errors, warnings = _validate(
        _epoch_config(tmin_seconds=-0.2, tmax_seconds=0.8),
        _preprocessing_run(output_path),
        event_log=_event_log(
            [
                NormalizedEvent(
                    onset_seconds=1.0,
                    source_row=1,
                    trial_type="standard",
                ),
                NormalizedEvent(
                    onset_seconds=3.6,
                    source_row=2,
                    trial_type="target",
                ),
            ]
        ),
    )

    assert errors == []
    assert warnings == [
        "1 candidate events fall outside the epoch window bounds and will be skipped."
    ]


def test_epoch_config_validation_falls_back_to_recording_metadata(tmp_path):
    output_path = tmp_path / "raw_preprocessed.fif"
    output_path.write_bytes(b"placeholder")
    run = replace(_preprocessing_run(output_path), output_metadata={})

    errors, warnings = _validate(_epoch_config(), run)

    assert errors == []
    assert warnings == []
