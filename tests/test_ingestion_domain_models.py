from dataclasses import asdict

from eeg_core.domain import (
    Dataset,
    DatasetStatus,
    EventColumnMapping,
    Experiment,
    NormalizedEvent,
    Project,
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
)


def test_experiment_keeps_default_event_mapping():
    mapping = EventColumnMapping(
        onset_seconds="stim_onset",
        duration_seconds="stim_duration",
        trial_type="condition",
        response="key_resp.keys",
        correct="key_resp.corr",
        reaction_time_seconds="key_resp.rt",
    )

    experiment = Experiment(
        experiment_id="experiment-001",
        project_id="project-001",
        name="Oddball task",
        task_name="oddball",
        default_event_mapping=mapping,
    )

    assert experiment.default_event_mapping.onset_seconds == "stim_onset"
    assert experiment.default_event_mapping.trial_type == "condition"


def test_domain_models_are_plain_serializable_dataclasses():
    project = Project(project_id="project-001", name="Memory EEG")
    dataset = Dataset(
        dataset_id="dataset-001",
        project_id=project.project_id,
        experiment_id="experiment-001",
        participant_id="sub-001",
        session_id="ses-001",
        status=DatasetStatus.NEEDS_FILES,
    )
    event = NormalizedEvent(
        onset_seconds=1.5,
        duration_seconds=0.2,
        trial_type="target",
        response="space",
        correct=True,
        reaction_time_seconds=0.42,
        source_row=3,
    )

    assert asdict(dataset)["status"] == DatasetStatus.NEEDS_FILES
    assert asdict(event)["onset_seconds"] == 1.5
    assert asdict(event)["correct"] is True


def test_validation_report_exposes_errors_and_warnings():
    report = ValidationReport(
        dataset_id="dataset-001",
        status=DatasetStatus.INVALID,
        issues=[
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="event_onset_out_of_range",
                message="Event onset exceeds recording duration.",
                field="onset_seconds",
            ),
            ValidationIssue(
                severity=ValidationSeverity.WARNING,
                code="missing_response",
                message="Response column is not mapped.",
                field="response",
            ),
        ],
    )

    assert not report.valid
    assert [issue.code for issue in report.errors] == ["event_onset_out_of_range"]
    assert [issue.code for issue in report.warnings] == ["missing_response"]
