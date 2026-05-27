from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any
import hashlib
import json

from eeg_core.domain.recording import RecordingMetadata


MetadataValue = str | int | float | bool | None
Metadata = dict[str, MetadataValue]


class DatasetStatus(StrEnum):
    DRAFT = "draft"
    NEEDS_FILES = "needs_files"
    NEEDS_MAPPING = "needs_mapping"
    VALIDATING = "validating"
    VALID = "valid"
    INVALID = "invalid"


class UploadedFileKind(StrEnum):
    EEG = "eeg"
    EVENTS = "events"
    METADATA = "metadata"


class ValidationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class RunKind(StrEnum):
    PREPROCESSING = "preprocessing"
    EPOCH = "epoch"
    ERP = "erp"


class PreprocessingRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


class EpochRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


class ErpRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


class BatchStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PARTIAL = "partial"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"


class BatchItemStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class EventColumnMapping:
    onset_seconds: str | None = None
    duration_seconds: str | None = None
    trial_type: str | None = None
    stimulus: str | None = None
    response: str | None = None
    correct: str | None = None
    reaction_time_seconds: str | None = None


@dataclass(frozen=True)
class EventRowFilterCondition:
    column: str
    equals: str | None = None


@dataclass(frozen=True)
class EventRowFilter:
    include: list[EventRowFilterCondition] = field(default_factory=list)
    exclude: list[EventRowFilterCondition] = field(default_factory=list)


@dataclass(frozen=True)
class Project:
    project_id: str
    name: str
    description: str | None = None
    metadata: Metadata = field(default_factory=dict)


@dataclass(frozen=True)
class Experiment:
    experiment_id: str
    project_id: str
    name: str
    task_name: str | None = None
    default_event_mapping: EventColumnMapping = field(
        default_factory=EventColumnMapping
    )
    metadata: Metadata = field(default_factory=dict)


@dataclass(frozen=True)
class Participant:
    participant_id: str
    project_id: str
    label: str
    group: str | None = None
    metadata: Metadata = field(default_factory=dict)


@dataclass(frozen=True)
class Session:
    session_id: str
    project_id: str
    experiment_id: str
    participant_id: str
    label: str
    recorded_at_utc: str | None = None
    metadata: Metadata = field(default_factory=dict)


@dataclass(frozen=True)
class UploadedFile:
    file_id: str
    dataset_id: str
    kind: UploadedFileKind
    original_filename: str
    stored_path: str
    content_type: str | None = None
    size_bytes: int | None = None
    checksum_sha256: str | None = None


@dataclass(frozen=True)
class Recording:
    recording_id: str
    dataset_id: str
    file_id: str
    metadata: RecordingMetadata


@dataclass(frozen=True)
class NormalizedEvent:
    onset_seconds: float
    source_row: int
    duration_seconds: float | None = None
    trial_type: str | None = None
    stimulus: str | None = None
    response: str | None = None
    correct: bool | None = None
    reaction_time_seconds: float | None = None


@dataclass(frozen=True)
class EventLog:
    event_log_id: str
    dataset_id: str
    file_id: str
    mapping: EventColumnMapping
    row_count: int
    filter_count: int = 0
    row_filter: EventRowFilter | None = None
    provenance: dict = field(default_factory=dict)
    events: list[NormalizedEvent] = field(default_factory=list)


@dataclass(frozen=True)
class Dataset:
    dataset_id: str
    project_id: str
    experiment_id: str
    participant_id: str
    session_id: str
    status: DatasetStatus = DatasetStatus.DRAFT
    recording_id: str | None = None
    event_log_id: str | None = None
    metadata: Metadata = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationIssue:
    severity: ValidationSeverity
    code: str
    message: str
    field: str | None = None


@dataclass(frozen=True)
class DiagnosticWarning:
    severity: ValidationSeverity
    source: str
    code: str
    impact: str | None = None
    suggested_action: str | None = None


RunDiagnostics = dict[str, list[DiagnosticWarning]]


@dataclass(frozen=True)
class ValidationReport:
    dataset_id: str
    status: DatasetStatus
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return self.status == DatasetStatus.VALID and not self.errors

    @property
    def errors(self) -> list[ValidationIssue]:
        return [
            issue
            for issue in self.issues
            if issue.severity == ValidationSeverity.ERROR
        ]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [
            issue
            for issue in self.issues
            if issue.severity == ValidationSeverity.WARNING
        ]


@dataclass(frozen=True)
class BadChannelDetectionConfig:
    enabled: bool = False
    method: str = "none"
    minimum_correlation: float | None = None
    zscore_threshold: float | None = None


