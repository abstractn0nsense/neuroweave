from dataclasses import dataclass, field
from enum import StrEnum

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
class PreprocessingConfig:
    high_pass_hz: float | None = None
    low_pass_hz: float | None = None
    notch_hz: float | None = None
    resample_hz: float | None = None
    reference: str | None = None


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
