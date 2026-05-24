from eeg_core.domain.ingestion import (
    Dataset,
    DatasetStatus,
    EventLog,
    Recording,
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
)


def validate_ingestion_dataset(
    dataset: Dataset,
    recording: Recording | None,
    event_log: EventLog | None,
) -> ValidationReport:
    issues: list[ValidationIssue] = []

    if recording is None:
        issues.append(
            _issue(
                severity=ValidationSeverity.ERROR,
                code="recording_missing",
                message="Upload a readable EEG file before validation.",
                field="recording_id",
            )
        )
    else:
        _validate_recording(recording, issues)

    if event_log is None:
        issues.append(
            _issue(
                severity=ValidationSeverity.ERROR,
                code="event_log_missing",
                message="Upload and map an event log before validation.",
                field="event_log_id",
            )
        )
    else:
        _validate_event_log(event_log, recording, issues)

    if not dataset.metadata.get("participant_label"):
        issues.append(
            _issue(
                severity=ValidationSeverity.WARNING,
                code="participant_label_missing",
                message="Participant label is missing.",
                field="metadata.participant_label",
            )
        )
    if not dataset.metadata.get("session_label"):
        issues.append(
            _issue(
                severity=ValidationSeverity.WARNING,
                code="session_label_missing",
                message="Session label is missing.",
                field="metadata.session_label",
            )
        )

    status = (
        DatasetStatus.INVALID
        if any(issue.severity == ValidationSeverity.ERROR for issue in issues)
        else DatasetStatus.VALID
    )
    return ValidationReport(
        dataset_id=dataset.dataset_id,
        status=status,
        issues=issues,
    )


def _validate_recording(
    recording: Recording,
    issues: list[ValidationIssue],
) -> None:
    metadata = recording.metadata
    if metadata.sampling_rate_hz <= 0:
        issues.append(
            _issue(
                severity=ValidationSeverity.ERROR,
                code="sampling_rate_invalid",
                message="EEG sampling rate is missing or invalid.",
                field="recording.metadata.sampling_rate_hz",
            )
        )
    if metadata.duration_seconds <= 0:
        issues.append(
            _issue(
                severity=ValidationSeverity.ERROR,
                code="duration_invalid",
                message="EEG recording duration is missing or invalid.",
                field="recording.metadata.duration_seconds",
            )
        )
    if metadata.channel_count <= 0 or not metadata.channel_names:
        issues.append(
            _issue(
                severity=ValidationSeverity.ERROR,
                code="channels_missing",
                message="EEG channel list is missing.",
                field="recording.metadata.channel_names",
            )
        )


def _validate_event_log(
    event_log: EventLog,
    recording: Recording | None,
    issues: list[ValidationIssue],
) -> None:
    if event_log.row_count <= 0 or not event_log.events:
        issues.append(
            _issue(
                severity=ValidationSeverity.ERROR,
                code="event_log_empty",
                message="Event log does not contain normalized events.",
                field="events",
            )
        )
        return

    if recording is not None and recording.metadata.duration_seconds > 0:
        duration = recording.metadata.duration_seconds
        for event in event_log.events:
            if event.onset_seconds < 0 or event.onset_seconds > duration:
                issues.append(
                    _issue(
                        severity=ValidationSeverity.ERROR,
                        code="event_onset_out_of_range",
                        message="Event onset is outside the EEG recording duration.",
                        field=f"events[{event.source_row}].onset_seconds",
                    )
                )

    if all(event.duration_seconds is None for event in event_log.events):
        issues.append(
            _issue(
                severity=ValidationSeverity.WARNING,
                code="event_duration_missing",
                message="Event duration is missing and may need to be inferred.",
                field="events.duration_seconds",
            )
        )
    if all(event.response is None for event in event_log.events):
        issues.append(
            _issue(
                severity=ValidationSeverity.WARNING,
                code="event_response_missing",
                message="Event log has no response values.",
                field="events.response",
            )
        )
    if all(event.correct is None for event in event_log.events):
        issues.append(
            _issue(
                severity=ValidationSeverity.WARNING,
                code="event_correct_missing",
                message="Event log has no accuracy values.",
                field="events.correct",
            )
        )
    if all(event.reaction_time_seconds is None for event in event_log.events):
        issues.append(
            _issue(
                severity=ValidationSeverity.WARNING,
                code="event_reaction_time_missing",
                message="Event log has no reaction-time values.",
                field="events.reaction_time_seconds",
            )
        )


def _issue(
    severity: ValidationSeverity,
    code: str,
    message: str,
    field: str | None,
) -> ValidationIssue:
    return ValidationIssue(
        severity=severity,
        code=code,
        message=message,
        field=field,
    )