@dataclass(frozen=True)
class BadChannelInterpolationConfig:
    enabled: bool = False
    reset_bads: bool = True


@dataclass(frozen=True)
class IcaConfig:
    enabled: bool = False
    method: str = "fastica"
    n_components: float | int | None = None
    random_state: int = 97
    max_iter: int | str = "auto"
    exclude_components: list[int] = field(default_factory=list)
    eog_channels: list[str] = field(default_factory=list)
    ecg_channels: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ArtifactHandlingConfig:
    eog_enabled: bool = False
    ecg_enabled: bool = False
    eog_channels: list[str] = field(default_factory=list)
    ecg_channels: list[str] = field(default_factory=list)
    create_annotations: bool = True


@dataclass(frozen=True)
class PreprocessingQcConfig:
    enabled: bool = True
    include_before_after: bool = True
    metrics: list[str] = field(
        default_factory=lambda: ["channel_status", "amplitude", "annotations"]
    )


@dataclass(frozen=True)
class PreprocessingConfig:
    artifact_schema_version: int = 1
    high_pass_hz: float | None = None
    low_pass_hz: float | None = None
    notch_hz: float | None = None
    resample_hz: float | None = None
    reference: str | None = None
    manual_bad_channels: list[str] = field(default_factory=list)
    bad_channel_detection: BadChannelDetectionConfig = field(
        default_factory=BadChannelDetectionConfig
    )
    bad_channel_interpolation: BadChannelInterpolationConfig = field(
        default_factory=BadChannelInterpolationConfig
    )
    ica: IcaConfig = field(default_factory=IcaConfig)
    artifact_handling: ArtifactHandlingConfig = field(
        default_factory=ArtifactHandlingConfig
    )
    qc: PreprocessingQcConfig = field(default_factory=PreprocessingQcConfig)


@dataclass(frozen=True)
class EpochConfig:
    preprocessing_run_id: str
    condition_field: str
    tmin_seconds: float
    tmax_seconds: float
    baseline_start_seconds: float | None = None
    baseline_end_seconds: float | None = None
    reject_eeg_uv: float | None = None


@dataclass(frozen=True)
class ErpConfig:
    epoch_run_id: str
    conditions: list[str] | None = None
    picks: list[str] | None = None
    method: str = "mean"
    plot_mode: str = "gfp"
    plot_channel: str | None = None


@dataclass(frozen=True)
class WorkflowTemplateCreatedFrom:
    dataset_id: str | None = None
    preprocessing_run_id: str | None = None
    epoch_run_id: str | None = None
    erp_run_id: str | None = None


@dataclass(frozen=True)
class WorkflowTemplateCompatibility:
    minimum_app_phase: str = "C"
    requires_event_log: bool = True
    requires_completed_preprocessing: bool = False
    requires_completed_epoch: bool = False


@dataclass(frozen=True)
class WorkflowTemplateFieldPolicyEntry:
    path: str
    reason: str
    source_value: Any = None
    source_value_summary: str | None = None
    default_action: str | None = None


@dataclass(frozen=True)
class WorkflowTemplateFieldPolicy:
    excluded_fields: list[WorkflowTemplateFieldPolicyEntry] = field(
        default_factory=list
    )
    review_required_fields: list[WorkflowTemplateFieldPolicyEntry] = field(
        default_factory=list
    )
    channel_specific_fields: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WorkflowTemplateEpochConfig:
    condition_field: str
    tmin_seconds: float
    tmax_seconds: float
    baseline_start_seconds: float | None = None
    baseline_end_seconds: float | None = None
    reject_eeg_uv: float | None = None


@dataclass(frozen=True)
class WorkflowTemplateErpConfig:
    conditions: list[str] | None = None
    picks: list[str] | None = None
    method: str = "mean"
    plot_mode: str = "gfp"
    plot_channel: str | None = None


@dataclass(frozen=True)
class WorkflowTemplateWorkflow:
    preprocessing: PreprocessingConfig | None = None
    epoch: WorkflowTemplateEpochConfig | None = None
    erp: WorkflowTemplateErpConfig | None = None


@dataclass(frozen=True)
class WorkflowTemplateValidation:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stale_reasons: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors

    @property
    def stale(self) -> bool:
        return bool(self.stale_reasons)


