from dataclasses import asdict

from eeg_core.domain import (
    ComparisonConfig,
    ComparisonObservation,
    Dataset,
    DatasetStatus,
    DiagnosticWarning,
    DiagnosticWarningSource,
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
    diagnostic_warning_from_dict,
    diagnostic_warnings_from_strings,
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
        output_path="data/epochs/dataset-001/epoch-001/epochs-epo.fif",
    )

    payload = asdict(run)

    assert run.status == EpochRunStatus.PENDING
    assert payload["run_kind"] == "epoch"
    assert payload["schema_version"] == 1
    assert payload["config"]["preprocessing_run_id"] == "preprocess-001"
    assert payload["config"]["condition_field"] == "trial_type"
    assert payload["diagnostics"] == {}


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
    assert payload["diagnostics"] == {}


def test_comparison_config_contract_accepts_optional_paired_observations():
    config = ComparisonConfig(
        erp_run_id="erp-001",
        condition_a="target",
        condition_b="standard",
        channel=None,
        use_gfp=True,
        window_start_seconds=-0.05,
        window_end_seconds=0.2,
        paired_observations=[
            ComparisonObservation(
                subject_id="sub-001",
                condition_a_mean_amplitude_uv=1.2,
                condition_b_mean_amplitude_uv=0.8,
            )
        ],
    )

    payload = asdict(config)

    assert payload["erp_run_id"] == "erp-001"
    assert payload["condition_a"] == "target"
    assert payload["condition_b"] == "standard"
    assert payload["metric"] == "mean_amplitude_uv"
    assert payload["paired_observations"] == [
        {
            "subject_id": "sub-001",
            "condition_a_mean_amplitude_uv": 1.2,
            "condition_b_mean_amplitude_uv": 0.8,
        }
    ]


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


def test_diagnostic_warning_serializes_as_plain_payload():
    warning = DiagnosticWarning(
        severity=ValidationSeverity.WARNING,
        source="worker",
        code="reference_unchanged",
        impact="The original EEG reference was preserved.",
        suggested_action="Confirm that this matches the analysis plan.",
    )

    payload = asdict(warning)

    assert payload == {
        "severity": "warning",
        "source": "worker",
        "code": "reference_unchanged",
        "impact": "The original EEG reference was preserved.",
        "suggested_action": "Confirm that this matches the analysis plan.",
    }


def test_diagnostic_warning_deserializes_from_payload():
    warning = diagnostic_warning_from_dict(
        {
            "severity": "warning",
            "source": "worker",
            "code": "events_skipped",
            "impact": "Some events were excluded from epoching.",
            "suggested_action": "Review the event mapping and epoch window.",
        }
    )

    assert warning == DiagnosticWarning(
        severity=ValidationSeverity.WARNING,
        source="worker",
        code="events_skipped",
        impact="Some events were excluded from epoching.",
        suggested_action="Review the event mapping and epoch window.",
    )


def test_diagnostic_warning_source_taxonomy_is_closed():
    assert {source.value for source in DiagnosticWarningSource} == {
        "bids",
        "event_mapping",
        "validation",
        "worker",
        "artifact",
        "export_bundle",
        "batch",
    }


def test_diagnostic_warning_deserializes_legacy_source_alias():
    warning = diagnostic_warning_from_dict(
        {
            "severity": "warning",
            "source": "analysis_report",
            "code": "artifact_missing",
        }
    )

    assert warning.source == DiagnosticWarningSource.ARTIFACT


def test_diagnostic_warnings_from_strings_uses_default_warning_contract():
    diagnostics = diagnostic_warnings_from_strings(
        ["Reference unchanged.", ""],
        source="worker",
    )

    assert asdict(diagnostics["warnings"][0]) == {
        "severity": "warning",
        "source": "worker",
        "code": "unstructured_warning",
        "impact": "Reference unchanged.",
        "suggested_action": None,
    }


def test_diagnostic_warnings_from_strings_returns_empty_diagnostics_without_warnings():
    assert diagnostic_warnings_from_strings([], source="epoch") == {}
