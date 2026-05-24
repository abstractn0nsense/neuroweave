from dataclasses import asdict

from eeg_core.domain import (
    ComparisonConfig,
    Dataset,
    DatasetStatus,
    EpochConfig,
    EpochRun,
    EpochRunStatus,
    ErpConfig,
    ErpRun,
    ErpRunStatus,
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


def test_epoch_run_contract_defaults_to_pending_epoch_run():
    run = EpochRun(
        run_id="epoch-001",
        dataset_id="dataset-001",
        config=EpochConfig(
            preprocessing_run_id="preprocess-001",
            condition_field="trial_type",
            tmin_seconds=-0.2,
            tmax_seconds=0.8,
            baseline_start_seconds=-0.2,
            baseline_end_seconds=0.0,
            reject_eeg_uv=150.0,
        ),
        output_path="data/epochs/dataset-001/epoch-001/epochs.fif",
    )

    payload = asdict(run)

    assert run.status == EpochRunStatus.PENDING
    assert payload["run_kind"] == "epoch"
    assert payload["schema_version"] == 1
    assert payload["config"]["preprocessing_run_id"] == "preprocess-001"
    assert payload["config"]["condition_field"] == "trial_type"


def test_erp_run_contract_defaults_to_pending_erp_run():
    run = ErpRun(
        run_id="erp-001",
        dataset_id="dataset-001",
        config=ErpConfig(
            epoch_run_id="epoch-001",
            conditions=["target"],
            plot_mode="gfp",
        ),
        output_path="data/erp/dataset-001/erp-001/erp_metadata.json",
    )

    payload = asdict(run)

    assert run.status == ErpRunStatus.PENDING
    assert payload["run_kind"] == "erp"
    assert payload["schema_version"] == 1
    assert payload["config"]["epoch_run_id"] == "epoch-001"
    assert payload["config"]["conditions"] == ["target"]
    assert payload["config"]["plot_mode"] == "gfp"


def test_comparison_config_contract_is_descriptive_only():
    config = ComparisonConfig(
        erp_run_id="erp-001",
        condition_a="target",
        condition_b="standard",
        channel=None,
        use_gfp=True,
        window_start_seconds=-0.05,
        window_end_seconds=0.2,
    )

    payload = asdict(config)

    assert payload["erp_run_id"] == "erp-001"
    assert payload["condition_a"] == "target"
    assert payload["condition_b"] == "standard"
    assert payload["metric"] == "mean_amplitude_uv"


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