@dataclass(frozen=True)
class WorkflowTemplate:
    template_id: str
    name: str
    created_at_utc: str
    updated_at_utc: str
    workflow: WorkflowTemplateWorkflow
    schema_version: int = 1
    template_kind: str = "workflow_template"
    description: str | None = None
    created_from: WorkflowTemplateCreatedFrom = field(
        default_factory=WorkflowTemplateCreatedFrom
    )
    compatibility: WorkflowTemplateCompatibility = field(
        default_factory=WorkflowTemplateCompatibility
    )
    field_policy: WorkflowTemplateFieldPolicy = field(
        default_factory=WorkflowTemplateFieldPolicy
    )
    notes: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BatchDatasetSelection:
    dataset_ids: list[str]
    project_id: str | None = None
    experiment_id: str | None = None


@dataclass(frozen=True)
class BatchRequest:
    template_id: str
    dataset_selection: BatchDatasetSelection
    requested_by: str | None = None
    continue_on_error: bool = True
    dry_run: bool = False
    metadata: Metadata = field(default_factory=dict)


@dataclass(frozen=True)
class BatchTemplateSnapshot:
    template_id: str
    template_name: str
    template_updated_at_utc: str
    captured_at_utc: str
    template_digest_sha256: str
    template: WorkflowTemplate


@dataclass(frozen=True)
class BatchRunBindings:
    preprocessing_run_id: str | None = None
    epoch_run_id: str | None = None
    erp_run_id: str | None = None


@dataclass(frozen=True)
class BatchSubjectRunPlan:
    item_id: str
    dataset_id: str
    status: BatchItemStatus = BatchItemStatus.PENDING
    configs: WorkflowTemplateWorkflow = field(default_factory=WorkflowTemplateWorkflow)
    bindings: BatchRunBindings = field(default_factory=BatchRunBindings)
    planned_steps: list[RunKind] = field(default_factory=list)
    run_ids: dict[str, str] = field(default_factory=dict)
    excluded_fields: list[WorkflowTemplateFieldPolicyEntry] = field(
        default_factory=list
    )
    review_required_fields: list[WorkflowTemplateFieldPolicyEntry] = field(
        default_factory=list
    )
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BatchRunPlanValidation:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class BatchRunPlan:
    batch_id: str
    request: BatchRequest
    template_snapshot: BatchTemplateSnapshot
    items: list[BatchSubjectRunPlan]
    created_at_utc: str
    updated_at_utc: str
    schema_version: int = 1
    status: BatchStatus = BatchStatus.PENDING
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ComparisonConfig:
    erp_run_id: str
    condition_a: str
    condition_b: str
    channel: str | None
    use_gfp: bool
    window_start_seconds: float
    window_end_seconds: float
    metric: str = "mean_amplitude_uv"


@dataclass(frozen=True)
class PreprocessingRun:
    run_id: str
    dataset_id: str
    config: PreprocessingConfig
    run_kind: RunKind = RunKind.PREPROCESSING
    schema_version: int = 1
    status: PreprocessingRunStatus = PreprocessingRunStatus.PENDING
    started_at_utc: str | None = None
    finished_at_utc: str | None = None
    cancel_requested_at_utc: str | None = None
    output_path: str | None = None
    output_metadata: Metadata = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    diagnostics: RunDiagnostics = field(default_factory=dict)


@dataclass(frozen=True)
class EpochRun:
    run_id: str
    dataset_id: str
    config: EpochConfig
    run_kind: RunKind = RunKind.EPOCH
    schema_version: int = 1
    status: EpochRunStatus = EpochRunStatus.PENDING
    started_at_utc: str | None = None
    finished_at_utc: str | None = None
    cancel_requested_at_utc: str | None = None
    output_path: str | None = None
    output_metadata: Metadata = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    diagnostics: RunDiagnostics = field(default_factory=dict)


@dataclass(frozen=True)
class ErpRun:
    run_id: str
    dataset_id: str
    config: ErpConfig
    run_kind: RunKind = RunKind.ERP
    schema_version: int = 1
    status: ErpRunStatus = ErpRunStatus.PENDING
    started_at_utc: str | None = None
    finished_at_utc: str | None = None
    cancel_requested_at_utc: str | None = None
    output_path: str | None = None
    output_metadata: Metadata = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    diagnostics: RunDiagnostics = field(default_factory=dict)


def diagnostic_warning_from_dict(data: dict) -> DiagnosticWarning:
    return DiagnosticWarning(
        severity=ValidationSeverity(data["severity"]),
        source=str(data["source"]),
        code=str(data["code"]),
        impact=data.get("impact"),
        suggested_action=data.get("suggested_action"),
    )


def diagnostic_warnings_from_strings(
    warnings: list[str],
    *,
    source: str,
    code: str = "unstructured_warning",
    severity: ValidationSeverity = ValidationSeverity.WARNING,
    suggested_action: str | None = None,
) -> RunDiagnostics:
    structured_warnings = [
        DiagnosticWarning(
            severity=severity,
            source=source,
            code=code,
            impact=warning,
            suggested_action=suggested_action,
        )
        for warning in warnings
        if warning
    ]
    return {"warnings": structured_warnings} if structured_warnings else {}


SUPPORTED_WORKFLOW_TEMPLATE_SCHEMA_VERSION = 1
WORKFLOW_TEMPLATE_KIND = "workflow_template"
SUPPORTED_BATCH_RUN_PLAN_SCHEMA_VERSION = 1


def validate_workflow_template(
    template: WorkflowTemplate,
) -> WorkflowTemplateValidation:
    errors: list[str] = []
    warnings: list[str] = []
    stale_reasons: list[str] = []

    if template.schema_version != SUPPORTED_WORKFLOW_TEMPLATE_SCHEMA_VERSION:
        errors.append(
            "WorkflowTemplate schema_version is not supported: "
            f"{template.schema_version}"
        )
        stale_reasons.append("unsupported_schema_version")

    if template.template_kind != WORKFLOW_TEMPLATE_KIND:
        errors.append(
            "WorkflowTemplate template_kind must be 'workflow_template'."
        )

    if not template.template_id:
        errors.append("WorkflowTemplate template_id is required.")
    if not template.name:
        errors.append("WorkflowTemplate name is required.")
    if not template.created_at_utc:
        errors.append("WorkflowTemplate created_at_utc is required.")
    if not template.updated_at_utc:
        errors.append("WorkflowTemplate updated_at_utc is required.")

    if (
        template.created_at_utc
        and template.updated_at_utc
        and template.updated_at_utc < template.created_at_utc
    ):
        errors.append("WorkflowTemplate updated_at_utc cannot precede created_at_utc.")

    workflow = template.workflow
    if (
        workflow.preprocessing is None
        and workflow.epoch is None
        and workflow.erp is None
    ):
        errors.append("WorkflowTemplate workflow must configure at least one step.")

    preprocessing = workflow.preprocessing
    if preprocessing is not None:
        if preprocessing.manual_bad_channels:
            errors.append(
                "WorkflowTemplate must not store manual_bad_channels in reusable "
                "preprocessing config."
            )
            stale_reasons.append("subject_specific_manual_bad_channels")
        if preprocessing.ica.exclude_components:
            errors.append(
                "WorkflowTemplate must not store ica.exclude_components in reusable "
                "preprocessing config."
            )
            stale_reasons.append("subject_specific_ica_exclusions")
        _require_channel_review(
            "workflow.preprocessing.ica.eog_channels",
            preprocessing.ica.eog_channels,
            template.field_policy,
            warnings,
            stale_reasons,
        )
        _require_channel_review(
            "workflow.preprocessing.ica.ecg_channels",
            preprocessing.ica.ecg_channels,
            template.field_policy,
            warnings,
            stale_reasons,
        )
        _require_channel_review(
            "workflow.preprocessing.artifact_handling.eog_channels",
            preprocessing.artifact_handling.eog_channels,
            template.field_policy,
            warnings,
            stale_reasons,
        )
        _require_channel_review(
            "workflow.preprocessing.artifact_handling.ecg_channels",
            preprocessing.artifact_handling.ecg_channels,
            template.field_policy,
            warnings,
            stale_reasons,
        )

    erp = workflow.erp
    if erp is not None:
        _require_channel_review(
            "workflow.erp.picks",
            erp.picks or [],
            template.field_policy,
            warnings,
            stale_reasons,
        )
        _require_channel_review(
            "workflow.erp.plot_channel",
            [erp.plot_channel] if erp.plot_channel else [],
            template.field_policy,
            warnings,
            stale_reasons,
        )

    return WorkflowTemplateValidation(
        errors=_unique_strings(errors),
        warnings=_unique_strings(warnings),
        stale_reasons=_unique_strings(stale_reasons),
    )


def _require_channel_review(
    path: str,
    values: list[str],
    field_policy: WorkflowTemplateFieldPolicy,
    warnings: list[str],
    stale_reasons: list[str],
) -> None:
    if not values:
        return

    review_paths = {
        entry.path for entry in field_policy.review_required_fields
    }
    channel_paths = set(field_policy.channel_specific_fields)
    if path in review_paths or path in channel_paths:
        return

    warnings.append(f"{path} should be marked as review_required before use.")
    stale_reasons.append(f"channel_specific_without_review:{path}")


def _unique_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def create_batch_template_snapshot(
    template: WorkflowTemplate,
    *,
    captured_at_utc: str,
) -> BatchTemplateSnapshot:
    return BatchTemplateSnapshot(
        template_id=template.template_id,
        template_name=template.name,
        template_updated_at_utc=template.updated_at_utc,
        captured_at_utc=captured_at_utc,
        template_digest_sha256=workflow_template_digest_sha256(template),
        template=template,
    )


def workflow_template_digest_sha256(template: WorkflowTemplate) -> str:
    payload = json.dumps(
        asdict(template),
        default=str,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_batch_request(request: BatchRequest) -> BatchRunPlanValidation:
    errors: list[str] = []
    warnings: list[str] = []

    if not request.template_id:
        errors.append("BatchRequest template_id is required.")

    dataset_ids = request.dataset_selection.dataset_ids
    if not dataset_ids:
        errors.append("BatchRequest dataset_selection.dataset_ids must not be empty.")

    if any(not dataset_id for dataset_id in dataset_ids):
        errors.append("BatchRequest dataset ids must be non-empty strings.")

    if len(dataset_ids) != len(set(dataset_ids)):
        errors.append("BatchRequest dataset_selection.dataset_ids must be unique.")

    if request.dry_run:
        warnings.append("BatchRequest dry_run does not create runnable batch items.")

    return BatchRunPlanValidation(
        errors=_unique_strings(errors),
        warnings=_unique_strings(warnings),
    )


def validate_batch_run_plan(plan: BatchRunPlan) -> BatchRunPlanValidation:
    errors: list[str] = []
    warnings: list[str] = []

    if plan.schema_version != SUPPORTED_BATCH_RUN_PLAN_SCHEMA_VERSION:
        errors.append(
            "BatchRunPlan schema_version is not supported: "
            f"{plan.schema_version}"
        )

    if not plan.batch_id:
        errors.append("BatchRunPlan batch_id is required.")

    if not plan.created_at_utc:
        errors.append("BatchRunPlan created_at_utc is required.")
    if not plan.updated_at_utc:
        errors.append("BatchRunPlan updated_at_utc is required.")
    if (
        plan.created_at_utc
        and plan.updated_at_utc
        and plan.updated_at_utc < plan.created_at_utc
    ):
        errors.append("BatchRunPlan updated_at_utc cannot precede created_at_utc.")

    request_validation = validate_batch_request(plan.request)
    errors.extend(request_validation.errors)
    warnings.extend(request_validation.warnings)

    if plan.template_snapshot.template_id != plan.request.template_id:
        errors.append("BatchRunPlan template snapshot must match request template_id.")

    expected_digest = workflow_template_digest_sha256(plan.template_snapshot.template)
    if plan.template_snapshot.template_digest_sha256 != expected_digest:
        errors.append("BatchRunPlan template snapshot digest does not match template.")

    template_validation = validate_workflow_template(plan.template_snapshot.template)
    errors.extend(
        f"BatchRunPlan template snapshot invalid: {error}"
        for error in template_validation.errors
    )
    warnings.extend(
        f"BatchRunPlan template snapshot warning: {warning}"
        for warning in template_validation.warnings
    )

    item_dataset_ids = [item.dataset_id for item in plan.items]
    selected_dataset_ids = plan.request.dataset_selection.dataset_ids
    if item_dataset_ids != selected_dataset_ids:
        errors.append(
            "BatchRunPlan items must match dataset_selection.dataset_ids order."
        )

    if len({item.item_id for item in plan.items}) != len(plan.items):
        errors.append("BatchRunPlan item_id values must be unique.")

    if plan.status == BatchStatus.PARTIAL:
        has_completed = any(
            item.status == BatchItemStatus.COMPLETED for item in plan.items
        )
        has_failed = any(item.status == BatchItemStatus.FAILED for item in plan.items)
        if not (has_completed and has_failed):
            errors.append(
                "BatchRunPlan partial status requires at least one completed and "
                "one failed item."
            )

    if plan.status == BatchStatus.COMPLETED and any(
        item.status != BatchItemStatus.COMPLETED for item in plan.items
    ):
        errors.append("BatchRunPlan completed status requires all items completed.")

    if plan.status == BatchStatus.FAILED and any(
        item.status == BatchItemStatus.COMPLETED for item in plan.items
    ):
        warnings.append(
            "BatchRunPlan failed status has completed items; partial may be more precise."
        )

    return BatchRunPlanValidation(
        errors=_unique_strings(errors),
        warnings=_unique_strings(warnings),
    )
