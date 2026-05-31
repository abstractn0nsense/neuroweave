from pathlib import Path
from queue import Queue
from threading import Lock, Thread
from dataclasses import asdict, replace
from datetime import UTC, datetime
from contextlib import asynccontextmanager
from typing import Any, Literal
import hashlib
import json
import os
import shutil
import subprocess
import sys
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


if getattr(sys, "frozen", False):
    REPO_ROOT = Path(os.environ.get("NEUROWEAVE_APP_ROOT", Path(sys.executable).parent)).resolve()
else:
    REPO_ROOT = Path(__file__).resolve().parents[2]
for package_src in (
    "packages/eeg-core/src",
    "packages/eeg-io/src",
    "packages/eeg-processing/src",
):
    sys.path.insert(0, str(REPO_ROOT / package_src))

from eeg_core.domain import (  # noqa: E402
    ArtifactHandlingConfig,
    BadChannelDetectionConfig,
    BadChannelInterpolationConfig,
    BatchDatasetSelection,
    BatchItemStatus,
    BatchApplyPreviewResult,
    BatchPlanningError,
    BatchRequest,
    BatchRunBindings,
    BatchRunPlan,
    BatchStatus,
    BatchSubjectRunPlan,
    BatchTemplateSnapshot,
    ChannelMetadata,
    ComparisonConfig,
    ComparisonObservation,
    Dataset as IngestionDataset,
    DatasetStatus,
    EpochConfig,
    EpochRun,
    EpochRunStatus,
    ErpConfig,
    ErpRun,
    ErpRunStatus,
    EventColumnMapping,
    EventLog,
    EventRowFilter,
    EventRowFilterCondition,
    Experiment,
    Participant,
    IcaConfig,
    PreprocessingConfig,
    PreprocessingQcConfig,
    PreprocessingRun,
    PreprocessingRunStatus,
    Project,
    Recording,
    RecordingMetadata,
    RunKind,
    SourceFileMetadata,
    UploadedFile as IngestionUploadedFile,
    UploadedFileKind,
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
    WorkflowTemplate,
    WorkflowTemplateCompatibility,
    WorkflowTemplateCreatedFrom,
    WorkflowTemplateEpochConfig,
    WorkflowTemplateErpConfig,
    WorkflowTemplateFieldPolicy,
    WorkflowTemplateFieldPolicyEntry,
    WorkflowTemplateWorkflow,
    diagnostic_warning_source_from_value,
    diagnostic_warnings_from_strings,
    plan_batch_run,
    validate_ingestion_dataset,
    validate_batch_request,
    validate_workflow_template,
)
from eeg_processing import (  # noqa: E402
    ComparisonError,
    EpochingError,
    ErpError,
    PreprocessingError,
    generate_comparison_summary,
)
from eeg_processing.epoching import SUPPORTED_CONDITION_FIELDS  # noqa: E402
from eeg_io.bids_sidecars import (  # noqa: E402
    BidsSidecarDiscovery,
    BidsSidecarError,
    discover_bids_sidecars,
    read_channels_tsv,
    read_eeg_json,
)
from eeg_io.analysis_report import AnalysisReportError, write_analysis_report  # noqa: E402
from eeg_io.artifact_manifest import (  # noqa: E402
    ArtifactManifestError,
    check_artifact_integrity,
)
from eeg_io.datasets import find_eeg_file_by_id, list_eeg_files  # noqa: E402
from eeg_io.event_logs import (  # noqa: E402
    EventLogNormalizationError,
    EventLogPreviewError,
    event_mapping_preset,
    normalize_event_log,
    preview_event_log,
)
from eeg_io.export_bundle import build_export_bundle  # noqa: E402
from eeg_io.provenance import (  # noqa: E402
    build_event_log_provenance_payload,
    build_provenance_payload,
)
from eeg_io.qc_summary import QcSummaryError, build_qc_summary  # noqa: E402
from eeg_io.registry import (  # noqa: E402
    JsonRegistryError,
    JsonBatchRepository,
    JsonRegistryRepository,
    JsonRunRepository,
    JsonWorkflowTemplateRepository,
)
from eeg_io.readers import EegMetadataReadError, read_eeg_metadata  # noqa: E402


RAW_PREPROCESSED_FILENAME = "raw_preprocessed_raw.fif"
LEGACY_RAW_PREPROCESSED_FILENAME = "raw_preprocessed.fif"
EPOCHS_FILENAME = "epochs-epo.fif"
LEGACY_EPOCHS_FILENAME = "epochs.fif"


def _path_from_env(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    if not value:
        return default
    return Path(value).expanduser().resolve()


DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]
LOCALHOST_CORS_REGEX = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"


def _cors_origins_from_env() -> list[str]:
    value = os.environ.get("NEUROWEAVE_CORS_ORIGINS")
    if value is None:
        return DEFAULT_CORS_ORIGINS
    origins = [origin.strip() for origin in value.split(",") if origin.strip()]
    return origins or DEFAULT_CORS_ORIGINS


def _cors_allow_origin_regex_from_env() -> str | None:
    value = os.environ.get("NEUROWEAVE_CORS_ALLOW_LOCALHOST_PORTS", "")
    if value.strip().lower() in {"1", "true", "yes", "y", "on"}:
        return LOCALHOST_CORS_REGEX
    return None


def _preprocessing_output_path(dataset_id: str, run_id: str) -> Path:
    return PROCESSED_DIR / dataset_id / run_id / RAW_PREPROCESSED_FILENAME


def _epoch_output_directory(dataset_id: str, run_id: str) -> Path:
    return EPOCHS_DIR / dataset_id / run_id


def _epoch_output_path(dataset_id: str, run_id: str) -> Path:
    return _epoch_output_directory(dataset_id, run_id) / EPOCHS_FILENAME


def _erp_output_directory(dataset_id: str, run_id: str) -> Path:
    return ERP_DIR / dataset_id / run_id


def _erp_metadata_path(dataset_id: str, run_id: str) -> Path:
    return _erp_output_directory(dataset_id, run_id) / "erp_metadata.json"


SAMPLE_DATASET_DIR = _path_from_env(
    "NEUROWEAVE_SAMPLE_DATASET_DIR",
    REPO_ROOT / "data" / "raw" / "samples",
)
UPLOADS_DIR = _path_from_env(
    "NEUROWEAVE_UPLOADS_DIR",
    REPO_ROOT / "data" / "raw" / "uploads",
)
RUNS_DIR = _path_from_env("NEUROWEAVE_RUNS_DIR", REPO_ROOT / "data" / "runs")
TEMPLATES_DIR = _path_from_env(
    "NEUROWEAVE_TEMPLATES_DIR",
    REPO_ROOT / "data" / "templates",
)
BATCHES_DIR = _path_from_env(
    "NEUROWEAVE_BATCHES_DIR",
    REPO_ROOT / "data" / "batches",
)
PROCESSED_DIR = _path_from_env(
    "NEUROWEAVE_PROCESSED_DIR",
    REPO_ROOT / "data" / "processed",
)
EPOCHS_DIR = _path_from_env("NEUROWEAVE_EPOCHS_DIR", REPO_ROOT / "data" / "epochs")
ERP_DIR = _path_from_env("NEUROWEAVE_ERP_DIR", REPO_ROOT / "data" / "erp")
registry_repository = JsonRegistryRepository(UPLOADS_DIR)
run_repository = JsonRunRepository(RUNS_DIR)
template_repository = JsonWorkflowTemplateRepository(TEMPLATES_DIR)
batch_repository = JsonBatchRepository(BATCHES_DIR)


class WorkerSubprocessError(PreprocessingError):
    def __init__(
        self,
        message: str,
        *,
        worker_exit_code: int | None,
        processing_warnings: list[str] | None = None,
    ):
        super().__init__(message, processing_warnings=processing_warnings)
        self.worker_exit_code = worker_exit_code


class EpochWorkerSubprocessError(EpochingError):
    def __init__(
        self,
        message: str,
        *,
        worker_exit_code: int | None,
        processing_warnings: list[str] | None = None,
    ):
        super().__init__(message, processing_warnings=processing_warnings)
        self.worker_exit_code = worker_exit_code


class ErpWorkerSubprocessError(ErpError):
    def __init__(
        self,
        message: str,
        *,
        worker_exit_code: int | None,
        processing_warnings: list[str] | None = None,
    ):
        super().__init__(message, processing_warnings=processing_warnings)
        self.worker_exit_code = worker_exit_code


class LocalPreprocessingWorker:
    def __init__(self) -> None:
        self._queue: Queue[str] = Queue()
        self._queued_run_ids: set[str] = set()
        self._lock = Lock()
        self._thread: Thread | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = Thread(
                target=self._run_loop,
                name="neuroweave-preprocessing-worker",
                daemon=True,
            )
            self._thread.start()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def enqueue(self, run_id: str) -> None:
        self.start()
        with self._lock:
            if run_id in self._queued_run_ids:
                return
            self._queued_run_ids.add(run_id)
            self._queue.put(run_id)

    def recover(self) -> None:
        for run in run_repository.list_preprocessing_runs():
            if run.status in {
                PreprocessingRunStatus.PENDING,
                PreprocessingRunStatus.RUNNING,
            }:
                self.enqueue(run.run_id)

    def _run_loop(self) -> None:
        while True:
            run_id = self._queue.get()
            try:
                _execute_preprocessing_run(run_id)
            finally:
                with self._lock:
                    self._queued_run_ids.discard(run_id)
                self._queue.task_done()


preprocessing_worker = LocalPreprocessingWorker()


class LocalEpochWorker:
    def __init__(self) -> None:
        self._queue: Queue[str] = Queue()
        self._queued_run_ids: set[str] = set()
        self._lock = Lock()
        self._thread: Thread | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = Thread(
                target=self._run_loop,
                name="neuroweave-epoch-worker",
                daemon=True,
            )
            self._thread.start()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def enqueue(self, run_id: str) -> None:
        self.start()
        with self._lock:
            if run_id in self._queued_run_ids:
                return
            self._queued_run_ids.add(run_id)
            self._queue.put(run_id)

    def recover(self) -> None:
        for run in run_repository.list_epoch_runs():
            if run.status in {
                EpochRunStatus.PENDING,
                EpochRunStatus.RUNNING,
            }:
                self.enqueue(run.run_id)

    def _run_loop(self) -> None:
        while True:
            run_id = self._queue.get()
            try:
                _execute_epoch_run(run_id)
            finally:
                with self._lock:
                    self._queued_run_ids.discard(run_id)
                self._queue.task_done()


epoch_worker = LocalEpochWorker()


class LocalErpWorker:
    def __init__(self) -> None:
        self._queue: Queue[str] = Queue()
        self._queued_run_ids: set[str] = set()
        self._lock = Lock()
        self._thread: Thread | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = Thread(
                target=self._run_loop,
                name="neuroweave-erp-worker",
                daemon=True,
            )
            self._thread.start()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def enqueue(self, run_id: str) -> None:
        self.start()
        with self._lock:
            if run_id in self._queued_run_ids:
                return
            self._queued_run_ids.add(run_id)
            self._queue.put(run_id)

    def recover(self) -> None:
        for run in run_repository.list_erp_runs():
            if run.status in {
                ErpRunStatus.PENDING,
                ErpRunStatus.RUNNING,
            }:
                self.enqueue(run.run_id)

    def _run_loop(self) -> None:
        while True:
            run_id = self._queue.get()
            try:
                _execute_erp_run(run_id)
            finally:
                with self._lock:
                    self._queued_run_ids.discard(run_id)
                self._queue.task_done()


erp_worker = LocalErpWorker()


class LocalBatchWorker:
    def __init__(self) -> None:
        self._queue: Queue[str] = Queue()
        self._queued_batch_ids: set[str] = set()
        self._lock = Lock()
        self._thread: Thread | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = Thread(
                target=self._run_loop,
                name="neuroweave-batch-worker",
                daemon=True,
            )
            self._thread.start()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def enqueue(self, batch_id: str) -> None:
        self.start()
        with self._lock:
            if batch_id in self._queued_batch_ids:
                return
            self._queued_batch_ids.add(batch_id)
            self._queue.put(batch_id)

    def recover(self) -> None:
        for batch in batch_repository.list_batches():
            if batch.status in {
                BatchStatus.PENDING,
                BatchStatus.RUNNING,
                BatchStatus.CANCELLING,
            }:
                self.enqueue(batch.batch_id)

    def _run_loop(self) -> None:
        while True:
            batch_id = self._queue.get()
            try:
                _execute_batch_run(batch_id)
            finally:
                with self._lock:
                    self._queued_batch_ids.discard(batch_id)
                self._queue.task_done()


batch_worker = LocalBatchWorker()


class HealthResponse(BaseModel):
    status: str
    service: str
    workers: dict[str, bool] = Field(default_factory=dict)
    data_directories: dict[str, str] = Field(default_factory=dict)


class SampleDataset(BaseModel):
    id: str
    filename: str
    format: str


class SampleDatasetsResponse(BaseModel):
    samples: list[SampleDataset]


class ChannelMetadataPayload(BaseModel):
    name: str
    type: str | None = None
    units: str | None = None
    status: str | None = None
    status_description: str | None = None


class SourceFileMetadataPayload(BaseModel):
    role: str
    original_filename: str
    stored_path: str
    size_bytes: int | None = None
    checksum_sha256: str | None = None
    content_type: str | None = None
    sidecar_type: str | None = None
    status: str | None = None
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)


class DatasetMetadata(BaseModel):
    id: str
    format: str
    channels: int
    sampling_rate: float
    duration_seconds: float
    channel_names: list[str]
    channel_details: list[ChannelMetadataPayload] = Field(default_factory=list)
    line_frequency_hz: float | None = None
    reference: str | None = None
    source_files: list[SourceFileMetadataPayload] = Field(default_factory=list)
    sidecar_discovery: dict[str, Any] = Field(default_factory=dict)


class CreateDatasetRequest(BaseModel):
    dataset_id: str | None = None
    project_id: str
    experiment_id: str
    participant_id: str | None = None
    participant_label: str
    participant_group: str | None = None
    session_id: str | None = None
    session_label: str
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class DatasetResponse(BaseModel):
    dataset_id: str
    project_id: str
    experiment_id: str
    participant_id: str
    session_id: str
    status: str
    recording_id: str | None
    event_log_id: str | None
    metadata: dict[str, str | int | float | bool | None]


class DatasetsResponse(BaseModel):
    datasets: list[DatasetResponse]


class DatasetLocalDataDeletionResponse(BaseModel):
    dataset_id: str
    dry_run: bool
    deleted: bool
    deleted_paths: list[str] = Field(default_factory=list)
    run_ids: dict[str, list[str]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class UploadedFileResponse(BaseModel):
    file_id: str
    dataset_id: str
    kind: str
    original_filename: str
    stored_path: str
    content_type: str | None
    size_bytes: int | None
    checksum_sha256: str | None


class BidsSidecarDiagnosticResponse(BaseModel):
    severity: str
    source: str
    code: str
    impact: str | None
    suggested_action: str | None


class BidsSidecarCandidateResponse(BaseModel):
    sidecar_type: str
    path: str
    status: str
    diagnostics: list[BidsSidecarDiagnosticResponse] = Field(default_factory=list)


class BidsSidecarDiscoveryResponse(BaseModel):
    schema_version: int
    reference_path: str
    bids_basename: str
    candidates: list[BidsSidecarCandidateResponse] = Field(default_factory=list)
    diagnostics: list[BidsSidecarDiagnosticResponse] = Field(default_factory=list)


class RecordingResponse(BaseModel):
    recording_id: str
    dataset_id: str
    file_id: str
    metadata: DatasetMetadata


class EegUploadResponse(BaseModel):
    dataset: DatasetResponse
    uploaded_file: UploadedFileResponse
    recording: RecordingResponse
    sidecar_discovery: BidsSidecarDiscoveryResponse | None = None
    sidecar_files: list[UploadedFileResponse] = Field(default_factory=list)


class SidecarUploadResponse(BaseModel):
    dataset: DatasetResponse
    uploaded_file: UploadedFileResponse
    recording: RecordingResponse


class EventLogPreviewResponse(BaseModel):
    columns: list[str]
    delimiter: str
    preview_rows: list[dict[str, str | None]]
    row_count: int


class EventUploadResponse(BaseModel):
    dataset: DatasetResponse
    uploaded_file: UploadedFileResponse
    preview: EventLogPreviewResponse
    sidecar_discovery: BidsSidecarDiscoveryResponse | None = None
    sidecar_files: list[UploadedFileResponse] = Field(default_factory=list)


class EventColumnMappingPayload(BaseModel):
    onset_seconds: str | None = None
    duration_seconds: str | None = None
    trial_type: str | None = None
    stimulus: str | None = None
    response: str | None = None
    correct: str | None = None
    reaction_time_seconds: str | None = None


class NormalizedEventResponse(BaseModel):
    onset_seconds: float
    source_row: int
    duration_seconds: float | None
    trial_type: str | None
    stimulus: str | None
    response: str | None
    correct: bool | None
    reaction_time_seconds: float | None
    source_columns: dict[str, str | None] = Field(default_factory=dict)


class EventLogResponse(BaseModel):
    event_log_id: str
    dataset_id: str
    file_id: str
    mapping: EventColumnMappingPayload
    row_count: int
    filter_count: int
    condition_column: str | None = None
    events: list[NormalizedEventResponse]


class EventRowFilterConditionPayload(BaseModel):
    column: str
    equals: str | None = None


class EventRowFilterPayload(BaseModel):
    include: list[EventRowFilterConditionPayload] = Field(default_factory=list)
    exclude: list[EventRowFilterConditionPayload] = Field(default_factory=list)


class ValidationIssueResponse(BaseModel):
    severity: str
    code: str
    message: str
    field: str | None


class ValidationReportResponse(BaseModel):
    dataset_id: str
    status: str
    valid: bool
    errors: list[ValidationIssueResponse]
    warnings: list[ValidationIssueResponse]
    issues: list[ValidationIssueResponse]


class EventMappingRequest(BaseModel):
    mapping: EventColumnMappingPayload | None = None
    preset: Literal["psychopy", "bids_events", "eeglab_annotations"] | None = None
    row_filter: EventRowFilterPayload | None = None
    condition_column: str | None = None


class BadChannelDetectionConfigPayload(BaseModel):
    enabled: bool = False
    method: Literal["none", "flat", "deviation", "ransac"] = "none"
    minimum_correlation: float | None = Field(default=None, ge=0, le=1)
    zscore_threshold: float | None = Field(default=None, gt=0)


class BadChannelInterpolationConfigPayload(BaseModel):
    enabled: bool = False
    reset_bads: bool = True


class IcaConfigPayload(BaseModel):
    enabled: bool = False
    method: Literal["fastica", "infomax", "picard"] = "fastica"
    n_components: int | float | None = Field(default=None, gt=0)
    random_state: int = 97
    max_iter: int | Literal["auto"] = "auto"
    exclude_components: list[int] = Field(default_factory=list)
    eog_channels: list[str] = Field(default_factory=list)
    ecg_channels: list[str] = Field(default_factory=list)


class ArtifactHandlingConfigPayload(BaseModel):
    eog_enabled: bool = False
    ecg_enabled: bool = False
    eog_channels: list[str] = Field(default_factory=list)
    ecg_channels: list[str] = Field(default_factory=list)
    create_annotations: bool = True


class PreprocessingQcConfigPayload(BaseModel):
    enabled: bool = True
    include_before_after: bool = True
    metrics: list[
        Literal["channel_status", "amplitude", "annotations", "psd", "ica"]
    ] = Field(default_factory=lambda: ["channel_status", "amplitude", "annotations"])


class PreprocessingConfigPayload(BaseModel):
    artifact_schema_version: int = Field(default=1, ge=1)
    high_pass_hz: float | None = Field(default=None, ge=0)
    low_pass_hz: float | None = Field(default=None, gt=0)
    notch_hz: float | None = Field(default=None, gt=0)
    resample_hz: float | None = Field(default=None, gt=0)
    reference: str | None = None
    manual_bad_channels: list[str] = Field(default_factory=list)
    bad_channel_detection: BadChannelDetectionConfigPayload = Field(
        default_factory=BadChannelDetectionConfigPayload
    )
    bad_channel_interpolation: BadChannelInterpolationConfigPayload = Field(
        default_factory=BadChannelInterpolationConfigPayload
    )
    ica: IcaConfigPayload = Field(default_factory=IcaConfigPayload)
    artifact_handling: ArtifactHandlingConfigPayload = Field(
        default_factory=ArtifactHandlingConfigPayload
    )
    qc: PreprocessingQcConfigPayload = Field(default_factory=PreprocessingQcConfigPayload)


class DiagnosticWarningResponse(BaseModel):
    severity: str
    source: str
    code: str
    impact: str | None
    suggested_action: str | None


class RunDiagnosticsResponse(BaseModel):
    warnings: list[DiagnosticWarningResponse] = Field(default_factory=list)


class PreprocessingRunResponse(BaseModel):
    run_id: str
    dataset_id: str
    run_kind: str
    schema_version: int
    config: PreprocessingConfigPayload
    status: str
    started_at_utc: str | None
    finished_at_utc: str | None
    cancel_requested_at_utc: str | None
    output_path: str | None
    output_metadata: dict[str, str | int | float | bool | None]
    warnings: list[str]
    diagnostics: RunDiagnosticsResponse | dict
    errors: list[str]


class PreprocessingRunsResponse(BaseModel):
    runs: list[PreprocessingRunResponse]


class EpochConfigPayload(BaseModel):
    preprocessing_run_id: str
    condition_field: str
    tmin_seconds: float
    tmax_seconds: float
    baseline_start_seconds: float | None = None
    baseline_end_seconds: float | None = None
    reject_eeg_uv: float | None = None


class EpochRunResponse(BaseModel):
    run_id: str
    dataset_id: str
    run_kind: str
    schema_version: int
    config: EpochConfigPayload
    status: str
    started_at_utc: str | None
    finished_at_utc: str | None
    cancel_requested_at_utc: str | None
    output_path: str | None
    output_metadata: dict[str, str | int | float | bool | None]
    warnings: list[str]
    diagnostics: RunDiagnosticsResponse | dict
    errors: list[str]


class EpochRunsResponse(BaseModel):
    runs: list[EpochRunResponse]


class ErpConfigPayload(BaseModel):
    epoch_run_id: str
    conditions: list[str] | None = None
    picks: list[str] | None = None
    method: str = "mean"
    plot_mode: str = "gfp"
    plot_channel: str | None = None


class ErpRunResponse(BaseModel):
    run_id: str
    dataset_id: str
    run_kind: str
    schema_version: int
    config: ErpConfigPayload
    status: str
    started_at_utc: str | None
    finished_at_utc: str | None
    cancel_requested_at_utc: str | None
    output_path: str | None
    output_metadata: dict[str, str | int | float | bool | None]
    warnings: list[str]
    diagnostics: RunDiagnosticsResponse | dict
    errors: list[str]


class ErpRunsResponse(BaseModel):
    runs: list[ErpRunResponse]


class WorkflowTemplateCreatedFromPayload(BaseModel):
    dataset_id: str | None = None
    preprocessing_run_id: str | None = None
    epoch_run_id: str | None = None
    erp_run_id: str | None = None


class WorkflowTemplateCompatibilityPayload(BaseModel):
    minimum_app_phase: str = "C"
    requires_event_log: bool = True
    requires_completed_preprocessing: bool = False
    requires_completed_epoch: bool = False


class WorkflowTemplateFieldPolicyEntryPayload(BaseModel):
    path: str
    reason: str
    source_value: Any = None
    source_value_summary: str | None = None
    default_action: str | None = None


class WorkflowTemplateFieldPolicyPayload(BaseModel):
    excluded_fields: list[WorkflowTemplateFieldPolicyEntryPayload] = Field(
        default_factory=list
    )
    review_required_fields: list[WorkflowTemplateFieldPolicyEntryPayload] = Field(
        default_factory=list
    )
    channel_specific_fields: list[str] = Field(default_factory=list)


class WorkflowTemplateEpochConfigPayload(BaseModel):
    condition_field: str = "trial_type"
    tmin_seconds: float = -0.2
    tmax_seconds: float = 0.8
    baseline_start_seconds: float | None = None
    baseline_end_seconds: float | None = None
    reject_eeg_uv: float | None = None


class WorkflowTemplateErpConfigPayload(BaseModel):
    conditions: list[str] | None = None
    picks: list[str] | None = None
    method: str = "mean"
    plot_mode: str = "gfp"
    plot_channel: str | None = None


class WorkflowTemplateWorkflowPayload(BaseModel):
    preprocessing: PreprocessingConfigPayload | None = None
    epoch: WorkflowTemplateEpochConfigPayload | None = None
    erp: WorkflowTemplateErpConfigPayload | None = None


class WorkflowTemplateValidationResponse(BaseModel):
    valid: bool
    stale: bool
    errors: list[str]
    warnings: list[str]
    stale_reasons: list[str]


class WorkflowTemplateSaveRequest(BaseModel):
    template_id: str | None = None
    name: str
    description: str | None = None
    created_from: WorkflowTemplateCreatedFromPayload = Field(
        default_factory=WorkflowTemplateCreatedFromPayload
    )
    compatibility: WorkflowTemplateCompatibilityPayload = Field(
        default_factory=WorkflowTemplateCompatibilityPayload
    )
    workflow: WorkflowTemplateWorkflowPayload
    field_policy: WorkflowTemplateFieldPolicyPayload = Field(
        default_factory=WorkflowTemplateFieldPolicyPayload
    )
    notes: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class WorkflowTemplateResponse(BaseModel):
    schema_version: int
    template_kind: str
    template_id: str
    name: str
    description: str | None
    created_at_utc: str
    updated_at_utc: str
    created_from: WorkflowTemplateCreatedFromPayload
    compatibility: WorkflowTemplateCompatibilityPayload
    workflow: WorkflowTemplateWorkflowPayload
    field_policy: WorkflowTemplateFieldPolicyPayload
    notes: list[str]
    extra: dict[str, Any]
    validation: WorkflowTemplateValidationResponse


class WorkflowTemplatesResponse(BaseModel):
    templates: list[WorkflowTemplateResponse]


class WorkflowTemplateFromRunRequest(BaseModel):
    template_id: str | None = None
    name: str
    description: str | None = None
    preprocessing_run_id: str | None = None
    epoch_run_id: str | None = None
    erp_run_id: str | None = None
    notes: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class WorkflowTemplateSubjectOverridesPayload(BaseModel):
    manual_bad_channels: list[str] = Field(default_factory=list)
    ica_exclude_components: list[int] = Field(default_factory=list)


class WorkflowTemplateApplyPreviewRequest(BaseModel):
    target_dataset_id: str
    preprocessing_run_id: str | None = None
    epoch_run_id: str | None = None
    subject_overrides: WorkflowTemplateSubjectOverridesPayload = Field(
        default_factory=WorkflowTemplateSubjectOverridesPayload
    )


class WorkflowTemplateApplyPreviewResponse(BaseModel):
    template_id: str
    target_dataset_id: str
    status: Literal["ready", "requires_review", "invalid"]
    configs: WorkflowTemplateWorkflowPayload
    excluded_fields: list[WorkflowTemplateFieldPolicyEntryPayload]
    review_required_fields: list[WorkflowTemplateFieldPolicyEntryPayload]
    errors: list[str]
    warnings: list[str]


class BatchDatasetSelectionPayload(BaseModel):
    dataset_ids: list[str]
    project_id: str | None = None
    experiment_id: str | None = None


class BatchCreateRequest(BaseModel):
    template_id: str
    dataset_selection: BatchDatasetSelectionPayload
    requested_by: str | None = None
    continue_on_error: bool = True
    dry_run: bool = False
    metadata: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict
    )


class BatchRequestPayload(BaseModel):
    template_id: str
    dataset_selection: BatchDatasetSelectionPayload
    requested_by: str | None
    continue_on_error: bool
    dry_run: bool
    metadata: dict[str, str | int | float | bool | None]


class BatchRunBindingsPayload(BaseModel):
    preprocessing_run_id: str | None = None
    epoch_run_id: str | None = None
    erp_run_id: str | None = None


class BatchTemplateSnapshotPayload(BaseModel):
    template_id: str
    template_name: str
    template_updated_at_utc: str
    captured_at_utc: str
    template_digest_sha256: str
    template: WorkflowTemplateResponse


class BatchSubjectRunPlanPayload(BaseModel):
    item_id: str
    dataset_id: str
    status: str
    attempt: int
    retry_of_item_id: str | None
    configs: WorkflowTemplateWorkflowPayload
    bindings: BatchRunBindingsPayload
    planned_steps: list[str]
    run_ids: dict[str, str]
    previous_run_ids: dict[str, str]
    previous_error: str | None
    excluded_fields: list[WorkflowTemplateFieldPolicyEntryPayload]
    review_required_fields: list[WorkflowTemplateFieldPolicyEntryPayload]
    warnings: list[str]
    errors: list[str]


class BatchRunPlanResponse(BaseModel):
    schema_version: int
    batch_id: str
    status: str
    created_at_utc: str
    updated_at_utc: str
    request: BatchRequestPayload
    template_snapshot: BatchTemplateSnapshotPayload
    items: list[BatchSubjectRunPlanPayload]
    warnings: list[str]
    errors: list[str]


class BatchRunsResponse(BaseModel):
    batches: list[BatchRunPlanResponse]


BATCH_SUMMARY_SCHEMA_VERSION = 1


class QcSummaryResponse(BaseModel):
    dataset_id: str
    run_id: str
    run_kind: str
    summary: dict


class ArtifactIntegrityResponse(BaseModel):
    run_id: str
    dataset_id: str
    run_kind: str
    integrity: dict


class RerunPlanResponse(BaseModel):
    run_id: str
    dataset_id: str
    run_kind: str
    plan: dict


class ComparisonObservationPayload(BaseModel):
    subject_id: str
    condition_a_mean_amplitude_uv: float
    condition_b_mean_amplitude_uv: float


class ComparisonConfigPayload(BaseModel):
    condition_a: str
    condition_b: str
    channel: str | None = None
    use_gfp: bool = True
    window_start_seconds: float
    window_end_seconds: float
    metric: str = "mean_amplitude_uv"
    paired_observations: list[ComparisonObservationPayload] = Field(
        default_factory=list
    )


class ComparisonSummaryResponse(BaseModel):
    summary: dict
    erp_run: ErpRunResponse


class AnalysisReportResponse(BaseModel):
    report: dict
    erp_run: ErpRunResponse
    report_url: str
    report_path: str


class CreateProjectRequest(BaseModel):
    project_id: str | None = None
    name: str
    description: str | None = None
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ProjectResponse(BaseModel):
    project_id: str
    name: str
    description: str | None
    metadata: dict[str, str | int | float | bool | None]


class ProjectsResponse(BaseModel):
    projects: list[ProjectResponse]


class CreateExperimentRequest(BaseModel):
    experiment_id: str | None = None
    name: str
    task_name: str | None = None
    default_event_mapping: EventColumnMappingPayload = Field(
        default_factory=EventColumnMappingPayload
    )
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ExperimentResponse(BaseModel):
    experiment_id: str
    project_id: str
    name: str
    task_name: str | None
    default_event_mapping: EventColumnMappingPayload
    metadata: dict[str, str | int | float | bool | None]


class ExperimentsResponse(BaseModel):
    experiments: list[ExperimentResponse]


@asynccontextmanager
async def lifespan(app: FastAPI):
    preprocessing_worker.start()
    epoch_worker.start()
    erp_worker.start()
    batch_worker.start()
    preprocessing_worker.recover()
    epoch_worker.recover()
    erp_worker.recover()
    batch_worker.recover()
    yield


app = FastAPI(title="NeuroWeave API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins_from_env(),
    allow_origin_regex=_cors_allow_origin_regex_from_env(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="neuroweave-api",
        workers={
            "preprocessing": preprocessing_worker.is_alive(),
            "epoch": epoch_worker.is_alive(),
            "erp": erp_worker.is_alive(),
            "batch": batch_worker.is_alive(),
        },
        data_directories={
            "samples": str(SAMPLE_DATASET_DIR),
            "uploads": str(UPLOADS_DIR),
            "runs": str(RUNS_DIR),
            "templates": str(TEMPLATES_DIR),
            "batches": str(BATCHES_DIR),
            "processed": str(PROCESSED_DIR),
            "epochs": str(EPOCHS_DIR),
            "erp": str(ERP_DIR),
        },
    )


@app.post(
    "/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_project(request: CreateProjectRequest) -> ProjectResponse:
    project = Project(
        project_id=request.project_id or _new_id("project"),
        name=request.name,
        description=request.description,
        metadata=request.metadata,
    )
    registry_repository.save_project(project)
    return _project_response(project)


@app.get("/projects", response_model=ProjectsResponse)
def list_projects() -> ProjectsResponse:
    return ProjectsResponse(
        projects=[
            _project_response(project)
            for project in registry_repository.list_projects()
        ]
    )


@app.post(
    "/projects/{project_id}/experiments",
    response_model=ExperimentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_experiment(
    project_id: str,
    request: CreateExperimentRequest,
) -> ExperimentResponse:
    if registry_repository.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    experiment = Experiment(
        experiment_id=request.experiment_id or _new_id("experiment"),
        project_id=project_id,
        name=request.name,
        task_name=request.task_name,
        default_event_mapping=EventColumnMapping(
            **request.default_event_mapping.model_dump()
        ),
        metadata=request.metadata,
    )
    registry_repository.save_experiment(experiment)
    return _experiment_response(experiment)


@app.get(
    "/projects/{project_id}/experiments",
    response_model=ExperimentsResponse,
)
def list_experiments(project_id: str) -> ExperimentsResponse:
    if registry_repository.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return ExperimentsResponse(
        experiments=[
            _experiment_response(experiment)
            for experiment in registry_repository.list_experiments(
                project_id=project_id
            )
        ]
    )


@app.post(
    "/datasets",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_dataset(request: CreateDatasetRequest) -> DatasetResponse:
    project = registry_repository.get_project(request.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    experiment = registry_repository.get_experiment(request.experiment_id)
    if experiment is None or experiment.project_id != request.project_id:
        raise HTTPException(status_code=404, detail="Experiment not found")

    participant_id = request.participant_id or _new_id("participant")
    participant = Participant(
        participant_id=participant_id,
        project_id=request.project_id,
        label=request.participant_label,
        group=request.participant_group,
    )
    registry_repository.save_participant(participant)

    dataset = IngestionDataset(
        dataset_id=request.dataset_id or _new_id("dataset"),
        project_id=request.project_id,
        experiment_id=request.experiment_id,
        participant_id=participant_id,
        session_id=request.session_id or _new_id("session"),
        status=DatasetStatus.NEEDS_FILES,
        metadata={
            **request.metadata,
            "participant_label": request.participant_label,
            "session_label": request.session_label,
        },
    )
    registry_repository.save_dataset(dataset)
    return _dataset_response(dataset)


@app.get("/datasets", response_model=DatasetsResponse)
def list_datasets(project_id: str | None = None) -> DatasetsResponse:
    return DatasetsResponse(
        datasets=[
            _dataset_response(dataset)
            for dataset in registry_repository.list_datasets(project_id=project_id)
        ]
    )


@app.delete(
    "/datasets/{dataset_id}/local-data",
    response_model=DatasetLocalDataDeletionResponse,
)
def delete_dataset_local_data(
    dataset_id: str,
    confirm_dataset_id: str,
    dry_run: bool = False,
) -> DatasetLocalDataDeletionResponse:
    dataset = registry_repository.get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if confirm_dataset_id != dataset_id:
        raise HTTPException(
            status_code=400,
            detail="confirm_dataset_id must match dataset_id",
        )

    plan = _dataset_local_data_deletion_plan(dataset_id)
    if plan["active_run_ids"]:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Dataset has active runs; wait for them to settle before deletion.",
                "active_run_ids": plan["active_run_ids"],
            },
        )

    if not dry_run:
        for path in plan["paths"]:
            if path.is_dir():
                shutil.rmtree(path)
            elif path.is_file():
                path.unlink()

    return DatasetLocalDataDeletionResponse(
        dataset_id=dataset_id,
        dry_run=dry_run,
        deleted=not dry_run,
        deleted_paths=[str(path) for path in plan["paths"]],
        run_ids=plan["run_ids"],
        warnings=plan["warnings"],
    )


@app.get("/datasets/samples", response_model=SampleDatasetsResponse)
def list_sample_datasets() -> SampleDatasetsResponse:
    samples = [
        SampleDataset(
            id=eeg_file.dataset_id,
            filename=eeg_file.filename,
            format=eeg_file.file_format,
        )
        for eeg_file in list_eeg_files(SAMPLE_DATASET_DIR)
    ]
    return SampleDatasetsResponse(samples=samples)


@app.get("/datasets/samples/{dataset_id}/metadata", response_model=DatasetMetadata)
def get_sample_dataset_metadata(dataset_id: str) -> DatasetMetadata:
    eeg_file = find_eeg_file_by_id(SAMPLE_DATASET_DIR, dataset_id)
    if eeg_file is None:
        raise HTTPException(status_code=404, detail="Sample dataset not found")

    try:
        metadata = read_eeg_metadata(eeg_file.path, dataset_id=eeg_file.dataset_id)
    except EegMetadataReadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return DatasetMetadata(
        id=metadata.dataset_id,
        format=metadata.file_format,
        channels=metadata.channel_count,
        sampling_rate=metadata.sampling_rate_hz,
        duration_seconds=metadata.duration_seconds,
        channel_names=metadata.channel_names,
        channel_details=[
            _channel_metadata_payload(channel)
            for channel in metadata.channel_details
        ],
        line_frequency_hz=metadata.line_frequency_hz,
        reference=metadata.reference,
    )


@app.post(
    "/datasets/{dataset_id}/files/eeg",
    response_model=EegUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_dataset_eeg_file(
    dataset_id: str,
    file: UploadFile = File(...),
) -> EegUploadResponse:
    dataset = registry_repository.get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    stored_path = _store_upload_file(
        file=file,
        destination_directory=registry_repository.eeg_directory(dataset_id),
    )

    try:
        metadata = read_eeg_metadata(stored_path, dataset_id=dataset_id)
    except EegMetadataReadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    uploaded_file = IngestionUploadedFile(
        file_id=_new_id("file"),
        dataset_id=dataset_id,
        kind=UploadedFileKind.EEG,
        original_filename=file.filename or stored_path.name,
        stored_path=str(stored_path),
        content_type=file.content_type,
        size_bytes=stored_path.stat().st_size,
        checksum_sha256=_sha256_file(stored_path),
    )
    registry_repository.save_uploaded_file(uploaded_file)

    sidecar_discovery = discover_bids_sidecars(stored_path)
    sidecar_files = _save_discovered_sidecar_files(
        dataset_id=dataset_id,
        discovery=sidecar_discovery,
    )
    metadata = _recording_metadata_with_source_manifest(
        metadata=metadata,
        primary_file=uploaded_file,
        primary_role="eeg_file",
        sidecar_files=sidecar_files,
        sidecar_discovery=sidecar_discovery,
    )
    recording = Recording(
        recording_id=_new_id("recording"),
        dataset_id=dataset_id,
        file_id=uploaded_file.file_id,
        metadata=metadata,
    )
    recording = _recording_with_discovered_sidecars(recording, sidecar_discovery)
    registry_repository.save_recording(recording)

    updated_dataset = replace(
        dataset,
        status=DatasetStatus.NEEDS_MAPPING,
        recording_id=recording.recording_id,
    )
    registry_repository.update_dataset(updated_dataset)

    return EegUploadResponse(
        dataset=_dataset_response(updated_dataset),
        uploaded_file=_uploaded_file_response(uploaded_file),
        recording=_recording_response(recording),
        sidecar_discovery=_bids_sidecar_discovery_response(sidecar_discovery),
        sidecar_files=[
            _uploaded_file_response(sidecar_file)
            for sidecar_file in sidecar_files
        ],
    )


@app.post(
    "/datasets/{dataset_id}/files/sidecars",
    response_model=SidecarUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_dataset_sidecar_file(
    dataset_id: str,
    file: UploadFile = File(...),
) -> SidecarUploadResponse:
    dataset = registry_repository.get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    recording = registry_repository.get_recording(dataset_id)
    if recording is None:
        raise HTTPException(status_code=409, detail="Recording not found")

    stored_path = _store_upload_file(
        file=file,
        destination_directory=registry_repository.metadata_directory(dataset_id),
    )

    try:
        enriched_recording = _recording_with_sidecar(recording, stored_path)
    except BidsSidecarError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    uploaded_file = IngestionUploadedFile(
        file_id=_new_id("file"),
        dataset_id=dataset_id,
        kind=UploadedFileKind.METADATA,
        original_filename=file.filename or stored_path.name,
        stored_path=str(stored_path),
        content_type=file.content_type,
        size_bytes=stored_path.stat().st_size,
        checksum_sha256=_sha256_file(stored_path),
    )
    registry_repository.save_uploaded_file(uploaded_file)
    enriched_recording = replace(
        enriched_recording,
        metadata=_recording_metadata_with_added_sources(
            enriched_recording.metadata,
            [
                _source_file_metadata_from_upload(
                    uploaded_file,
                    role="bids_sidecar",
                    sidecar_type=_sidecar_type_for_path(stored_path),
                    status="valid",
                )
            ],
        ),
    )
    registry_repository.save_recording(enriched_recording)

    return SidecarUploadResponse(
        dataset=_dataset_response(dataset),
        uploaded_file=_uploaded_file_response(uploaded_file),
        recording=_recording_response(enriched_recording),
    )


@app.post(
    "/datasets/{dataset_id}/files/events",
    response_model=EventUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_dataset_events_file(
    dataset_id: str,
    file: UploadFile = File(...),
) -> EventUploadResponse:
    dataset = registry_repository.get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    stored_path = _store_upload_file(
        file=file,
        destination_directory=registry_repository.events_directory(dataset_id),
    )

    try:
        preview = preview_event_log(stored_path)
    except EventLogPreviewError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    uploaded_file = IngestionUploadedFile(
        file_id=_new_id("file"),
        dataset_id=dataset_id,
        kind=UploadedFileKind.EVENTS,
        original_filename=file.filename or stored_path.name,
        stored_path=str(stored_path),
        content_type=file.content_type,
        size_bytes=stored_path.stat().st_size,
        checksum_sha256=_sha256_file(stored_path),
    )
    registry_repository.save_uploaded_file(uploaded_file)
    registry_repository.save_events_preview(dataset_id, preview)
    sidecar_discovery = discover_bids_sidecars(stored_path)
    sidecar_files = _save_discovered_sidecar_files(
        dataset_id=dataset_id,
        discovery=sidecar_discovery,
    )

    updated_dataset = replace(
        dataset,
        status=DatasetStatus.NEEDS_MAPPING,
        event_log_id=uploaded_file.file_id,
    )
    registry_repository.update_dataset(updated_dataset)

    return EventUploadResponse(
        dataset=_dataset_response(updated_dataset),
        uploaded_file=_uploaded_file_response(uploaded_file),
        preview=EventLogPreviewResponse(**preview),
        sidecar_discovery=_bids_sidecar_discovery_response(sidecar_discovery),
        sidecar_files=[
            _uploaded_file_response(sidecar_file)
            for sidecar_file in sidecar_files
        ],
    )


@app.post(
    "/datasets/{dataset_id}/events/mapping",
    response_model=EventLogResponse,
)
def map_dataset_events(
    dataset_id: str,
    request: EventMappingRequest,
) -> EventLogResponse:
    dataset = registry_repository.get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if not dataset.event_log_id:
        raise HTTPException(status_code=404, detail="Event file not found")

    uploaded_file = _find_uploaded_file(dataset_id, dataset.event_log_id)
    if uploaded_file is None or uploaded_file.kind != UploadedFileKind.EVENTS:
        raise HTTPException(status_code=404, detail="Event file not found")

    mapping = _resolve_event_mapping(dataset, request.mapping, request.preset)
    row_filter = _event_row_filter_from_payload(request.row_filter)
    condition_column = _event_condition_column_from_payload(request.condition_column)
    try:
        event_log = normalize_event_log(
            dataset_id=dataset_id,
            event_log_id=dataset.event_log_id,
            file_id=uploaded_file.file_id,
            path=Path(uploaded_file.stored_path),
            mapping=mapping,
            row_filter=row_filter,
            condition_column=condition_column,
            provenance=_event_log_provenance(
                dataset_id=dataset_id,
                uploaded_file=uploaded_file,
                preset=request.preset,
                preset_applied=request.mapping is None and request.preset is not None,
                mapping=mapping,
                row_filter=row_filter,
                condition_column=condition_column,
            ),
        )
    except (EventLogPreviewError, EventLogNormalizationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    registry_repository.save_event_log(event_log)
    return _event_log_response(event_log)


@app.get("/datasets/{dataset_id}/events", response_model=EventLogResponse)
def get_dataset_events(dataset_id: str) -> EventLogResponse:
    if registry_repository.get_dataset(dataset_id) is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    event_log = registry_repository.get_event_log(dataset_id)
    if event_log is None:
        raise HTTPException(status_code=404, detail="Event log not found")

    return _event_log_response(event_log)


@app.get(
    "/datasets/{dataset_id}/validation",
    response_model=ValidationReportResponse,
)
def get_dataset_validation(dataset_id: str) -> ValidationReportResponse:
    dataset = registry_repository.get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    report = _validate_dataset(dataset)
    updated_dataset = replace(dataset, status=report.status)
    registry_repository.update_dataset(updated_dataset)
    return _validation_report_response(report)


@app.post(
    "/datasets/{dataset_id}/preprocessing-runs",
    response_model=PreprocessingRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_preprocessing_run(
    dataset_id: str,
    config_payload: PreprocessingConfigPayload,
) -> PreprocessingRunResponse:
    dataset = registry_repository.get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    report = _validate_dataset(dataset)
    if not report.valid:
        updated_dataset = replace(dataset, status=report.status)
        registry_repository.update_dataset(updated_dataset)
        raise HTTPException(
            status_code=409,
            detail="Dataset must be valid before preprocessing.",
        )

    recording = registry_repository.get_recording(dataset_id)
    if recording is None:
        raise HTTPException(status_code=409, detail="Recording not found")

    uploaded_file = _find_uploaded_file(dataset_id, recording.file_id)
    if uploaded_file is None or uploaded_file.kind != UploadedFileKind.EEG:
        raise HTTPException(status_code=409, detail="EEG file not found")

    config = _preprocessing_config_from_payload(config_payload)
    config_errors = _validate_preprocessing_config(config, recording)
    if config_errors:
        raise HTTPException(status_code=422, detail=config_errors)

    run_id = _new_id("preprocess")
    output_path = _preprocessing_output_path(dataset_id, run_id)

    run = PreprocessingRun(
        run_id=run_id,
        dataset_id=dataset_id,
        config=config,
        status=PreprocessingRunStatus.PENDING,
        output_path=str(output_path),
        output_metadata=_preprocessing_input_provenance(
            uploaded_file=uploaded_file,
            recording=recording,
        ),
    )
    run_repository.save_preprocessing_run(run)
    preprocessing_worker.enqueue(run_id)
    return _preprocessing_run_response(run)


@app.get(
    "/preprocessing-runs/{run_id}",
    response_model=PreprocessingRunResponse,
)
def get_preprocessing_run(run_id: str) -> PreprocessingRunResponse:
    run = run_repository.get_preprocessing_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Preprocessing run not found")

    return _preprocessing_run_response(run)


@app.post(
    "/preprocessing-runs/{run_id}/cancel",
    response_model=PreprocessingRunResponse,
)
def cancel_preprocessing_run(run_id: str) -> PreprocessingRunResponse:
    run = run_repository.get_preprocessing_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Preprocessing run not found")

    cancelled_run = _request_preprocessing_run_cancellation(run_id)
    if cancelled_run is not None:
        return _preprocessing_run_response(cancelled_run)

    return _preprocessing_run_response(run)


def _request_preprocessing_run_cancellation(
    run_id: str,
) -> PreprocessingRun | None:
    run = run_repository.get_preprocessing_run(run_id)
    if run is None:
        return None

    if run.status == PreprocessingRunStatus.PENDING:
        cancelled_at = _utc_now_iso()
        warnings = [*run.warnings, "Run cancelled before preprocessing started."]
        cancelled_run = replace(
            run,
            status=PreprocessingRunStatus.CANCELLED,
            finished_at_utc=cancelled_at,
            cancel_requested_at_utc=run.cancel_requested_at_utc or cancelled_at,
            warnings=warnings,
            diagnostics=_diagnostics_from_warnings(warnings, "preprocessing"),
        )
        run_repository.save_preprocessing_run(cancelled_run)
        return cancelled_run

    if run.status == PreprocessingRunStatus.RUNNING:
        warnings = [
            *run.warnings,
            "Cancellation requested; preprocessing will stop at the next checkpoint.",
        ]
        cancelling_run = replace(
            run,
            status=PreprocessingRunStatus.CANCELLING,
            cancel_requested_at_utc=run.cancel_requested_at_utc or _utc_now_iso(),
            warnings=warnings,
            diagnostics=_diagnostics_from_warnings(warnings, "preprocessing"),
        )
        run_repository.save_preprocessing_run(cancelling_run)
        return cancelling_run

    return run


@app.get(
    "/datasets/{dataset_id}/preprocessing-runs",
    response_model=PreprocessingRunsResponse,
)
def list_dataset_preprocessing_runs(dataset_id: str) -> PreprocessingRunsResponse:
    if registry_repository.get_dataset(dataset_id) is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return PreprocessingRunsResponse(
        runs=[
            _preprocessing_run_response(run)
            for run in run_repository.list_preprocessing_runs(dataset_id=dataset_id)
        ]
    )


@app.post(
    "/datasets/{dataset_id}/epoch-runs",
    response_model=EpochRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_epoch_run(
    dataset_id: str,
    config_payload: EpochConfigPayload,
) -> EpochRunResponse:
    dataset = registry_repository.get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    preprocessing_run = run_repository.get_preprocessing_run(
        config_payload.preprocessing_run_id
    )
    if preprocessing_run is None:
        raise HTTPException(status_code=404, detail="Preprocessing run not found")

    event_log = registry_repository.get_event_log(dataset_id)
    recording = registry_repository.get_recording(dataset_id)
    config = EpochConfig(**config_payload.model_dump())
    config_errors, config_warnings = _validate_epoch_config(
        config=config,
        dataset=dataset,
        preprocessing_run=preprocessing_run,
        event_log=event_log,
        recording=recording,
    )
    if config_errors:
        raise HTTPException(status_code=422, detail=config_errors)

    run_id = _new_id("epoch")
    output_path = _epoch_output_path(dataset_id, run_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    run = EpochRun(
        run_id=run_id,
        dataset_id=dataset_id,
        config=config,
        status=EpochRunStatus.PENDING,
        output_path=str(output_path),
        output_metadata=_epoch_input_provenance(
            preprocessing_run=preprocessing_run,
            event_log=event_log,
            recording=recording,
        ),
        warnings=config_warnings,
        diagnostics=_diagnostics_from_warnings(config_warnings, "validation"),
    )
    run_repository.save_epoch_run(run)
    epoch_worker.enqueue(run_id)
    return _epoch_run_response(run)


@app.get(
    "/epoch-runs/{run_id}",
    response_model=EpochRunResponse,
)
def get_epoch_run(run_id: str) -> EpochRunResponse:
    run = run_repository.get_epoch_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Epoch run not found")

    return _epoch_run_response(run)


@app.get(
    "/datasets/{dataset_id}/epoch-runs",
    response_model=EpochRunsResponse,
)
def list_dataset_epoch_runs(dataset_id: str) -> EpochRunsResponse:
    if registry_repository.get_dataset(dataset_id) is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return EpochRunsResponse(
        runs=[
            _epoch_run_response(run)
            for run in run_repository.list_epoch_runs(dataset_id=dataset_id)
        ]
    )


@app.post(
    "/datasets/{dataset_id}/erp-runs",
    response_model=ErpRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_erp_run(
    dataset_id: str,
    config_payload: ErpConfigPayload,
) -> ErpRunResponse:
    if registry_repository.get_dataset(dataset_id) is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    epoch_run = run_repository.get_epoch_run(config_payload.epoch_run_id)
    if epoch_run is None:
        raise HTTPException(status_code=404, detail="Epoch run not found")

    config = ErpConfig(**config_payload.model_dump())
    config_errors, config_warnings = _validate_erp_config(
        config=config,
        dataset_id=dataset_id,
        epoch_run=epoch_run,
    )
    if config_errors:
        raise HTTPException(status_code=422, detail=config_errors)

    run_id = _new_id("erp")
    output_path = _erp_metadata_path(dataset_id, run_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    run = ErpRun(
        run_id=run_id,
        dataset_id=dataset_id,
        config=config,
        status=ErpRunStatus.PENDING,
        output_path=str(output_path),
        output_metadata=_erp_input_provenance(epoch_run),
        warnings=config_warnings,
        diagnostics=_diagnostics_from_warnings(config_warnings, "validation"),
    )
    run_repository.save_erp_run(run)
    erp_worker.enqueue(run_id)
    return _erp_run_response(run)


@app.get(
    "/erp-runs/{run_id}",
    response_model=ErpRunResponse,
)
def get_erp_run(run_id: str) -> ErpRunResponse:
    run = run_repository.get_erp_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="ERP run not found")

    return _erp_run_response(run)


@app.get(
    "/datasets/{dataset_id}/erp-runs",
    response_model=ErpRunsResponse,
)
def list_dataset_erp_runs(dataset_id: str) -> ErpRunsResponse:
    if registry_repository.get_dataset(dataset_id) is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return ErpRunsResponse(
        runs=[
            _erp_run_response(run)
            for run in run_repository.list_erp_runs(dataset_id=dataset_id)
        ]
    )


@app.post(
    "/workflow-templates",
    response_model=WorkflowTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
def save_workflow_template(
    request: WorkflowTemplateSaveRequest,
) -> WorkflowTemplateResponse:
    template_id = request.template_id or _new_id("template")
    existing_template = template_repository.get_template(template_id)
    created_at = (
        existing_template.created_at_utc
        if existing_template is not None
        else _utc_now_iso()
    )
    template = _workflow_template_from_request(
        request=request,
        template_id=template_id,
        created_at_utc=created_at,
        updated_at_utc=_utc_now_iso(),
    )
    validation = validate_workflow_template(template)
    if not validation.valid:
        raise HTTPException(status_code=422, detail=validation.errors)

    try:
        saved_template = template_repository.save_template(template)
    except JsonRegistryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _workflow_template_response(saved_template)


@app.post(
    "/workflow-templates/from-run",
    response_model=WorkflowTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_workflow_template_from_run(
    request: WorkflowTemplateFromRunRequest,
) -> WorkflowTemplateResponse:
    template_id = request.template_id or _new_id("template")
    if not (
        request.preprocessing_run_id
        or request.epoch_run_id
        or request.erp_run_id
    ):
        raise HTTPException(
            status_code=422,
            detail="At least one source run id is required.",
        )

    try:
        template = _workflow_template_from_completed_runs(
            request=request,
            template_id=template_id,
            created_at_utc=_utc_now_iso(),
            updated_at_utc=_utc_now_iso(),
        )
        saved_template = template_repository.save_template(template)
    except JsonRegistryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _workflow_template_response(saved_template)


@app.get(
    "/workflow-templates",
    response_model=WorkflowTemplatesResponse,
)
def list_workflow_templates() -> WorkflowTemplatesResponse:
    return WorkflowTemplatesResponse(
        templates=[
            _workflow_template_response(template)
            for template in template_repository.list_templates()
        ]
    )


@app.get(
    "/workflow-templates/{template_id}",
    response_model=WorkflowTemplateResponse,
)
def get_workflow_template(template_id: str) -> WorkflowTemplateResponse:
    template = template_repository.get_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Workflow template not found")
    return _workflow_template_response(template)


@app.post(
    "/workflow-templates/{template_id}/apply-preview",
    response_model=WorkflowTemplateApplyPreviewResponse,
)
def preview_workflow_template_apply(
    template_id: str,
    request: WorkflowTemplateApplyPreviewRequest,
) -> WorkflowTemplateApplyPreviewResponse:
    template = template_repository.get_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Workflow template not found")

    dataset = registry_repository.get_dataset(request.target_dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return _workflow_template_apply_preview(
        template=template,
        request=request,
        dataset=dataset,
    )


@app.delete(
    "/workflow-templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_workflow_template(template_id: str) -> None:
    if not template_repository.delete_template(template_id):
        raise HTTPException(status_code=404, detail="Workflow template not found")
    return None


@app.post(
    "/batches",
    response_model=BatchRunPlanResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_batch(request: BatchCreateRequest) -> BatchRunPlanResponse:
    batch_request = _batch_request_from_payload(request)
    request_validation = validate_batch_request(batch_request)
    if not request_validation.valid:
        raise HTTPException(status_code=422, detail=request_validation.errors)

    template = template_repository.get_template(request.template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Workflow template not found")

    captured_at = _utc_now_iso()
    batch_id = _new_id("batch")
    try:
        planning_result = plan_batch_run(
            batch_id=batch_id,
            request=batch_request,
            template=template,
            captured_at_utc=captured_at,
            dataset_resolver=registry_repository.get_dataset,
            apply_preview_resolver=_batch_apply_preview_for_planning,
            run_bindings_resolver=_batch_run_bindings_for_preview,
        )
    except BatchPlanningError as exc:
        raise HTTPException(status_code=422, detail=exc.errors) from exc

    try:
        saved_batch = batch_repository.save_batch(planning_result.plan)
    except JsonRegistryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    batch_worker.enqueue(saved_batch.batch_id)
    return _batch_run_plan_response(saved_batch)


@app.get("/batches", response_model=BatchRunsResponse)
def list_batches() -> BatchRunsResponse:
    return BatchRunsResponse(
        batches=[
            _batch_run_plan_response(batch)
            for batch in batch_repository.list_batches()
        ]
    )


@app.get("/batches/{batch_id}/summary-artifact")
def get_batch_summary_artifact(batch_id: str) -> FileResponse:
    batch = batch_repository.get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    summary_path = _write_batch_summary_artifact(batch)
    return FileResponse(
        summary_path,
        media_type="application/json",
        filename="batch_summary.json",
    )


@app.post(
    "/batches/{batch_id}/items/{item_id}/retry",
    response_model=BatchRunPlanResponse,
)
def retry_batch_item(batch_id: str, item_id: str) -> BatchRunPlanResponse:
    batch = batch_repository.get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")

    if batch.status in {
        BatchStatus.PENDING,
        BatchStatus.RUNNING,
        BatchStatus.CANCELLING,
    }:
        raise HTTPException(
            status_code=409,
            detail="Batch must be idle before retry.",
        )

    item = _batch_item_by_id(batch, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Batch item not found")
    if item.status != BatchItemStatus.FAILED:
        raise HTTPException(
            status_code=409,
            detail="Only failed batch items can be retried.",
        )

    retry_item = _retry_failed_batch_item(item)
    retry_batch = replace(
        batch,
        status=BatchStatus.PENDING,
        updated_at_utc=_batch_updated_at(batch),
        items=[
            retry_item if current.item_id == item.item_id else current
            for current in batch.items
        ],
    )
    try:
        saved_batch = batch_repository.save_batch(retry_batch)
    except JsonRegistryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    batch_worker.enqueue(saved_batch.batch_id)
    return _batch_run_plan_response(saved_batch)


@app.get("/batches/{batch_id}", response_model=BatchRunPlanResponse)
def get_batch(batch_id: str) -> BatchRunPlanResponse:
    batch = batch_repository.get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    return _batch_run_plan_response(batch)


@app.post("/batches/{batch_id}/cancel", response_model=BatchRunPlanResponse)
def cancel_batch(batch_id: str) -> BatchRunPlanResponse:
    batch = batch_repository.get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")

    if batch.status in {
        BatchStatus.COMPLETED,
        BatchStatus.FAILED,
        BatchStatus.CANCELLED,
    }:
        return _batch_run_plan_response(batch)

    cancel_status = (
        BatchStatus.CANCELLED
        if batch.status == BatchStatus.PENDING
        else BatchStatus.CANCELLING
    )
    item_status = (
        BatchItemStatus.CANCELLED
        if cancel_status == BatchStatus.CANCELLED
        else BatchItemStatus.CANCELLING
    )
    for item in batch.items:
        preprocessing_run_id = item.run_ids.get(RunKind.PREPROCESSING.value)
        if item.status == BatchItemStatus.RUNNING and preprocessing_run_id:
            _request_preprocessing_run_cancellation(preprocessing_run_id)

    updated_batch = replace(
        batch,
        status=cancel_status,
        updated_at_utc=_batch_updated_at(batch),
        items=[
            replace(item, status=item_status)
            if item.status in {BatchItemStatus.PENDING, BatchItemStatus.RUNNING}
            else item
            for item in batch.items
        ],
    )
    batch_repository.save_batch(updated_batch)
    if updated_batch.status == BatchStatus.CANCELLED:
        _write_batch_summary_artifact(updated_batch)
    return _batch_run_plan_response(updated_batch)


@app.get("/datasets/{dataset_id}/qc-summary", response_model=QcSummaryResponse)
def get_dataset_qc_summary(
    dataset_id: str,
    run_id: str | None = None,
) -> QcSummaryResponse:
    if registry_repository.get_dataset(dataset_id) is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    run = _resolve_qc_summary_run(dataset_id=dataset_id, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Completed QC run not found")

    manifest_path = _run_artifact_manifest_path(run)
    if manifest_path is None:
        raise HTTPException(status_code=404, detail="Artifact manifest not found")

    try:
        summary = build_qc_summary(manifest_path)
    except QcSummaryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    batch_context = _batch_context_for_run(run)
    if batch_context is not None:
        summary["batch"] = batch_context
    summary["phase_d"] = _phase_d_metadata_for_run(run)

    return QcSummaryResponse(
        dataset_id=dataset_id,
        run_id=run.run_id,
        run_kind=run.run_kind.value,
        summary=summary,
    )


@app.get("/datasets/{dataset_id}/export-bundle")
def get_dataset_export_bundle(
    dataset_id: str,
    run_id: str | None = None,
) -> FileResponse:
    if registry_repository.get_dataset(dataset_id) is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    run = _resolve_qc_summary_run(dataset_id=dataset_id, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Completed export run not found")

    return _export_bundle_response(run)


@app.get("/erp-runs/{run_id}/export-bundle")
def get_erp_run_export_bundle(run_id: str) -> FileResponse:
    run = run_repository.get_erp_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="ERP run not found")
    if _run_status_value(run) != "completed":
        raise HTTPException(status_code=409, detail="Run is not completed")

    return _export_bundle_response(run)


@app.post(
    "/erp-runs/{run_id}/analysis-report",
    response_model=AnalysisReportResponse,
)
def create_erp_analysis_report(run_id: str) -> AnalysisReportResponse:
    run = run_repository.get_erp_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="ERP run not found")
    if _run_status_value(run) != "completed":
        raise HTTPException(status_code=409, detail="Run is not completed")

    try:
        report, completed_run, report_path = _generate_run_analysis_report(run)
    except (AnalysisReportError, ArtifactManifestError, QcSummaryError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    run_repository.save_erp_run(completed_run)
    return AnalysisReportResponse(
        report=report,
        erp_run=_erp_run_response(completed_run),
        report_url=f"/artifacts/{completed_run.run_id}/{report_path.name}",
        report_path=str(report_path),
    )


@app.post(
    "/erp-runs/{run_id}/comparison-summary",
    response_model=ComparisonSummaryResponse,
)
def create_comparison_summary(
    run_id: str,
    config_payload: ComparisonConfigPayload,
) -> ComparisonSummaryResponse:
    run = run_repository.get_erp_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="ERP run not found")
    errors = _validate_comparison_config(config_payload=config_payload, run=run)
    if errors:
        raise HTTPException(status_code=422, detail=errors)

    assert run.output_path is not None
    output_path = Path(run.output_path).parent / "comparison_summary.json"
    config = ComparisonConfig(
        erp_run_id=run.run_id,
        condition_a=config_payload.condition_a,
        condition_b=config_payload.condition_b,
        channel=config_payload.channel,
        use_gfp=config_payload.use_gfp,
        window_start_seconds=config_payload.window_start_seconds,
        window_end_seconds=config_payload.window_end_seconds,
        metric=config_payload.metric,
        paired_observations=[
            ComparisonObservation(
                subject_id=observation.subject_id,
                condition_a_mean_amplitude_uv=(
                    observation.condition_a_mean_amplitude_uv
                ),
                condition_b_mean_amplitude_uv=(
                    observation.condition_b_mean_amplitude_uv
                ),
            )
            for observation in config_payload.paired_observations
        ],
    )

    try:
        summary = generate_comparison_summary(
            erp_metadata_path=Path(run.output_path),
            output_path=output_path,
            config=config,
        )
    except ComparisonError as exc:
        raise HTTPException(status_code=422, detail=[str(exc)]) from exc

    completed_run = replace(
        run,
        output_metadata=_comparison_completed_metadata(
            run=run,
            summary_path=output_path,
            summary=summary,
        ),
    )
    run_repository.save_erp_run(completed_run)
    return ComparisonSummaryResponse(
        summary=summary,
        erp_run=_erp_run_response(completed_run),
    )


@app.get("/artifacts/{run_id}/{filename}")
def get_run_artifact(run_id: str, filename: str) -> FileResponse:
    artifact_root = _artifact_root_for_run(run_id)
    if artifact_root is None:
        raise HTTPException(status_code=404, detail="Run artifact root not found")
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid artifact filename")

    artifact_path = artifact_root / filename
    try:
        resolved_artifact_path = artifact_path.resolve()
        resolved_artifact_root = artifact_root.resolve()
    except OSError as exc:
        raise HTTPException(status_code=404, detail="Artifact not found") from exc

    if (
        not resolved_artifact_path.is_relative_to(resolved_artifact_root)
        or not resolved_artifact_path.is_file()
    ):
        raise HTTPException(status_code=404, detail="Artifact not found")

    return FileResponse(resolved_artifact_path)


@app.get("/runs/{run_id}/artifact-integrity", response_model=ArtifactIntegrityResponse)
def get_run_artifact_integrity(run_id: str) -> ArtifactIntegrityResponse:
    run = _find_run_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    manifest_path = _run_artifact_manifest_path(run)
    if manifest_path is None:
        raise HTTPException(status_code=404, detail="Artifact manifest not found")

    try:
        integrity = check_artifact_integrity(manifest_path)
    except ArtifactManifestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return ArtifactIntegrityResponse(
        run_id=run.run_id,
        dataset_id=run.dataset_id,
        run_kind=_run_kind_value(run),
        integrity=integrity,
    )


@app.get("/runs/{run_id}/rerun-plan", response_model=RerunPlanResponse)
def get_run_rerun_plan(run_id: str) -> RerunPlanResponse:
    run = _find_run_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    plan = _build_rerun_plan(run)
    return RerunPlanResponse(
        run_id=run.run_id,
        dataset_id=run.dataset_id,
        run_kind=_run_kind_value(run),
        plan=plan,
    )


@app.get("/datasets/{dataset_id}", response_model=DatasetResponse)
def get_dataset(dataset_id: str) -> DatasetResponse:
    dataset = registry_repository.get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return _dataset_response(dataset)


def _project_response(project: Project) -> ProjectResponse:
    return ProjectResponse(
        project_id=project.project_id,
        name=project.name,
        description=project.description,
        metadata=project.metadata,
    )


def _experiment_response(experiment: Experiment) -> ExperimentResponse:
    return ExperimentResponse(
        experiment_id=experiment.experiment_id,
        project_id=experiment.project_id,
        name=experiment.name,
        task_name=experiment.task_name,
        default_event_mapping=EventColumnMappingPayload(
            **experiment.default_event_mapping.__dict__
        ),
        metadata=experiment.metadata,
    )


def _dataset_response(dataset: IngestionDataset) -> DatasetResponse:
    return DatasetResponse(
        dataset_id=dataset.dataset_id,
        project_id=dataset.project_id,
        experiment_id=dataset.experiment_id,
        participant_id=dataset.participant_id,
        session_id=dataset.session_id,
        status=dataset.status.value,
        recording_id=dataset.recording_id,
        event_log_id=dataset.event_log_id,
        metadata=dataset.metadata,
    )


def _uploaded_file_response(uploaded_file: IngestionUploadedFile) -> UploadedFileResponse:
    return UploadedFileResponse(
        file_id=uploaded_file.file_id,
        dataset_id=uploaded_file.dataset_id,
        kind=uploaded_file.kind.value,
        original_filename=uploaded_file.original_filename,
        stored_path=uploaded_file.stored_path,
        content_type=uploaded_file.content_type,
        size_bytes=uploaded_file.size_bytes,
        checksum_sha256=uploaded_file.checksum_sha256,
    )


def _recording_response(recording: Recording) -> RecordingResponse:
    return RecordingResponse(
        recording_id=recording.recording_id,
        dataset_id=recording.dataset_id,
        file_id=recording.file_id,
        metadata=DatasetMetadata(
            id=recording.metadata.dataset_id,
            format=recording.metadata.file_format,
            channels=recording.metadata.channel_count,
            sampling_rate=recording.metadata.sampling_rate_hz,
            duration_seconds=recording.metadata.duration_seconds,
            channel_names=recording.metadata.channel_names,
            channel_details=[
                _channel_metadata_payload(channel)
                for channel in recording.metadata.channel_details
            ],
            line_frequency_hz=recording.metadata.line_frequency_hz,
            reference=recording.metadata.reference,
            source_files=[
                _source_file_metadata_payload(source_file)
                for source_file in recording.metadata.source_files
            ],
            sidecar_discovery=recording.metadata.sidecar_discovery,
        ),
    )


def _source_file_metadata_payload(
    source_file: SourceFileMetadata,
) -> SourceFileMetadataPayload:
    return SourceFileMetadataPayload(
        role=source_file.role,
        original_filename=source_file.original_filename,
        stored_path=source_file.stored_path,
        size_bytes=source_file.size_bytes,
        checksum_sha256=source_file.checksum_sha256,
        content_type=source_file.content_type,
        sidecar_type=source_file.sidecar_type,
        status=source_file.status,
        diagnostics=source_file.diagnostics,
    )


def _bids_sidecar_discovery_response(
    discovery: BidsSidecarDiscovery,
) -> BidsSidecarDiscoveryResponse:
    return BidsSidecarDiscoveryResponse(
        schema_version=discovery.schema_version,
        reference_path=str(discovery.reference_path),
        bids_basename=discovery.bids_basename,
        candidates=[
            BidsSidecarCandidateResponse(
                sidecar_type=candidate.sidecar_type,
                path=str(candidate.path),
                status=candidate.status,
                diagnostics=[
                    BidsSidecarDiagnosticResponse(
                        severity=diagnostic.severity,
                        source=diagnostic.source,
                        code=diagnostic.code,
                        impact=diagnostic.impact,
                        suggested_action=diagnostic.suggested_action,
                    )
                    for diagnostic in candidate.diagnostics
                ],
            )
            for candidate in discovery.candidates
        ],
        diagnostics=[
            BidsSidecarDiagnosticResponse(
                severity=diagnostic.severity,
                source=diagnostic.source,
                code=diagnostic.code,
                impact=diagnostic.impact,
                suggested_action=diagnostic.suggested_action,
            )
            for diagnostic in discovery.diagnostics
        ],
    )


def _save_discovered_sidecar_files(
    *,
    dataset_id: str,
    discovery: BidsSidecarDiscovery,
) -> list[IngestionUploadedFile]:
    existing_paths = {
        str(Path(uploaded_file.stored_path).resolve())
        for uploaded_file in registry_repository.list_uploaded_files(dataset_id)
    }
    reference_path = str(discovery.reference_path.resolve())
    uploaded_sidecars: list[IngestionUploadedFile] = []

    for candidate in discovery.candidates:
        resolved_path = str(candidate.path.resolve())
        if resolved_path == reference_path or resolved_path in existing_paths:
            continue
        uploaded_file = IngestionUploadedFile(
            file_id=_new_id("file"),
            dataset_id=dataset_id,
            kind=UploadedFileKind.METADATA,
            original_filename=candidate.path.name,
            stored_path=str(candidate.path),
            content_type=_content_type_for_path(candidate.path),
            size_bytes=candidate.path.stat().st_size,
            checksum_sha256=_sha256_file(candidate.path),
        )
        registry_repository.save_uploaded_file(uploaded_file)
        existing_paths.add(resolved_path)
        uploaded_sidecars.append(uploaded_file)

    return uploaded_sidecars


def _recording_metadata_with_source_manifest(
    *,
    metadata: RecordingMetadata,
    primary_file: IngestionUploadedFile,
    primary_role: str,
    sidecar_files: list[IngestionUploadedFile],
    sidecar_discovery: BidsSidecarDiscovery,
) -> RecordingMetadata:
    return replace(
        _recording_metadata_with_added_sources(
            metadata,
            [
                _source_file_metadata_from_upload(primary_file, role=primary_role),
                *[
                    _source_file_metadata_from_upload(
                        sidecar_file,
                        role="bids_sidecar",
                        sidecar_type=_sidecar_type_for_path(
                            Path(sidecar_file.stored_path)
                        ),
                        status=_sidecar_status_for_path(
                            sidecar_discovery,
                            Path(sidecar_file.stored_path),
                        ),
                        diagnostics=_sidecar_diagnostics_for_path(
                            sidecar_discovery,
                            Path(sidecar_file.stored_path),
                        ),
                    )
                    for sidecar_file in sidecar_files
                ],
            ],
        ),
        sidecar_discovery=_bids_sidecar_discovery_metadata(sidecar_discovery),
    )


def _recording_metadata_with_added_sources(
    metadata: RecordingMetadata,
    source_files: list[SourceFileMetadata],
) -> RecordingMetadata:
    by_key = {
        (source_file.role, source_file.stored_path): source_file
        for source_file in metadata.source_files
    }
    for source_file in source_files:
        by_key[(source_file.role, source_file.stored_path)] = source_file
    return replace(metadata, source_files=list(by_key.values()))


def _source_file_metadata_from_upload(
    uploaded_file: IngestionUploadedFile,
    *,
    role: str,
    sidecar_type: str | None = None,
    status: str | None = None,
    diagnostics: list[dict[str, Any]] | None = None,
) -> SourceFileMetadata:
    return SourceFileMetadata(
        role=role,
        original_filename=uploaded_file.original_filename,
        stored_path=uploaded_file.stored_path,
        size_bytes=uploaded_file.size_bytes,
        checksum_sha256=uploaded_file.checksum_sha256,
        content_type=uploaded_file.content_type,
        sidecar_type=sidecar_type,
        status=status,
        diagnostics=diagnostics or [],
    )


def _source_file_payload_from_upload(
    uploaded_file: IngestionUploadedFile,
    *,
    role: str,
    sidecar_type: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": role,
        "file_id": uploaded_file.file_id,
        "original_filename": uploaded_file.original_filename,
        "stored_path": uploaded_file.stored_path,
        "path": uploaded_file.stored_path,
        "content_type": uploaded_file.content_type,
        "size_bytes": uploaded_file.size_bytes,
        "checksum_sha256": uploaded_file.checksum_sha256,
    }
    if sidecar_type is not None:
        payload["sidecar_type"] = sidecar_type
    return payload


def _bids_sidecar_discovery_metadata(discovery: BidsSidecarDiscovery) -> dict[str, Any]:
    return {
        "schema_version": discovery.schema_version,
        "reference_path": str(discovery.reference_path),
        "bids_basename": discovery.bids_basename,
        "candidates": [
            {
                "sidecar_type": candidate.sidecar_type,
                "path": str(candidate.path),
                "status": candidate.status,
                "diagnostics": [
                    {
                        "severity": diagnostic.severity,
                        "source": diagnostic.source,
                        "code": diagnostic.code,
                        "impact": diagnostic.impact,
                        "suggested_action": diagnostic.suggested_action,
                    }
                    for diagnostic in candidate.diagnostics
                ],
            }
            for candidate in discovery.candidates
        ],
        "diagnostics": [
            {
                "severity": diagnostic.severity,
                "source": diagnostic.source,
                "code": diagnostic.code,
                "impact": diagnostic.impact,
                "suggested_action": diagnostic.suggested_action,
            }
            for diagnostic in discovery.diagnostics
        ],
    }


def _sidecar_status_for_path(
    discovery: BidsSidecarDiscovery,
    path: Path,
) -> str | None:
    resolved_path = path.resolve()
    for candidate in discovery.candidates:
        if candidate.path.resolve() == resolved_path:
            return candidate.status
    return None


def _sidecar_diagnostics_for_path(
    discovery: BidsSidecarDiscovery,
    path: Path,
) -> list[dict[str, Any]]:
    resolved_path = path.resolve()
    for candidate in discovery.candidates:
        if candidate.path.resolve() == resolved_path:
            return [
                {
                    "severity": diagnostic.severity,
                    "source": diagnostic.source,
                    "code": diagnostic.code,
                    "impact": diagnostic.impact,
                    "suggested_action": diagnostic.suggested_action,
                }
                for diagnostic in candidate.diagnostics
            ]
    return []


def _sidecar_type_for_path(path: Path) -> str | None:
    lower_name = path.name.lower()
    if lower_name.endswith("_eeg.json"):
        return "eeg_json"
    if lower_name.endswith("_channels.tsv"):
        return "channels_tsv"
    if lower_name.endswith("_events.tsv"):
        return "events_tsv"
    if lower_name.endswith("_electrodes.tsv"):
        return "electrodes_tsv"
    if lower_name.endswith("_coordsystem.json"):
        return "coordsystem_json"
    return None


def _content_type_for_path(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "application/json"
    if suffix == ".tsv":
        return "text/tab-separated-values"
    if suffix == ".csv":
        return "text/csv"
    return None


def _recording_with_discovered_sidecars(
    recording: Recording,
    discovery: BidsSidecarDiscovery,
) -> Recording:
    enriched_recording = recording
    for candidate in discovery.candidates:
        if candidate.status != "valid":
            continue
        if candidate.sidecar_type not in {"channels_tsv", "eeg_json"}:
            continue
        enriched_recording = _recording_with_sidecar(
            enriched_recording,
            candidate.path,
        )
    return enriched_recording


def _recording_with_sidecar(recording: Recording, sidecar_path: Path) -> Recording:
    filename = sidecar_path.name.lower()
    metadata = recording.metadata
    if filename.endswith("_channels.tsv"):
        channels = read_channels_tsv(sidecar_path)
        return replace(
            recording,
            metadata=replace(
                metadata,
                channel_details=[
                    ChannelMetadata(
                        name=channel.name,
                        type=channel.type,
                        units=channel.units,
                        status=channel.status,
                        status_description=channel.status_description,
                    )
                    for channel in channels
                ],
            ),
        )

    if filename.endswith("_eeg.json"):
        sidecar = read_eeg_json(sidecar_path)
        return replace(
            recording,
            metadata=replace(
                metadata,
                line_frequency_hz=sidecar.line_frequency_hz,
                reference=sidecar.reference,
            ),
        )

    raise BidsSidecarError(
        "Unsupported BIDS sidecar filename; expected *_channels.tsv or *_eeg.json."
    )


def _channel_metadata_payload(channel: ChannelMetadata) -> ChannelMetadataPayload:
    return ChannelMetadataPayload(
        name=channel.name,
        type=channel.type,
        units=channel.units,
        status=channel.status,
        status_description=channel.status_description,
    )


def _event_log_response(event_log: EventLog) -> EventLogResponse:
    return EventLogResponse(
        event_log_id=event_log.event_log_id,
        dataset_id=event_log.dataset_id,
        file_id=event_log.file_id,
        mapping=EventColumnMappingPayload(**event_log.mapping.__dict__),
        row_count=event_log.row_count,
        filter_count=event_log.filter_count,
        condition_column=event_log.condition_column,
        events=[
            NormalizedEventResponse(
                onset_seconds=event.onset_seconds,
                source_row=event.source_row,
                duration_seconds=event.duration_seconds,
                trial_type=event.trial_type,
                stimulus=event.stimulus,
                response=event.response,
                correct=event.correct,
                reaction_time_seconds=event.reaction_time_seconds,
                source_columns=event.source_columns,
            )
            for event in event_log.events
        ],
    )


def _validation_report_response(report: ValidationReport) -> ValidationReportResponse:
    issues = [_validation_issue_response(issue) for issue in report.issues]
    return ValidationReportResponse(
        dataset_id=report.dataset_id,
        status=report.status.value,
        valid=report.valid,
        errors=[
            issue
            for issue in issues
            if issue.severity == ValidationSeverity.ERROR.value
        ],
        warnings=[
            issue
            for issue in issues
            if issue.severity == ValidationSeverity.WARNING.value
        ],
        issues=issues,
    )


def _preprocessing_run_response(run: PreprocessingRun) -> PreprocessingRunResponse:
    return PreprocessingRunResponse(
        run_id=run.run_id,
        dataset_id=run.dataset_id,
        run_kind=run.run_kind.value,
        schema_version=run.schema_version,
        config=PreprocessingConfigPayload(**asdict(run.config)),
        status=run.status.value,
        started_at_utc=run.started_at_utc,
        finished_at_utc=run.finished_at_utc,
        cancel_requested_at_utc=run.cancel_requested_at_utc,
        output_path=run.output_path,
        output_metadata=run.output_metadata,
        warnings=run.warnings,
        diagnostics=_run_diagnostics_response(run.diagnostics),
        errors=run.errors,
    )


def _epoch_run_response(run: EpochRun) -> EpochRunResponse:
    return EpochRunResponse(
        run_id=run.run_id,
        dataset_id=run.dataset_id,
        run_kind=run.run_kind.value,
        schema_version=run.schema_version,
        config=EpochConfigPayload(**run.config.__dict__),
        status=run.status.value,
        started_at_utc=run.started_at_utc,
        finished_at_utc=run.finished_at_utc,
        cancel_requested_at_utc=run.cancel_requested_at_utc,
        output_path=run.output_path,
        output_metadata=run.output_metadata,
        warnings=run.warnings,
        diagnostics=_run_diagnostics_response(run.diagnostics),
        errors=run.errors,
    )


def _erp_run_response(run: ErpRun) -> ErpRunResponse:
    return ErpRunResponse(
        run_id=run.run_id,
        dataset_id=run.dataset_id,
        run_kind=run.run_kind.value,
        schema_version=run.schema_version,
        config=ErpConfigPayload(**run.config.__dict__),
        status=run.status.value,
        started_at_utc=run.started_at_utc,
        finished_at_utc=run.finished_at_utc,
        cancel_requested_at_utc=run.cancel_requested_at_utc,
        output_path=run.output_path,
        output_metadata=run.output_metadata,
        warnings=run.warnings,
        diagnostics=_run_diagnostics_response(run.diagnostics),
        errors=run.errors,
    )


def _workflow_template_response(
    template: WorkflowTemplate,
) -> WorkflowTemplateResponse:
    validation = validate_workflow_template(template)
    return WorkflowTemplateResponse(
        schema_version=template.schema_version,
        template_kind=template.template_kind,
        template_id=template.template_id,
        name=template.name,
        description=template.description,
        created_at_utc=template.created_at_utc,
        updated_at_utc=template.updated_at_utc,
        created_from=WorkflowTemplateCreatedFromPayload(
            **asdict(template.created_from)
        ),
        compatibility=WorkflowTemplateCompatibilityPayload(
            **asdict(template.compatibility)
        ),
        workflow=_workflow_template_workflow_payload(template.workflow),
        field_policy=_workflow_template_field_policy_payload(template.field_policy),
        notes=template.notes,
        extra=template.extra,
        validation=WorkflowTemplateValidationResponse(
            valid=validation.valid,
            stale=validation.stale,
            errors=validation.errors,
            warnings=validation.warnings,
            stale_reasons=validation.stale_reasons,
        ),
    )


def _workflow_template_workflow_payload(
    workflow: WorkflowTemplateWorkflow,
) -> WorkflowTemplateWorkflowPayload:
    return WorkflowTemplateWorkflowPayload(
        preprocessing=(
            PreprocessingConfigPayload(**asdict(workflow.preprocessing))
            if workflow.preprocessing is not None
            else None
        ),
        epoch=(
            WorkflowTemplateEpochConfigPayload(**asdict(workflow.epoch))
            if workflow.epoch is not None
            else None
        ),
        erp=(
            WorkflowTemplateErpConfigPayload(**asdict(workflow.erp))
            if workflow.erp is not None
            else None
        ),
    )


def _workflow_template_field_policy_payload(
    field_policy: WorkflowTemplateFieldPolicy,
) -> WorkflowTemplateFieldPolicyPayload:
    return WorkflowTemplateFieldPolicyPayload(
        excluded_fields=[
            WorkflowTemplateFieldPolicyEntryPayload(**asdict(entry))
            for entry in field_policy.excluded_fields
        ],
        review_required_fields=[
            WorkflowTemplateFieldPolicyEntryPayload(**asdict(entry))
            for entry in field_policy.review_required_fields
        ],
        channel_specific_fields=field_policy.channel_specific_fields,
    )


def _batch_request_from_payload(request: BatchCreateRequest) -> BatchRequest:
    return BatchRequest(
        template_id=request.template_id,
        dataset_selection=BatchDatasetSelection(
            dataset_ids=list(request.dataset_selection.dataset_ids),
            project_id=request.dataset_selection.project_id,
            experiment_id=request.dataset_selection.experiment_id,
        ),
        requested_by=request.requested_by,
        continue_on_error=request.continue_on_error,
        dry_run=request.dry_run,
        metadata=dict(request.metadata),
    )


def _batch_apply_preview_for_planning(
    template: WorkflowTemplate,
    dataset: IngestionDataset,
) -> BatchApplyPreviewResult:
    preview = _workflow_template_apply_preview(
        template=template,
        request=WorkflowTemplateApplyPreviewRequest(
            target_dataset_id=dataset.dataset_id,
        ),
        dataset=dataset,
    )
    return BatchApplyPreviewResult(
        target_dataset_id=preview.target_dataset_id,
        status=preview.status,
        configs=_workflow_template_workflow_from_payload(preview.configs),
        excluded_fields=[
            WorkflowTemplateFieldPolicyEntry(**entry.model_dump())
            for entry in preview.excluded_fields
        ],
        review_required_fields=[
            WorkflowTemplateFieldPolicyEntry(**entry.model_dump())
            for entry in preview.review_required_fields
        ],
        errors=list(preview.errors),
        warnings=list(preview.warnings),
    )


def _batch_run_bindings_for_preview(dataset_id: str) -> BatchRunBindings:
    preprocessing_run = _preview_preprocessing_binding(
        dataset_id=dataset_id,
        requested_run_id=None,
    )
    epoch_run = _preview_epoch_binding(
        dataset_id=dataset_id,
        requested_run_id=None,
    )
    return BatchRunBindings(
        preprocessing_run_id=(
            preprocessing_run.run_id if preprocessing_run is not None else None
        ),
        epoch_run_id=epoch_run.run_id if epoch_run is not None else None,
    )


def _batch_run_plan_response(plan: BatchRunPlan) -> BatchRunPlanResponse:
    return BatchRunPlanResponse(
        schema_version=plan.schema_version,
        batch_id=plan.batch_id,
        status=plan.status.value,
        created_at_utc=plan.created_at_utc,
        updated_at_utc=plan.updated_at_utc,
        request=_batch_request_payload(plan.request),
        template_snapshot=_batch_template_snapshot_payload(plan.template_snapshot),
        items=[_batch_subject_run_plan_payload(item) for item in plan.items],
        warnings=plan.warnings,
        errors=plan.errors,
    )


def _batch_request_payload(request: BatchRequest) -> BatchRequestPayload:
    return BatchRequestPayload(
        template_id=request.template_id,
        dataset_selection=BatchDatasetSelectionPayload(
            dataset_ids=request.dataset_selection.dataset_ids,
            project_id=request.dataset_selection.project_id,
            experiment_id=request.dataset_selection.experiment_id,
        ),
        requested_by=request.requested_by,
        continue_on_error=request.continue_on_error,
        dry_run=request.dry_run,
        metadata=request.metadata,
    )


def _batch_template_snapshot_payload(
    snapshot: BatchTemplateSnapshot,
) -> BatchTemplateSnapshotPayload:
    return BatchTemplateSnapshotPayload(
        template_id=snapshot.template_id,
        template_name=snapshot.template_name,
        template_updated_at_utc=snapshot.template_updated_at_utc,
        captured_at_utc=snapshot.captured_at_utc,
        template_digest_sha256=snapshot.template_digest_sha256,
        template=_workflow_template_response(snapshot.template),
    )


def _batch_subject_run_plan_payload(
    item: BatchSubjectRunPlan,
) -> BatchSubjectRunPlanPayload:
    return BatchSubjectRunPlanPayload(
        item_id=item.item_id,
        dataset_id=item.dataset_id,
        status=item.status.value,
        attempt=item.attempt,
        retry_of_item_id=item.retry_of_item_id,
        configs=_workflow_template_workflow_payload(item.configs),
        bindings=BatchRunBindingsPayload(**asdict(item.bindings)),
        planned_steps=[step.value for step in item.planned_steps],
        run_ids=item.run_ids,
        previous_run_ids=item.previous_run_ids,
        previous_error=item.previous_error,
        excluded_fields=[
            WorkflowTemplateFieldPolicyEntryPayload(**asdict(entry))
            for entry in item.excluded_fields
        ],
        review_required_fields=[
            WorkflowTemplateFieldPolicyEntryPayload(**asdict(entry))
            for entry in item.review_required_fields
        ],
        warnings=item.warnings,
        errors=item.errors,
    )


def _workflow_template_from_request(
    *,
    request: WorkflowTemplateSaveRequest,
    template_id: str,
    created_at_utc: str,
    updated_at_utc: str,
) -> WorkflowTemplate:
    return WorkflowTemplate(
        template_id=template_id,
        name=request.name,
        description=request.description,
        created_at_utc=created_at_utc,
        updated_at_utc=updated_at_utc,
        created_from=WorkflowTemplateCreatedFrom(
            **request.created_from.model_dump()
        ),
        compatibility=WorkflowTemplateCompatibility(
            **request.compatibility.model_dump()
        ),
        workflow=_workflow_template_workflow_from_payload(request.workflow),
        field_policy=_workflow_template_field_policy_from_payload(
            request.field_policy
        ),
        notes=list(request.notes),
        extra=dict(request.extra),
    )


def _workflow_template_workflow_from_payload(
    payload: WorkflowTemplateWorkflowPayload,
) -> WorkflowTemplateWorkflow:
    return WorkflowTemplateWorkflow(
        preprocessing=(
            _preprocessing_config_from_payload(payload.preprocessing)
            if payload.preprocessing is not None
            else None
        ),
        epoch=(
            WorkflowTemplateEpochConfig(**payload.epoch.model_dump())
            if payload.epoch is not None
            else None
        ),
        erp=(
            WorkflowTemplateErpConfig(**payload.erp.model_dump())
            if payload.erp is not None
            else None
        ),
    )


def _workflow_template_field_policy_from_payload(
    payload: WorkflowTemplateFieldPolicyPayload,
) -> WorkflowTemplateFieldPolicy:
    return WorkflowTemplateFieldPolicy(
        excluded_fields=[
            WorkflowTemplateFieldPolicyEntry(**entry.model_dump())
            for entry in payload.excluded_fields
        ],
        review_required_fields=[
            WorkflowTemplateFieldPolicyEntry(**entry.model_dump())
            for entry in payload.review_required_fields
        ],
        channel_specific_fields=list(payload.channel_specific_fields),
    )


def _workflow_template_from_completed_runs(
    *,
    request: WorkflowTemplateFromRunRequest,
    template_id: str,
    created_at_utc: str,
    updated_at_utc: str,
) -> WorkflowTemplate:
    erp_run = (
        _completed_erp_run_or_error(request.erp_run_id)
        if request.erp_run_id
        else None
    )
    epoch_run_id = request.epoch_run_id
    if epoch_run_id is None and erp_run is not None:
        epoch_run_id = erp_run.config.epoch_run_id
    epoch_run = (
        _completed_epoch_run_or_error(epoch_run_id)
        if epoch_run_id
        else None
    )
    preprocessing_run_id = request.preprocessing_run_id
    if preprocessing_run_id is None and epoch_run is not None:
        preprocessing_run_id = epoch_run.config.preprocessing_run_id
    preprocessing_run = (
        _completed_preprocessing_run_or_error(preprocessing_run_id)
        if preprocessing_run_id
        else None
    )

    if erp_run is not None and epoch_run is not None:
        if erp_run.dataset_id != epoch_run.dataset_id:
            raise HTTPException(
                status_code=422,
                detail="ERP and epoch source runs must belong to the same dataset.",
            )
    if epoch_run is not None and preprocessing_run is not None:
        if epoch_run.dataset_id != preprocessing_run.dataset_id:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Epoch and preprocessing source runs must belong to the same "
                    "dataset."
                ),
            )

    workflow = WorkflowTemplateWorkflow(
        preprocessing=(
            _template_preprocessing_config_from_run(preprocessing_run)
            if preprocessing_run is not None
            else None
        ),
        epoch=(
            _template_epoch_config_from_run(epoch_run)
            if epoch_run is not None
            else None
        ),
        erp=(
            _template_erp_config_from_run(erp_run)
            if erp_run is not None
            else None
        ),
    )
    field_policy = _template_field_policy_from_source_runs(
        preprocessing_run=preprocessing_run,
        epoch_run=epoch_run,
        erp_run=erp_run,
    )
    created_from = WorkflowTemplateCreatedFrom(
        dataset_id=_template_source_dataset_id(
            preprocessing_run=preprocessing_run,
            epoch_run=epoch_run,
            erp_run=erp_run,
        ),
        preprocessing_run_id=preprocessing_run.run_id
        if preprocessing_run is not None
        else None,
        epoch_run_id=epoch_run.run_id if epoch_run is not None else None,
        erp_run_id=erp_run.run_id if erp_run is not None else None,
    )
    return WorkflowTemplate(
        template_id=template_id,
        name=request.name,
        description=request.description,
        created_at_utc=created_at_utc,
        updated_at_utc=updated_at_utc,
        created_from=created_from,
        compatibility=WorkflowTemplateCompatibility(
            requires_event_log=epoch_run is not None,
            requires_completed_preprocessing=False,
            requires_completed_epoch=False,
        ),
        workflow=workflow,
        field_policy=field_policy,
        notes=list(request.notes),
        extra=dict(request.extra),
    )


def _completed_preprocessing_run_or_error(run_id: str) -> PreprocessingRun:
    run = run_repository.get_preprocessing_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Preprocessing run not found")
    if run.status != PreprocessingRunStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail="Preprocessing run must be completed before template creation.",
        )
    return run


def _completed_epoch_run_or_error(run_id: str) -> EpochRun:
    run = run_repository.get_epoch_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Epoch run not found")
    if run.status != EpochRunStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail="Epoch run must be completed before template creation.",
        )
    return run


def _completed_erp_run_or_error(run_id: str) -> ErpRun:
    run = run_repository.get_erp_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="ERP run not found")
    if run.status != ErpRunStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail="ERP run must be completed before template creation.",
        )
    return run


def _template_preprocessing_config_from_run(
    run: PreprocessingRun,
) -> PreprocessingConfig:
    config = run.config
    return replace(
        config,
        manual_bad_channels=[],
        ica=replace(config.ica, exclude_components=[]),
    )


def _template_epoch_config_from_run(
    run: EpochRun,
) -> WorkflowTemplateEpochConfig:
    config = run.config
    return WorkflowTemplateEpochConfig(
        condition_field=config.condition_field,
        tmin_seconds=config.tmin_seconds,
        tmax_seconds=config.tmax_seconds,
        baseline_start_seconds=config.baseline_start_seconds,
        baseline_end_seconds=config.baseline_end_seconds,
        reject_eeg_uv=config.reject_eeg_uv,
    )


def _template_erp_config_from_run(
    run: ErpRun,
) -> WorkflowTemplateErpConfig:
    config = run.config
    return WorkflowTemplateErpConfig(
        conditions=list(config.conditions) if config.conditions is not None else None,
        picks=list(config.picks) if config.picks is not None else None,
        method=config.method,
        plot_mode=config.plot_mode,
        plot_channel=config.plot_channel,
    )


def _template_field_policy_from_source_runs(
    *,
    preprocessing_run: PreprocessingRun | None,
    epoch_run: EpochRun | None,
    erp_run: ErpRun | None,
) -> WorkflowTemplateFieldPolicy:
    excluded_fields: list[WorkflowTemplateFieldPolicyEntry] = []
    review_required_fields: list[WorkflowTemplateFieldPolicyEntry] = []
    channel_specific_fields: list[str] = []

    if preprocessing_run is not None:
        config = preprocessing_run.config
        if config.manual_bad_channels:
            excluded_fields.append(
                WorkflowTemplateFieldPolicyEntry(
                    path="workflow.preprocessing.manual_bad_channels",
                    reason="subject_specific",
                    source_value_summary=(
                        f"{len(config.manual_bad_channels)} channel(s) omitted "
                        "by default"
                    ),
                    default_action="omit",
                )
            )
        if config.ica.exclude_components:
            excluded_fields.append(
                WorkflowTemplateFieldPolicyEntry(
                    path="workflow.preprocessing.ica.exclude_components",
                    reason="subject_specific_review_decision",
                    source_value_summary=(
                        f"{len(config.ica.exclude_components)} component(s) omitted "
                        "by default"
                    ),
                    default_action="omit",
                )
            )
        for path, values in (
            ("workflow.preprocessing.ica.eog_channels", config.ica.eog_channels),
            ("workflow.preprocessing.ica.ecg_channels", config.ica.ecg_channels),
            (
                "workflow.preprocessing.artifact_handling.eog_channels",
                config.artifact_handling.eog_channels,
            ),
            (
                "workflow.preprocessing.artifact_handling.ecg_channels",
                config.artifact_handling.ecg_channels,
            ),
        ):
            if values:
                channel_specific_fields.append(path)
                review_required_fields.append(
                    WorkflowTemplateFieldPolicyEntry(
                        path=path,
                        reason="channel_specific",
                        source_value=list(values),
                        default_action="validate_against_target_channels",
                    )
                )

    if epoch_run is not None:
        excluded_fields.append(
            WorkflowTemplateFieldPolicyEntry(
                path="workflow.epoch.preprocessing_run_id",
                reason="source_run_binding",
                source_value=epoch_run.config.preprocessing_run_id,
                default_action="bind_at_apply_time",
            )
        )

    if erp_run is not None:
        excluded_fields.append(
            WorkflowTemplateFieldPolicyEntry(
                path="workflow.erp.epoch_run_id",
                reason="source_run_binding",
                source_value=erp_run.config.epoch_run_id,
                default_action="bind_at_apply_time",
            )
        )
        config = erp_run.config
        if config.picks:
            channel_specific_fields.append("workflow.erp.picks")
            review_required_fields.append(
                WorkflowTemplateFieldPolicyEntry(
                    path="workflow.erp.picks",
                    reason="channel_specific",
                    source_value=list(config.picks),
                    default_action="validate_against_target_channels",
                )
            )
        if config.plot_channel:
            channel_specific_fields.append("workflow.erp.plot_channel")
            review_required_fields.append(
                WorkflowTemplateFieldPolicyEntry(
                    path="workflow.erp.plot_channel",
                    reason="channel_specific",
                    source_value=config.plot_channel,
                    default_action="validate_against_target_channels",
                )
            )

    return WorkflowTemplateFieldPolicy(
        excluded_fields=excluded_fields,
        review_required_fields=review_required_fields,
        channel_specific_fields=list(dict.fromkeys(channel_specific_fields)),
    )


def _template_source_dataset_id(
    *,
    preprocessing_run: PreprocessingRun | None,
    epoch_run: EpochRun | None,
    erp_run: ErpRun | None,
) -> str | None:
    for run in (erp_run, epoch_run, preprocessing_run):
        if run is not None:
            return run.dataset_id
    return None


def _workflow_template_apply_preview(
    *,
    template: WorkflowTemplate,
    request: WorkflowTemplateApplyPreviewRequest,
    dataset: IngestionDataset,
) -> WorkflowTemplateApplyPreviewResponse:
    errors: list[str] = []
    warnings: list[str] = []
    template_validation = validate_workflow_template(template)
    errors.extend(template_validation.errors)
    warnings.extend(template_validation.warnings)

    workflow = template.workflow
    preprocessing_config = (
        _apply_subject_overrides_to_preprocessing_config(
            workflow.preprocessing,
            request.subject_overrides,
        )
        if workflow.preprocessing is not None
        else None
    )
    recording = registry_repository.get_recording(dataset.dataset_id)
    event_log = registry_repository.get_event_log(dataset.dataset_id)
    preprocessing_run = _preview_preprocessing_binding(
        dataset_id=dataset.dataset_id,
        requested_run_id=request.preprocessing_run_id,
    )
    epoch_run = _preview_epoch_binding(
        dataset_id=dataset.dataset_id,
        requested_run_id=request.epoch_run_id,
    )

    if preprocessing_config is not None:
        if recording is None:
            errors.append("Recording metadata is required before preprocessing.")
        else:
            errors.extend(_validate_preprocessing_config(preprocessing_config, recording))

    if workflow.epoch is not None:
        epoch_errors, epoch_warnings = _validate_template_epoch_preview(
            config=workflow.epoch,
            dataset=dataset,
            preprocessing_run=preprocessing_run,
            event_log=event_log,
            recording=recording,
            has_planned_preprocessing=preprocessing_config is not None,
        )
        errors.extend(epoch_errors)
        warnings.extend(epoch_warnings)

    if workflow.erp is not None:
        erp_errors, erp_warnings = _validate_template_erp_preview(
            config=workflow.erp,
            dataset_id=dataset.dataset_id,
            epoch_run=epoch_run,
            has_planned_epoch=workflow.epoch is not None,
            recording=recording,
        )
        errors.extend(erp_errors)
        warnings.extend(erp_warnings)

    review_required = list(template.field_policy.review_required_fields)
    stale_reasons = list(template_validation.stale_reasons)
    if errors:
        status_value = "invalid"
    elif review_required or stale_reasons:
        status_value = "requires_review"
    else:
        status_value = "ready"

    return WorkflowTemplateApplyPreviewResponse(
        template_id=template.template_id,
        target_dataset_id=dataset.dataset_id,
        status=status_value,
        configs=_workflow_template_workflow_payload(
            WorkflowTemplateWorkflow(
                preprocessing=preprocessing_config,
                epoch=workflow.epoch,
                erp=workflow.erp,
            )
        ),
        excluded_fields=[
            WorkflowTemplateFieldPolicyEntryPayload(**asdict(entry))
            for entry in template.field_policy.excluded_fields
        ],
        review_required_fields=[
            WorkflowTemplateFieldPolicyEntryPayload(**asdict(entry))
            for entry in review_required
        ],
        errors=_unique_strings(errors),
        warnings=_unique_strings(warnings),
    )


def _apply_subject_overrides_to_preprocessing_config(
    config: PreprocessingConfig | None,
    overrides: WorkflowTemplateSubjectOverridesPayload,
) -> PreprocessingConfig | None:
    if config is None:
        return None
    return replace(
        config,
        manual_bad_channels=list(overrides.manual_bad_channels),
        ica=replace(
            config.ica,
            exclude_components=list(overrides.ica_exclude_components),
        ),
    )


def _preview_preprocessing_binding(
    *,
    dataset_id: str,
    requested_run_id: str | None,
) -> PreprocessingRun | None:
    if requested_run_id:
        return run_repository.get_preprocessing_run(requested_run_id)
    completed_runs = [
        run
        for run in run_repository.list_preprocessing_runs(dataset_id=dataset_id)
        if run.status == PreprocessingRunStatus.COMPLETED
    ]
    return _latest_completed_run(completed_runs)


def _preview_epoch_binding(
    *,
    dataset_id: str,
    requested_run_id: str | None,
) -> EpochRun | None:
    if requested_run_id:
        return run_repository.get_epoch_run(requested_run_id)
    completed_runs = [
        run
        for run in run_repository.list_epoch_runs(dataset_id=dataset_id)
        if run.status == EpochRunStatus.COMPLETED
    ]
    return _latest_completed_run(completed_runs)


def _latest_completed_run(
    runs: list[PreprocessingRun] | list[EpochRun],
) -> PreprocessingRun | EpochRun | None:
    if not runs:
        return None
    return sorted(runs, key=lambda run: run.finished_at_utc or run.run_id)[-1]


def _validate_template_epoch_preview(
    *,
    config: WorkflowTemplateEpochConfig,
    dataset: IngestionDataset,
    preprocessing_run: PreprocessingRun | None,
    event_log: EventLog | None,
    recording: Recording | None,
    has_planned_preprocessing: bool,
) -> tuple[list[str], list[str]]:
    if preprocessing_run is not None:
        return _validate_epoch_config(
            config=EpochConfig(
                preprocessing_run_id=preprocessing_run.run_id,
                condition_field=config.condition_field,
                tmin_seconds=config.tmin_seconds,
                tmax_seconds=config.tmax_seconds,
                baseline_start_seconds=config.baseline_start_seconds,
                baseline_end_seconds=config.baseline_end_seconds,
                reject_eeg_uv=config.reject_eeg_uv,
            ),
            dataset=dataset,
            preprocessing_run=preprocessing_run,
            event_log=event_log,
            recording=recording,
        )

    errors, warnings = _validate_template_epoch_config_basics(
        config=config,
        dataset=dataset,
        event_log=event_log,
        recording=recording,
    )
    if has_planned_preprocessing and not errors:
        warnings.append(
            "Epoch run binding will be resolved after template preprocessing completes."
        )
    elif not errors:
        errors.append(
            "A completed preprocessing run is required before applying epoch config."
        )
    return errors, warnings


def _validate_template_epoch_config_basics(
    *,
    config: WorkflowTemplateEpochConfig,
    dataset: IngestionDataset,
    event_log: EventLog | None,
    recording: Recording | None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if dataset.status != DatasetStatus.VALID:
        errors.append("Dataset must be valid before epoching.")
    if event_log is None or not event_log.events:
        errors.append("Dataset must have mapped events before epoching.")
    if recording is None:
        errors.append("Recording metadata is required before epoching.")
    if config.tmin_seconds >= config.tmax_seconds:
        errors.append("tmin_seconds must be lower than tmax_seconds.")
    if config.tmax_seconds <= 0:
        errors.append("tmax_seconds must be greater than 0.")
    errors.extend(
        _validate_epoch_baseline(
            EpochConfig(
                preprocessing_run_id="preview",
                condition_field=config.condition_field,
                tmin_seconds=config.tmin_seconds,
                tmax_seconds=config.tmax_seconds,
                baseline_start_seconds=config.baseline_start_seconds,
                baseline_end_seconds=config.baseline_end_seconds,
                reject_eeg_uv=config.reject_eeg_uv,
            )
        )
    )
    if config.condition_field not in SUPPORTED_CONDITION_FIELDS:
        errors.append(f"Unsupported condition field: {config.condition_field}.")
    if config.reject_eeg_uv is not None and config.reject_eeg_uv <= 0:
        errors.append("reject_eeg_uv must be greater than 0.")
    if errors:
        return errors, warnings

    assert event_log is not None
    candidate_events = [
        event
        for event in event_log.events
        if _epoch_condition_label(getattr(event, config.condition_field)) is not None
    ]
    if not candidate_events:
        return [
            f"No usable events found for condition field: {config.condition_field}."
        ], warnings
    assert recording is not None
    out_of_bounds_count = 0
    for event in candidate_events:
        start_seconds = event.onset_seconds + config.tmin_seconds
        end_seconds = event.onset_seconds + config.tmax_seconds
        if start_seconds < 0 or end_seconds > recording.metadata.duration_seconds:
            out_of_bounds_count += 1
    if out_of_bounds_count == len(candidate_events):
        return ["All candidate epoch windows are outside the recording bounds."], warnings
    if out_of_bounds_count:
        warnings.append(
            f"{out_of_bounds_count} candidate events fall outside the epoch window bounds and will be skipped."
        )
    return errors, warnings


def _validate_template_erp_preview(
    *,
    config: WorkflowTemplateErpConfig,
    dataset_id: str,
    epoch_run: EpochRun | None,
    has_planned_epoch: bool,
    recording: Recording | None,
) -> tuple[list[str], list[str]]:
    if epoch_run is not None:
        return _validate_erp_config(
            config=ErpConfig(
                epoch_run_id=epoch_run.run_id,
                conditions=config.conditions,
                picks=config.picks,
                method=config.method,
                plot_mode=config.plot_mode,
                plot_channel=config.plot_channel,
            ),
            dataset_id=dataset_id,
            epoch_run=epoch_run,
        )

    errors, warnings = _validate_template_erp_config_basics(
        config=config,
        recording=recording,
    )
    if has_planned_epoch and not errors:
        warnings.append(
            "ERP run binding will be resolved after template epoching completes."
        )
    elif not errors:
        errors.append("A completed epoch run is required before applying ERP config.")
    return errors, warnings


def _validate_template_erp_config_basics(
    *,
    config: WorkflowTemplateErpConfig,
    recording: Recording | None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if config.method != "mean":
        errors.append("ERP method must be 'mean'.")
    if config.plot_mode not in {"gfp", "channel"}:
        errors.append("ERP plot_mode must be 'gfp' or 'channel'.")
    if config.plot_mode == "channel" and not config.plot_channel:
        errors.append("ERP plot_channel is required when plot_mode is 'channel'.")
    if config.conditions is not None:
        conditions = [condition.strip() for condition in config.conditions]
        if not all(conditions):
            errors.append("ERP condition labels must not be empty.")
        if len(set(conditions)) != len(conditions):
            errors.append("ERP condition labels must be unique.")
    channel_names = set(recording.metadata.channel_names) if recording is not None else set()
    if config.picks is not None:
        picks = [pick.strip() for pick in config.picks]
        if not all(picks):
            errors.append("ERP picks must not be empty.")
        if len(set(picks)) != len(picks):
            errors.append("ERP picks must be unique.")
        if channel_names:
            missing = [pick for pick in picks if pick not in channel_names]
            if missing:
                errors.append("ERP picks contain unknown channels: " + ", ".join(missing))
    if config.plot_channel and channel_names and config.plot_channel not in channel_names:
        errors.append(
            "ERP plot_channel contains an unknown channel: " + config.plot_channel
        )
    return errors, warnings


def _unique_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _run_diagnostics_response(diagnostics: dict) -> RunDiagnosticsResponse | dict:
    warnings = diagnostics.get("warnings") if isinstance(diagnostics, dict) else None
    if not warnings:
        return {}
    return RunDiagnosticsResponse(
        warnings=[
            DiagnosticWarningResponse(
                severity=_diagnostic_warning_field(warning, "severity"),
                source=_diagnostic_warning_field(warning, "source"),
                code=_diagnostic_warning_field(warning, "code"),
                impact=_diagnostic_warning_optional_field(warning, "impact"),
                suggested_action=_diagnostic_warning_optional_field(
                    warning,
                    "suggested_action",
                ),
            )
            for warning in warnings
        ]
    )


def _diagnostic_warning_field(warning: object, field_name: str) -> str:
    value = _diagnostic_warning_optional_field(warning, field_name)
    if isinstance(value, ValidationSeverity):
        return value.value
    if field_name == "severity":
        try:
            return ValidationSeverity(str(value)).value
        except ValueError:
            return ValidationSeverity.WARNING.value
    if field_name == "source":
        return diagnostic_warning_source_from_value(value).value
    return str(value) if value is not None else ""


def _diagnostic_warning_optional_field(
    warning: object,
    field_name: str,
) -> object | None:
    if isinstance(warning, dict):
        return warning.get(field_name)
    return getattr(warning, field_name, None)


def _epoch_input_provenance(
    preprocessing_run: PreprocessingRun,
    event_log: EventLog | None,
    recording: Recording | None,
) -> dict[str, str | int | float | bool | None]:
    input_path = _resolve_preprocessing_output_path(preprocessing_run)
    return {
        "input_preprocessing_run_id": preprocessing_run.run_id,
        "input_preprocessed_path": str(input_path)
        if input_path is not None
        else preprocessing_run.output_path,
        "input_sampling_rate_hz": _epoch_output_sampling_rate_hz(
            preprocessing_run=preprocessing_run,
            recording=recording,
        ),
        "input_duration_seconds": _epoch_output_duration_seconds(
            preprocessing_run=preprocessing_run,
            recording=recording,
        ),
        "event_log_id": event_log.event_log_id if event_log is not None else None,
        "event_count": len(event_log.events) if event_log is not None else 0,
        "recording_id": recording.recording_id if recording is not None else None,
        "input_channel_count": recording.metadata.channel_count
        if recording is not None
        else None,
    }


def _erp_input_provenance(
    epoch_run: EpochRun,
) -> dict[str, str | int | float | bool | None]:
    input_path = _resolve_epoch_output_path(epoch_run)
    return {
        "input_epoch_run_id": epoch_run.run_id,
        "input_epochs_path": str(input_path)
        if input_path is not None
        else epoch_run.output_path,
        "input_preprocessing_run_id": epoch_run.output_metadata.get(
            "input_preprocessing_run_id"
        ),
        "input_condition_count": epoch_run.output_metadata.get("condition_count"),
        "input_epoch_count": epoch_run.output_metadata.get("epoch_count"),
        "input_sampling_rate_hz": epoch_run.output_metadata.get(
            "output_sampling_rate_hz"
        ),
        "input_channel_count": epoch_run.output_metadata.get("output_channel_count"),
    }


def _epoch_completed_provenance(
    run: EpochRun,
    output_path: Path,
    processing_metadata: dict,
) -> dict[str, str | int | float | bool | None]:
    diagnostics_metadata = _write_epoch_diagnostics(
        output_directory=output_path.parent,
        processing_metadata=processing_metadata,
        run=run,
    )
    artifact_entries = [
        _artifact_manifest_entry(
            logical_name="epochs",
            path=output_path,
            artifact_type="primary_fif",
            output_directory=output_path.parent,
        ),
        *[
            _artifact_manifest_entry(
                logical_name=logical_name,
                path=Path(str(path_value)),
                artifact_type="diagnostic_json",
                output_directory=output_path.parent,
            )
            for logical_name, path_value in (
                ("epoch_summary", diagnostics_metadata.get("epoch_summary_path")),
                (
                    "condition_counts",
                    diagnostics_metadata.get("condition_counts_path"),
                ),
                ("drop_log", diagnostics_metadata.get("drop_log_path")),
            )
            if isinstance(path_value, str) and Path(path_value).is_file()
        ],
    ]
    provenance_path = _write_run_provenance(
        output_directory=output_path.parent,
        run_id=run.run_id,
        dataset_id=run.dataset_id,
        run_kind=run.run_kind.value,
        config_snapshot=_epoch_config_payload(run.config),
        sources=_epoch_provenance_sources(run, processing_metadata),
        artifacts=artifact_entries,
        software_versions=_software_versions(processing_metadata),
    )
    artifact_entries.append(
        _artifact_manifest_entry(
            logical_name="provenance",
            path=provenance_path,
            artifact_type="provenance_json",
            output_directory=output_path.parent,
        )
    )
    manifest_metadata = _write_artifact_manifest(
        output_directory=output_path.parent,
        artifacts=artifact_entries,
    )
    output_size_bytes = output_path.stat().st_size
    output_checksum_sha256 = _sha256_file(output_path)
    return {
        **run.output_metadata,
        "artifact_root": str(output_path.parent),
        "primary_artifact_path": str(output_path),
        "primary_artifact_size_bytes": output_size_bytes,
        "primary_artifact_checksum_sha256": output_checksum_sha256,
        "artifact_count": manifest_metadata["artifact_count"],
        "artifact_manifest_path": manifest_metadata["artifact_manifest_path"],
        "provenance_available": True,
        "provenance_path": str(provenance_path),
        "provenance_schema_version": 1,
        "output_path": str(output_path),
        "output_size_bytes": output_size_bytes,
        "output_checksum_sha256": output_checksum_sha256,
        "output_file_format": processing_metadata["file_format"],
        "output_channel_count": processing_metadata["channel_count"],
        "output_sampling_rate_hz": processing_metadata["sampling_rate_hz"],
        "output_duration_seconds": processing_metadata["duration_seconds"],
        "mne_version": processing_metadata["mne_version"],
        "input_preprocessing_run_id": processing_metadata[
            "input_preprocessing_run_id"
        ],
        "condition_count": processing_metadata["condition_count"],
        "event_count_total": processing_metadata["event_count_total"],
        "event_count_used": processing_metadata["event_count_used"],
        "event_count_skipped": processing_metadata["event_count_skipped"],
        "epoch_count": processing_metadata["epoch_count"],
        "dropped_epoch_count": processing_metadata["dropped_epoch_count"],
        **diagnostics_metadata,
    }


def _erp_completed_provenance(
    run: ErpRun,
    output_path: Path,
    processing_metadata: dict,
) -> dict[str, str | int | float | bool | None]:
    metadata_path = _write_erp_metadata(
        output_path=output_path,
        processing_metadata=processing_metadata,
        run=run,
    )
    condition_artifacts = [
        _artifact_manifest_entry(
            logical_name=f"evoked_{item['safe_condition']}",
            path=Path(str(item["evoked_path"])),
            artifact_type="evoked_fif",
            output_directory=output_path.parent,
        )
        for item in processing_metadata.get("conditions", [])
        if isinstance(item, dict)
        and isinstance(item.get("safe_condition"), str)
        and isinstance(item.get("evoked_path"), str)
    ]
    plot_artifacts = [
        _artifact_manifest_entry(
            logical_name=f"{plot_kind}_{item['safe_condition']}",
            path=Path(str(path_value)),
            artifact_type=f"{plot_kind}_plot",
            output_directory=output_path.parent,
        )
        for item in processing_metadata.get("conditions", [])
        if isinstance(item, dict) and isinstance(item.get("safe_condition"), str)
        for plot_kind, path_value in (
            ("png", item.get("plot_png_path")),
            ("svg", item.get("plot_svg_path")),
        )
        if isinstance(path_value, str) and Path(path_value).is_file()
    ]
    artifact_entries = [
        *condition_artifacts,
        *plot_artifacts,
        _artifact_manifest_entry(
            logical_name="erp_metadata",
            path=metadata_path,
            artifact_type="metadata_json",
            output_directory=output_path.parent,
        ),
    ]
    provenance_path = _write_run_provenance(
        output_directory=output_path.parent,
        run_id=run.run_id,
        dataset_id=run.dataset_id,
        run_kind=run.run_kind.value,
        config_snapshot=_erp_config_payload(run.config),
        sources=_erp_provenance_sources(run, processing_metadata),
        artifacts=artifact_entries,
        software_versions=_software_versions(processing_metadata),
    )
    artifact_entries.append(
        _artifact_manifest_entry(
            logical_name="provenance",
            path=provenance_path,
            artifact_type="provenance_json",
            output_directory=output_path.parent,
        )
    )
    manifest_metadata = _write_artifact_manifest(
        output_directory=output_path.parent,
        artifacts=artifact_entries,
    )
    return {
        **run.output_metadata,
        "artifact_root": str(output_path.parent),
        "primary_artifact_path": str(output_path),
        "artifact_count": manifest_metadata["artifact_count"],
        "artifact_manifest_path": manifest_metadata["artifact_manifest_path"],
        "provenance_available": True,
        "provenance_path": str(provenance_path),
        "provenance_schema_version": 1,
        "output_path": str(output_path),
        "output_file_format": processing_metadata["file_format"],
        "mne_version": processing_metadata["mne_version"],
        "input_epoch_run_id": processing_metadata["input_epoch_run_id"],
        "input_epochs_path": processing_metadata["input_epochs_path"],
        "condition_count": processing_metadata["condition_count"],
        "evoked_count": processing_metadata["evoked_count"],
        "plot_count": processing_metadata.get("plot_count", 0),
        "plot_status": processing_metadata.get("plot_status", "unknown"),
        **_erp_preview_plot_metadata(run.run_id, processing_metadata),
        "erp_metadata_path": str(metadata_path),
        "erp_metadata_available": True,
    }


def _write_erp_metadata(
    output_path: Path,
    processing_metadata: dict,
    run: ErpRun,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path = output_path
    payload = processing_metadata.get("metadata")
    if not isinstance(payload, dict):
        payload = {
            "schema_version": 1,
            "conditions": processing_metadata.get("conditions", []),
            "warnings": processing_metadata.get("warnings", []),
        }
    payload = {
        "run_id": run.run_id,
        "dataset_id": run.dataset_id,
        **payload,
    }
    _write_json_file(metadata_path, payload)
    return metadata_path


def _write_run_provenance(
    *,
    output_directory: Path,
    run_id: str,
    dataset_id: str,
    run_kind: str,
    config_snapshot: dict,
    sources: list[dict],
    artifacts: list[dict[str, str | int]],
    software_versions: dict[str, str],
) -> Path:
    provenance_path = output_directory / "provenance.json"
    payload = build_provenance_payload(
        run_id=run_id,
        dataset_id=dataset_id,
        run_kind=run_kind,
        config_snapshot=config_snapshot,
        sources=sources,
        artifacts=[
            _provenance_artifact_summary(artifact)
            for artifact in artifacts
        ],
        software_versions=software_versions,
        created_at_utc=_utc_now_iso(),
    )
    _write_json_file(provenance_path, payload)
    return provenance_path


def _preprocessing_provenance_sources(run: PreprocessingRun) -> list[dict]:
    metadata = run.output_metadata
    return [
        {
            "role": "eeg_file",
            "file_id": metadata.get("input_file_id"),
            "original_filename": metadata.get("input_original_filename"),
            "path": metadata.get("input_path"),
            "size_bytes": metadata.get("input_size_bytes"),
            "checksum_sha256": metadata.get("input_checksum_sha256"),
            "file_format": metadata.get("input_file_format"),
        }
    ]


def _epoch_provenance_sources(
    run: EpochRun,
    processing_metadata: dict,
) -> list[dict]:
    metadata = run.output_metadata
    return [
        {
            "role": "preprocessing_run",
            "run_id": processing_metadata.get("input_preprocessing_run_id")
            or metadata.get("input_preprocessing_run_id"),
            "path": metadata.get("input_preprocessed_path"),
        },
        {
            "role": "event_log",
            "event_log_id": metadata.get("event_log_id"),
            "event_count": metadata.get("event_count"),
        },
        {
            "role": "recording",
            "recording_id": metadata.get("recording_id"),
        },
    ]


def _erp_provenance_sources(
    run: ErpRun,
    processing_metadata: dict,
) -> list[dict]:
    metadata = run.output_metadata
    return [
        {
            "role": "epoch_run",
            "run_id": processing_metadata.get("input_epoch_run_id")
            or metadata.get("input_epoch_run_id"),
            "path": processing_metadata.get("input_epochs_path")
            or metadata.get("input_epochs_path"),
        },
        {
            "role": "preprocessing_run",
            "run_id": metadata.get("input_preprocessing_run_id"),
        },
    ]


def _software_versions(processing_metadata: dict) -> dict[str, str]:
    versions = {"python": sys.version.split()[0]}
    mne_version = processing_metadata.get("mne_version")
    if isinstance(mne_version, str) and mne_version:
        versions["mne"] = mne_version
    return versions


def _provenance_artifact_summary(artifact: dict[str, str | int]) -> dict:
    return {
        "logical_name": artifact.get("logical_name"),
        "artifact_type": artifact.get("artifact_type"),
        "path": artifact.get("path"),
        "size_bytes": artifact.get("size_bytes"),
        "checksum_sha256": artifact.get("checksum_sha256"),
    }


def _erp_preview_plot_metadata(
    run_id: str,
    processing_metadata: dict,
) -> dict[str, str | int | float | bool | None]:
    conditions = processing_metadata.get("conditions")
    if not isinstance(conditions, list):
        return {
            "preview_plot_path": None,
            "preview_plot_filename": None,
            "preview_plot_url": None,
            "preview_plot_condition": None,
            "preview_plot_mode": None,
            "preview_plot_channel": None,
        }

    labels: list[str] = []
    for item in conditions:
        if isinstance(item, dict) and isinstance(item.get("condition"), str):
            labels.append(str(item["condition"]))
    for item in conditions:
        if not isinstance(item, dict):
            continue
        plot_path = item.get("plot_png_path")
        if not isinstance(plot_path, str) or not Path(plot_path).is_file():
            continue
        filename = Path(plot_path).name
        return {
            "condition_labels": ",".join(labels),
            "preview_plot_path": plot_path,
            "preview_plot_filename": filename,
            "preview_plot_url": f"/artifacts/{run_id}/{filename}",
            "preview_plot_condition": item.get("condition"),
            "preview_plot_mode": item.get("plot_mode"),
            "preview_plot_channel": item.get("plot_channel"),
        }

    return {
        "condition_labels": ",".join(labels),
        "preview_plot_path": None,
        "preview_plot_filename": None,
        "preview_plot_url": None,
        "preview_plot_condition": None,
        "preview_plot_mode": None,
        "preview_plot_channel": None,
    }


def _comparison_completed_metadata(
    run: ErpRun,
    summary_path: Path,
    summary: dict,
) -> dict[str, str | int | float | bool | None]:
    manifest_metadata = _append_artifact_manifest_entry(
        output_directory=summary_path.parent,
        entry=_artifact_manifest_entry(
            logical_name="comparison_summary",
            path=summary_path,
            artifact_type="comparison_json",
            output_directory=summary_path.parent,
        ),
    )
    condition_a = summary.get("conditions", {}).get("a", {})
    condition_b = summary.get("conditions", {}).get("b", {})
    difference = summary.get("difference", {})
    target = summary.get("target", {})
    window = summary.get("window", {})
    statistics = summary.get("statistics", {})
    statistics_result = (
        statistics.get("result") if isinstance(statistics, dict) else None
    )
    return {
        **run.output_metadata,
        "artifact_count": manifest_metadata["artifact_count"],
        "artifact_manifest_path": manifest_metadata["artifact_manifest_path"],
        "comparison_available": True,
        "comparison_summary_path": str(summary_path),
        "comparison_summary_url": f"/artifacts/{run.run_id}/{summary_path.name}",
        "comparison_metric": summary.get("metric"),
        "comparison_condition_a": condition_a.get("label"),
        "comparison_condition_b": condition_b.get("label"),
        "comparison_target_type": target.get("type"),
        "comparison_target_channel": target.get("channel"),
        "comparison_window_start_seconds": window.get("start_seconds"),
        "comparison_window_end_seconds": window.get("end_seconds"),
        "comparison_mean_a_uv": condition_a.get("mean_amplitude_uv"),
        "comparison_mean_b_uv": condition_b.get("mean_amplitude_uv"),
        "comparison_difference_uv": difference.get("mean_amplitude_uv"),
        "comparison_statistics_implemented": (
            statistics.get("implemented") if isinstance(statistics, dict) else False
        ),
        "comparison_statistics_status": (
            statistics.get("status") if isinstance(statistics, dict) else None
        ),
        "comparison_statistics_method": (
            statistics.get("method") if isinstance(statistics, dict) else None
        ),
        "comparison_statistics_p_value": (
            statistics_result.get("p_value")
            if isinstance(statistics_result, dict)
            else None
        ),
        "comparison_statistics_effect_size": (
            statistics_result.get("effect_size", {}).get("value")
            if isinstance(statistics_result, dict)
            and isinstance(statistics_result.get("effect_size"), dict)
            else None
        ),
    }


def _write_epoch_diagnostics(
    output_directory: Path,
    processing_metadata: dict,
    run: EpochRun,
) -> dict[str, str | int | float | bool | None]:
    diagnostics = processing_metadata.get("diagnostics")
    if not isinstance(diagnostics, dict):
        return {
            "diagnostics_available": False,
            "diagnostics_file_count": 0,
        }

    output_directory.mkdir(parents=True, exist_ok=True)
    files = {
        "epoch_summary": output_directory / "epoch_summary.json",
        "condition_counts": output_directory / "condition_counts.json",
        "drop_log": output_directory / "drop_log.json",
    }
    written_paths: dict[str, Path] = {}
    for key, path in files.items():
        payload = diagnostics.get(key)
        if isinstance(payload, (dict, list)):
            if key == "epoch_summary" and isinstance(payload, dict):
                payload = {
                    "run_id": run.run_id,
                    "dataset_id": run.dataset_id,
                    **payload,
                }
            serializable_payload = (
                {"entries": payload} if isinstance(payload, list) else payload
            )
            _write_json_file(path, serializable_payload)
            written_paths[key] = path

    return {
        "diagnostics_available": bool(written_paths),
        "diagnostics_file_count": len(written_paths),
        "diagnostics_directory": str(output_directory),
        "epoch_summary_path": str(written_paths.get("epoch_summary"))
        if "epoch_summary" in written_paths
        else None,
        "condition_counts_path": str(written_paths.get("condition_counts"))
        if "condition_counts" in written_paths
        else None,
        "drop_log_path": str(written_paths.get("drop_log"))
        if "drop_log" in written_paths
        else None,
    }


def _preprocessing_input_provenance(
    uploaded_file: IngestionUploadedFile,
    recording: Recording,
) -> dict[str, str | int | float | bool | None]:
    return {
        "input_file_id": uploaded_file.file_id,
        "input_original_filename": uploaded_file.original_filename,
        "input_path": uploaded_file.stored_path,
        "input_size_bytes": uploaded_file.size_bytes,
        "input_checksum_sha256": uploaded_file.checksum_sha256,
        "input_file_format": recording.metadata.file_format,
        "input_channel_count": recording.metadata.channel_count,
        "input_sampling_rate_hz": recording.metadata.sampling_rate_hz,
        "input_duration_seconds": recording.metadata.duration_seconds,
        "input_channel_names": ",".join(recording.metadata.channel_names),
    }


def _preprocessing_completed_provenance(
    run: PreprocessingRun,
    output_path: Path,
    processing_metadata: dict,
) -> dict[str, str | int | float | bool | None]:
    diagnostics_metadata = _write_preprocessing_diagnostics(
        output_directory=output_path.parent,
        processing_metadata=processing_metadata,
    )
    artifact_entries = [
        _artifact_manifest_entry(
            logical_name="raw_preprocessed",
            path=output_path,
            artifact_type="primary_fif",
            output_directory=output_path.parent,
        ),
        *[
            _artifact_manifest_entry(
                logical_name=logical_name,
                path=Path(str(path_value)),
                artifact_type="diagnostic_json",
                output_directory=output_path.parent,
            )
            for logical_name, path_value in (
                (
                    "preprocessing_summary",
                    diagnostics_metadata.get("preprocessing_summary_path"),
                ),
                ("filter_report", diagnostics_metadata.get("filter_report_path")),
                (
                    "artifact_summary",
                    diagnostics_metadata.get("artifact_summary_path"),
                ),
                (
                    "bad_channel_report",
                    diagnostics_metadata.get("bad_channel_report_path"),
                ),
                (
                    "artifact_rejection_report",
                    diagnostics_metadata.get("artifact_rejection_report_path"),
                ),
                ("ica_report", diagnostics_metadata.get("ica_report_path")),
                (
                    "before_after_qc",
                    diagnostics_metadata.get("before_after_qc_path"),
                ),
            )
            if isinstance(path_value, str) and Path(path_value).is_file()
        ],
    ]
    provenance_path = _write_run_provenance(
        output_directory=output_path.parent,
        run_id=run.run_id,
        dataset_id=run.dataset_id,
        run_kind=run.run_kind.value,
        config_snapshot=_preprocessing_config_payload(run.config),
        sources=_preprocessing_provenance_sources(run),
        artifacts=artifact_entries,
        software_versions=_software_versions(processing_metadata),
    )
    artifact_entries.append(
        _artifact_manifest_entry(
            logical_name="provenance",
            path=provenance_path,
            artifact_type="provenance_json",
            output_directory=output_path.parent,
        )
    )
    manifest_metadata = _write_artifact_manifest(
        output_directory=output_path.parent,
        artifacts=artifact_entries,
    )
    output_size_bytes = output_path.stat().st_size
    output_checksum_sha256 = _sha256_file(output_path)
    return {
        **run.output_metadata,
        "artifact_root": str(output_path.parent),
        "primary_artifact_path": str(output_path),
        "primary_artifact_size_bytes": output_size_bytes,
        "primary_artifact_checksum_sha256": output_checksum_sha256,
        "artifact_count": manifest_metadata["artifact_count"],
        "artifact_manifest_path": manifest_metadata["artifact_manifest_path"],
        "provenance_available": True,
        "provenance_path": str(provenance_path),
        "provenance_schema_version": 1,
        "output_path": str(output_path),
        "output_size_bytes": output_size_bytes,
        "output_checksum_sha256": output_checksum_sha256,
        "output_file_format": processing_metadata["file_format"],
        "output_channel_count": processing_metadata["channel_count"],
        "output_sampling_rate_hz": processing_metadata["sampling_rate_hz"],
        "output_duration_seconds": processing_metadata["duration_seconds"],
        "mne_version": processing_metadata["mne_version"],
        **diagnostics_metadata,
    }


def _write_preprocessing_diagnostics(
    output_directory: Path,
    processing_metadata: dict,
) -> dict[str, str | int | float | bool | None]:
    diagnostics = processing_metadata.get("diagnostics")
    if not isinstance(diagnostics, dict):
        return {
            "diagnostics_available": False,
            "diagnostics_file_count": 0,
        }

    output_directory.mkdir(parents=True, exist_ok=True)
    artifact_summary = diagnostics.get("artifact_summary")
    artifact_summary_payload = (
        artifact_summary if isinstance(artifact_summary, dict) else {}
    )
    qc_summary_payload = (
        artifact_summary_payload.get("qc", {})
        if isinstance(artifact_summary_payload, dict)
        else {}
    )
    files = {
        "preprocessing_summary": (
            output_directory / "preprocessing_summary.json",
            diagnostics.get("preprocessing_summary"),
        ),
        "filter_report": (
            output_directory / "filter_report.json",
            diagnostics.get("filter_report"),
        ),
        "artifact_summary": (
            output_directory / "artifact_summary.json",
            artifact_summary_payload,
        ),
        "bad_channel_report": (
            output_directory / "bad_channel_report.json",
            artifact_summary_payload.get("bad_channels", {}),
        ),
        "artifact_rejection_report": (
            output_directory / "artifact_rejection_report.json",
            artifact_summary_payload.get("artifact_rejection", {}),
        ),
        "ica_report": (
            output_directory / "ica_report.json",
            artifact_summary_payload.get("ica", {}),
        ),
        "before_after_qc": (
            output_directory / "before_after_qc.json",
            qc_summary_payload.get("before_after", {})
            if isinstance(qc_summary_payload, dict)
            else {},
        ),
    }
    written_paths: dict[str, Path] = {}
    for key, (path, payload) in files.items():
        if isinstance(payload, dict):
            _write_json_file(path, payload)
            written_paths[key] = path

    output_artifacts = (
        artifact_summary.get("output", {})
        if isinstance(artifact_summary, dict)
        else {}
    )
    bad_channels = (
        artifact_summary.get("bad_channels", {})
        if isinstance(artifact_summary, dict)
        else {}
    )
    bad_channel_detection = (
        bad_channels.get("detection", {})
        if isinstance(bad_channels, dict)
        else {}
    )
    bad_channel_interpolation = (
        bad_channels.get("interpolation", {})
        if isinstance(bad_channels, dict)
        else {}
    )
    artifact_rejection = (
        artifact_summary.get("artifact_rejection", {})
        if isinstance(artifact_summary, dict)
        else {}
    )
    ica_summary = (
        artifact_summary.get("ica", {})
        if isinstance(artifact_summary, dict)
        else {}
    )
    qc_summary = (
        artifact_summary.get("qc", {})
        if isinstance(artifact_summary, dict)
        else {}
    )
    before_after_qc = (
        qc_summary.get("before_after", {})
        if isinstance(qc_summary, dict)
        else {}
    )
    qc_delta = (
        before_after_qc.get("delta", {})
        if isinstance(before_after_qc, dict)
        else {}
    )
    return {
        "diagnostics_available": bool(written_paths),
        "diagnostics_file_count": len(written_paths),
        "diagnostics_directory": str(output_directory),
        "preprocessing_summary_path": str(written_paths.get("preprocessing_summary"))
        if "preprocessing_summary" in written_paths
        else None,
        "filter_report_path": str(written_paths.get("filter_report"))
        if "filter_report" in written_paths
        else None,
        "artifact_summary_path": str(written_paths.get("artifact_summary"))
        if "artifact_summary" in written_paths
        else None,
        "bad_channel_report_path": str(written_paths.get("bad_channel_report"))
        if "bad_channel_report" in written_paths
        else None,
        "artifact_rejection_report_path": str(
            written_paths.get("artifact_rejection_report")
        )
        if "artifact_rejection_report" in written_paths
        else None,
        "ica_report_path": str(written_paths.get("ica_report"))
        if "ica_report" in written_paths
        else None,
        "before_after_qc_path": str(written_paths.get("before_after_qc"))
        if "before_after_qc" in written_paths
        else None,
        "artifact_bad_channel_count": output_artifacts.get("bad_channel_count")
        if isinstance(output_artifacts, dict)
        else None,
        "artifact_annotation_count": output_artifacts.get("annotation_count")
        if isinstance(output_artifacts, dict)
        else None,
        "artifact_bad_channel_detection_status": bad_channel_detection.get("status")
        if isinstance(bad_channel_detection, dict)
        else None,
        "artifact_bad_channel_candidate_count": bad_channel_detection.get(
            "candidate_count"
        )
        if isinstance(bad_channel_detection, dict)
        else None,
        "artifact_bad_channel_interpolation_status": bad_channel_interpolation.get(
            "status"
        )
        if isinstance(bad_channel_interpolation, dict)
        else None,
        "artifact_bad_channel_interpolated_count": len(
            bad_channel_interpolation.get("interpolated_channels", [])
        )
        if isinstance(bad_channel_interpolation, dict)
        and isinstance(bad_channel_interpolation.get("interpolated_channels"), list)
        else None,
        "qc_before_after_available": bool(before_after_qc),
        "qc_bad_channel_count_delta": qc_delta.get("bad_channel_count")
        if isinstance(qc_delta, dict)
        else None,
        "qc_annotation_count_delta": qc_delta.get("annotation_count")
        if isinstance(qc_delta, dict)
        else None,
        "qc_variance_mean_ratio": qc_delta.get("variance_mean_ratio")
        if isinstance(qc_delta, dict)
        else None,
        "qc_psd_total_power_ratio": qc_delta.get("psd_total_power_ratio")
        if isinstance(qc_delta, dict)
        else None,
        "artifact_rejection_status": artifact_rejection.get("status")
        if isinstance(artifact_rejection, dict)
        else None,
        "artifact_eog_candidate_count": _artifact_candidate_count(
            artifact_rejection,
            "eog",
        ),
        "artifact_ecg_candidate_count": _artifact_candidate_count(
            artifact_rejection,
            "ecg",
        ),
        "ica_status": ica_summary.get("status")
        if isinstance(ica_summary, dict)
        else None,
        "ica_component_count": ica_summary.get("component_count")
        if isinstance(ica_summary, dict)
        else None,
        "ica_excluded_component_count": len(
            ica_summary.get("excluded_components_applied", [])
        )
        if isinstance(ica_summary, dict)
        and isinstance(ica_summary.get("excluded_components_applied"), list)
        else None,
    }


def _artifact_candidate_count(
    artifact_rejection: object,
    artifact_kind: str,
) -> int | None:
    if not isinstance(artifact_rejection, dict):
        return None
    artifact_report = artifact_rejection.get(artifact_kind)
    if not isinstance(artifact_report, dict):
        return None
    candidate_count = artifact_report.get("candidate_count")
    return candidate_count if isinstance(candidate_count, int) else None


def _write_artifact_manifest(
    output_directory: Path,
    artifacts: list[dict[str, str | int]],
) -> dict[str, str | int]:
    output_directory.mkdir(parents=True, exist_ok=True)
    manifest_path = output_directory / "artifact_manifest.json"
    manifest = {
        "schema_version": 1,
        "artifact_root": str(output_directory),
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }
    _write_json_file(manifest_path, manifest)
    return {
        "artifact_count": len(artifacts),
        "artifact_manifest_path": str(manifest_path),
    }


def _append_artifact_manifest_entry(
    output_directory: Path,
    entry: dict[str, str | int],
) -> dict[str, str | int]:
    output_directory.mkdir(parents=True, exist_ok=True)
    manifest_path = output_directory / "artifact_manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifacts = [
            artifact
            for artifact in manifest.get("artifacts", [])
            if artifact.get("logical_name") != entry["logical_name"]
        ]
    else:
        manifest = {
            "schema_version": 1,
            "artifact_root": str(output_directory),
        }
        artifacts = []

    artifacts.append(entry)
    manifest = {
        **manifest,
        "schema_version": 1,
        "artifact_root": str(output_directory),
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }
    _write_json_file(manifest_path, manifest)
    return {
        "artifact_count": len(artifacts),
        "artifact_manifest_path": str(manifest_path),
    }


def _artifact_root_for_run(run_id: str) -> Path | None:
    for run in (
        run_repository.get_preprocessing_run(run_id),
        run_repository.get_epoch_run(run_id),
        run_repository.get_erp_run(run_id),
    ):
        if run is None:
            continue
        artifact_root = run.output_metadata.get("artifact_root")
        if isinstance(artifact_root, str):
            return Path(artifact_root)
        if run.output_path:
            return Path(run.output_path).parent
    return None


def _resolve_qc_summary_run(
    *,
    dataset_id: str,
    run_id: str | None,
) -> PreprocessingRun | EpochRun | ErpRun | None:
    if run_id is not None:
        run = _find_run_by_id(run_id)
        if run is None or run.dataset_id != dataset_id:
            raise HTTPException(status_code=404, detail="Run not found")
        if _run_status_value(run) != "completed":
            raise HTTPException(status_code=409, detail="Run is not completed")
        return run

    completed_runs: list[PreprocessingRun | EpochRun | ErpRun] = [
        run
        for run in [
            *run_repository.list_preprocessing_runs(dataset_id=dataset_id),
            *run_repository.list_epoch_runs(dataset_id=dataset_id),
            *run_repository.list_erp_runs(dataset_id=dataset_id),
        ]
        if _run_status_value(run) == "completed"
    ]
    if not completed_runs:
        return None

    return max(
        completed_runs,
        key=lambda run: (
            _run_finished_sort_value(run),
            _qc_run_kind_priority(run),
        ),
    )


def _find_run_by_id(run_id: str) -> PreprocessingRun | EpochRun | ErpRun | None:
    return (
        run_repository.get_preprocessing_run(run_id)
        or run_repository.get_epoch_run(run_id)
        or run_repository.get_erp_run(run_id)
    )


def _dataset_local_data_deletion_plan(dataset_id: str) -> dict[str, Any]:
    preprocessing_runs = run_repository.list_preprocessing_runs(dataset_id)
    epoch_runs = run_repository.list_epoch_runs(dataset_id)
    erp_runs = run_repository.list_erp_runs(dataset_id)
    runs: list[PreprocessingRun | EpochRun | ErpRun] = [
        *preprocessing_runs,
        *epoch_runs,
        *erp_runs,
    ]
    warnings: list[str] = []
    paths: list[Path] = []

    _append_safe_deletion_path(
        paths,
        registry_repository.dataset_directory(dataset_id),
        allowed_roots=[registry_repository.datasets_root],
        warnings=warnings,
        label="dataset directory",
    )
    for run in preprocessing_runs:
        _append_safe_deletion_path(
            paths,
            run_repository.preprocessing_run_directory(run.run_id),
            allowed_roots=[run_repository.runs_root],
            warnings=warnings,
            label=f"preprocessing run {run.run_id}",
        )
    for run in epoch_runs:
        _append_safe_deletion_path(
            paths,
            run_repository.epoch_run_directory(run.run_id),
            allowed_roots=[run_repository.runs_root],
            warnings=warnings,
            label=f"epoch run {run.run_id}",
        )
    for run in erp_runs:
        _append_safe_deletion_path(
            paths,
            run_repository.erp_run_directory(run.run_id),
            allowed_roots=[run_repository.runs_root],
            warnings=warnings,
            label=f"ERP run {run.run_id}",
        )

    for output_root in (PROCESSED_DIR, EPOCHS_DIR, ERP_DIR):
        _append_safe_deletion_path(
            paths,
            output_root / dataset_id,
            allowed_roots=[output_root],
            warnings=warnings,
            label=f"output directory {output_root.name}",
        )

    for run in runs:
        for path_value, label in (
            (run.output_path, f"{_run_kind_value(run)} output path {run.run_id}"),
            (
                run.output_metadata.get("artifact_manifest_path"),
                f"{_run_kind_value(run)} artifact manifest directory {run.run_id}",
            ),
        ):
            if isinstance(path_value, str) and path_value.strip():
                _append_safe_deletion_path(
                    paths,
                    Path(path_value).parent,
                    allowed_roots=[PROCESSED_DIR, EPOCHS_DIR, ERP_DIR],
                    warnings=warnings,
                    label=label,
                )

    return {
        "paths": _dedupe_paths_deepest_first(paths),
        "active_run_ids": [
            run.run_id
            for run in runs
            if _run_status_value(run) in {"pending", "running", "cancelling"}
        ],
        "run_ids": {
            "preprocessing": [run.run_id for run in preprocessing_runs],
            "epoch": [run.run_id for run in epoch_runs],
            "erp": [run.run_id for run in erp_runs],
        },
        "warnings": warnings,
    }


def _append_safe_deletion_path(
    paths: list[Path],
    path: Path,
    *,
    allowed_roots: list[Path],
    warnings: list[str],
    label: str,
) -> None:
    resolved_path = path.resolve()
    resolved_roots = [root.resolve() for root in allowed_roots]
    if not any(
        resolved_path == root or resolved_path.is_relative_to(root)
        for root in resolved_roots
    ):
        warnings.append(f"Skipped unsafe {label}: {path}")
        return
    if resolved_path.exists():
        paths.append(resolved_path)


def _dedupe_paths_deepest_first(paths: list[Path]) -> list[Path]:
    deduped = {str(path): path for path in paths}
    return sorted(
        deduped.values(),
        key=lambda path: len(path.parts),
        reverse=True,
    )


def _run_artifact_manifest_path(
    run: PreprocessingRun | EpochRun | ErpRun,
) -> Path | None:
    value = run.output_metadata.get("artifact_manifest_path")
    if isinstance(value, str) and value.strip():
        path = Path(value)
        if path.is_file():
            return path
    return None


def _build_rerun_plan(run: PreprocessingRun | EpochRun | ErpRun) -> dict:
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    parent_context = _rerun_parent_context(run, blockers)
    source_checks = _rerun_source_checks(run, blockers, warnings)
    artifact_checks = [
        _rerun_artifact_check(chain_run, blockers)
        for chain_run in parent_context["runs"]
    ]
    config_checks = _rerun_config_checks(
        target_run=run,
        chain_runs=parent_context["runs"],
        mismatches=parent_context["config_mismatches"],
    )
    for chain_run in parent_context["runs"]:
        if _run_status_value(chain_run) != "completed":
            blockers.append(
                _rerun_diagnostic(
                    code="run_not_completed",
                    source="validation",
                    impact=(
                        f"{_run_kind_value(chain_run)} run {chain_run.run_id} is "
                        "not completed, so a deterministic rerun preview cannot "
                        "be marked ready."
                    ),
                    suggested_action="Wait for the run to complete or select a completed run.",
                    context={
                        "run_id": chain_run.run_id,
                        "run_kind": _run_kind_value(chain_run),
                        "status": _run_status_value(chain_run),
                    },
                )
            )

    status_value = "ready"
    if blockers:
        status_value = "blocked"
    elif warnings:
        status_value = "partially_recoverable"

    return {
        "schema_version": 1,
        "plan_kind": "rerun_plan",
        "run_id": run.run_id,
        "run_kind": _run_kind_value(run),
        "dataset_id": run.dataset_id,
        "status": status_value,
        "can_rerun": not blockers,
        "would_execute": False,
        "execution": {
            "queued": False,
            "reason": "Planning only; no rerun was created.",
        },
        "chain": parent_context["chain"],
        "checks": {
            "sources": source_checks,
            "parent_runs": parent_context["parent_checks"],
            "config": config_checks,
            "artifacts": artifact_checks,
        },
        "blockers": blockers,
        "warnings": warnings,
        "diagnostics": {
            "blockers": blockers,
            "warnings": warnings,
        },
    }


def _rerun_parent_context(
    run: PreprocessingRun | EpochRun | ErpRun,
    blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    runs: list[PreprocessingRun | EpochRun | ErpRun] = []
    chain: list[dict[str, Any]] = []
    parent_checks: list[dict[str, Any]] = []
    config_mismatches: list[dict[str, Any]] = []

    def add_run_item(chain_run: PreprocessingRun | EpochRun | ErpRun) -> None:
        runs.append(chain_run)
        chain.append(_rerun_chain_item(chain_run))

    def missing_parent(run_kind: str, run_id: str, child_run_id: str) -> None:
        item = {
            "run_id": run_id,
            "run_kind": run_kind,
            "status": "missing",
            "child_run_id": child_run_id,
        }
        chain.append(item)
        parent_checks.append(
            {
                "status": "missing",
                "run_id": run_id,
                "run_kind": run_kind,
                "child_run_id": child_run_id,
            }
        )
        blockers.append(
            _rerun_diagnostic(
                code="parent_run_missing",
                source="validation",
                impact=f"Parent {run_kind} run {run_id} is not available.",
                suggested_action="Restore the parent run registry entry before rerun.",
                context=item,
            )
        )

    if isinstance(run, PreprocessingRun):
        add_run_item(run)
    elif isinstance(run, EpochRun):
        preprocessing_run_id = run.config.preprocessing_run_id
        recorded_preprocessing_run_id = _metadata_string(
            run.output_metadata,
            "input_preprocessing_run_id",
        )
        if (
            recorded_preprocessing_run_id is not None
            and recorded_preprocessing_run_id != preprocessing_run_id
        ):
            config_mismatches.append(
                _rerun_config_mismatch(
                    run_id=run.run_id,
                    field="config.preprocessing_run_id",
                    configured=preprocessing_run_id,
                    recorded=recorded_preprocessing_run_id,
                )
            )
        preprocessing_run = run_repository.get_preprocessing_run(preprocessing_run_id)
        if preprocessing_run is None:
            missing_parent("preprocessing", preprocessing_run_id, run.run_id)
        else:
            add_run_item(preprocessing_run)
            parent_checks.append(_rerun_parent_check_item(preprocessing_run, run))
        add_run_item(run)
    else:
        epoch_run_id = run.config.epoch_run_id
        recorded_epoch_run_id = _metadata_string(
            run.output_metadata,
            "input_epoch_run_id",
        )
        if recorded_epoch_run_id is not None and recorded_epoch_run_id != epoch_run_id:
            config_mismatches.append(
                _rerun_config_mismatch(
                    run_id=run.run_id,
                    field="config.epoch_run_id",
                    configured=epoch_run_id,
                    recorded=recorded_epoch_run_id,
                )
            )
        epoch_run = run_repository.get_epoch_run(epoch_run_id)
        if epoch_run is None:
            missing_parent("epoch", epoch_run_id, run.run_id)
            recorded_preprocessing_run_id = _metadata_string(
                run.output_metadata,
                "input_preprocessing_run_id",
            )
            if recorded_preprocessing_run_id is not None:
                missing_parent(
                    "preprocessing",
                    recorded_preprocessing_run_id,
                    run.run_id,
                )
        else:
            preprocessing_run_id = epoch_run.config.preprocessing_run_id
            recorded_preprocessing_run_id = _metadata_string(
                epoch_run.output_metadata,
                "input_preprocessing_run_id",
            )
            if (
                recorded_preprocessing_run_id is not None
                and recorded_preprocessing_run_id != preprocessing_run_id
            ):
                config_mismatches.append(
                    _rerun_config_mismatch(
                        run_id=epoch_run.run_id,
                        field="config.preprocessing_run_id",
                        configured=preprocessing_run_id,
                        recorded=recorded_preprocessing_run_id,
                    )
                )
            erp_recorded_preprocessing_run_id = _metadata_string(
                run.output_metadata,
                "input_preprocessing_run_id",
            )
            if (
                erp_recorded_preprocessing_run_id is not None
                and recorded_preprocessing_run_id is not None
                and erp_recorded_preprocessing_run_id != recorded_preprocessing_run_id
            ):
                config_mismatches.append(
                    _rerun_config_mismatch(
                        run_id=run.run_id,
                        field="output_metadata.input_preprocessing_run_id",
                        configured=recorded_preprocessing_run_id,
                        recorded=erp_recorded_preprocessing_run_id,
                    )
                )
            preprocessing_run = run_repository.get_preprocessing_run(
                preprocessing_run_id
            )
            if preprocessing_run is None:
                missing_parent("preprocessing", preprocessing_run_id, epoch_run.run_id)
            else:
                add_run_item(preprocessing_run)
                parent_checks.append(_rerun_parent_check_item(preprocessing_run, epoch_run))
            add_run_item(epoch_run)
            parent_checks.append(_rerun_parent_check_item(epoch_run, run))
        add_run_item(run)

    for mismatch in config_mismatches:
        blockers.append(
            _rerun_diagnostic(
                code="config_parent_mismatch",
                source="validation",
                impact=(
                    f"{mismatch['run_id']} has conflicting configured and "
                    f"recorded parent values for {mismatch['field']}."
                ),
                suggested_action=(
                    "Review the run registry before enabling one-click rerun."
                ),
                context=mismatch,
            )
        )

    return {
        "runs": runs,
        "chain": chain,
        "parent_checks": parent_checks,
        "config_mismatches": config_mismatches,
    }


def _rerun_source_checks(
    run: PreprocessingRun | EpochRun | ErpRun,
    blockers: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    dataset = registry_repository.get_dataset(run.dataset_id)
    recording = registry_repository.get_recording(run.dataset_id)
    event_log = registry_repository.get_event_log(run.dataset_id)
    recording_sources: list[dict[str, Any]] = []
    event_sources: list[dict[str, Any]] = []

    if dataset is None:
        blockers.append(
            _rerun_diagnostic(
                code="dataset_missing",
                source="validation",
                impact=f"Dataset {run.dataset_id} is not available.",
                suggested_action="Restore the dataset registry entry before rerun.",
                context={"dataset_id": run.dataset_id},
            )
        )
    if recording is None:
        blockers.append(
            _rerun_diagnostic(
                code="recording_missing",
                source="validation",
                impact=f"Recording metadata for dataset {run.dataset_id} is missing.",
                suggested_action="Re-ingest the dataset before rerun.",
                context={"dataset_id": run.dataset_id},
            )
        )
    elif not recording.metadata.source_files:
        warnings.append(
            _rerun_diagnostic(
                code="recording_source_files_missing",
                severity="warning",
                source="export_bundle",
                impact="Recording source file metadata is not available.",
                suggested_action=(
                    "Re-ingest the dataset with Phase D metadata to improve rerun "
                    "auditability."
                ),
                context={"recording_id": recording.recording_id},
            )
        )
    else:
        for source_file in recording.metadata.source_files:
            item = _rerun_path_check(
                path_value=source_file.stored_path,
                role=source_file.role,
                original_filename=source_file.original_filename,
            )
            recording_sources.append(item)
            if item["status"] != "ok":
                blockers.append(
                    _rerun_diagnostic(
                        code="source_file_missing",
                        source="validation",
                        impact=f"Source file is missing: {source_file.stored_path}",
                        suggested_action=(
                            "Restore the source file or re-ingest the dataset."
                        ),
                        context=item,
                    )
                )

    if isinstance(run, (EpochRun, ErpRun)):
        if event_log is None:
            blockers.append(
                _rerun_diagnostic(
                    code="event_log_missing",
                    source="validation",
                    impact=f"Event log for dataset {run.dataset_id} is missing.",
                    suggested_action="Restore or remap the event log before rerun.",
                    context={"dataset_id": run.dataset_id},
                )
            )
        elif not event_log.provenance:
            warnings.append(
                _rerun_diagnostic(
                    code="event_provenance_missing",
                    severity="warning",
                    source="export_bundle",
                    impact="Event log provenance metadata is not available.",
                    suggested_action=(
                        "Remap the event log with Phase D metadata to improve "
                        "rerun auditability."
                    ),
                    context={"event_log_id": event_log.event_log_id},
                )
            )
        else:
            for event_source in _event_file_sources(event_log):
                item = _rerun_path_check(
                    path_value=event_source.get("stored_path")
                    or event_source.get("path"),
                    role=str(event_source.get("role") or "event_file"),
                    original_filename=event_source.get("original_filename"),
                )
                event_sources.append(item)
                if item["status"] != "ok":
                    blockers.append(
                        _rerun_diagnostic(
                            code="event_source_file_missing",
                            source="validation",
                            impact=(
                                "Event source file is missing: "
                                f"{item.get('path')}"
                            ),
                            suggested_action=(
                                "Restore the event source file or remap events."
                            ),
                            context=item,
                        )
                    )

    return {
        "dataset": {
            "dataset_id": run.dataset_id,
            "status": "ok" if dataset is not None else "missing",
        },
        "recording": {
            "recording_id": recording.recording_id if recording is not None else None,
            "status": "ok" if recording is not None else "missing",
            "source_files": recording_sources,
        },
        "event_log": {
            "event_log_id": event_log.event_log_id if event_log is not None else None,
            "status": "ok" if event_log is not None else "missing",
            "source_files": event_sources,
        },
    }


def _rerun_artifact_check(
    run: PreprocessingRun | EpochRun | ErpRun,
    blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    manifest_path_value = run.output_metadata.get("artifact_manifest_path")
    manifest_path = _run_artifact_manifest_path(run)
    if manifest_path is None:
        item = {
            "run_id": run.run_id,
            "run_kind": _run_kind_value(run),
            "status": "missing",
            "artifact_manifest_path": manifest_path_value,
        }
        blockers.append(
            _rerun_diagnostic(
                code="artifact_manifest_missing",
                source="artifact",
                impact=f"Artifact manifest for run {run.run_id} is missing.",
                suggested_action="Restore the artifact manifest before rerun.",
                context=item,
            )
        )
        return item

    try:
        integrity = check_artifact_integrity(manifest_path)
    except ArtifactManifestError as exc:
        item = {
            "run_id": run.run_id,
            "run_kind": _run_kind_value(run),
            "status": "invalid",
            "artifact_manifest_path": str(manifest_path),
            "error": str(exc),
        }
        blockers.append(
            _rerun_diagnostic(
                code="artifact_manifest_invalid",
                source="artifact",
                impact=f"Artifact manifest for run {run.run_id} is invalid.",
                suggested_action="Repair or regenerate the artifact manifest.",
                context=item,
            )
        )
        return item

    if integrity["status"] != "ok":
        blockers.append(
            _rerun_diagnostic(
                code="artifact_integrity_failed",
                source="artifact",
                impact=f"Artifacts for run {run.run_id} are missing or mismatched.",
                suggested_action="Restore missing artifacts or regenerate this run.",
                context={
                    "run_id": run.run_id,
                    "run_kind": _run_kind_value(run),
                    "status": integrity["status"],
                    "status_counts": integrity["status_counts"],
                },
            )
        )

    return {
        "run_id": run.run_id,
        "run_kind": _run_kind_value(run),
        "status": integrity["status"],
        "artifact_manifest_path": integrity["manifest_path"],
        "status_counts": integrity["status_counts"],
    }


def _rerun_config_checks(
    *,
    target_run: PreprocessingRun | EpochRun | ErpRun,
    chain_runs: list[PreprocessingRun | EpochRun | ErpRun],
    mismatches: list[dict[str, Any]],
) -> dict[str, Any]:
    snapshots = [
        {
            "run_id": chain_run.run_id,
            "run_kind": _run_kind_value(chain_run),
            "config_snapshot": asdict(chain_run.config),
            "config_digest_sha256": _stable_sha256(asdict(chain_run.config)),
        }
        for chain_run in chain_runs
    ]
    return {
        "status": "mismatch" if mismatches else "ok",
        "target_run_id": target_run.run_id,
        "target_config_digest_sha256": _stable_sha256(asdict(target_run.config)),
        "chain_config_snapshots": snapshots,
        "mismatches": mismatches,
    }


def _rerun_chain_item(run: PreprocessingRun | EpochRun | ErpRun) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "run_kind": _run_kind_value(run),
        "status": _run_status_value(run),
        "artifact_manifest_path": run.output_metadata.get("artifact_manifest_path"),
    }


def _rerun_parent_check_item(
    parent_run: PreprocessingRun | EpochRun | ErpRun,
    child_run: EpochRun | ErpRun,
) -> dict[str, Any]:
    return {
        "status": "ok" if _run_status_value(parent_run) == "completed" else "blocked",
        "run_id": parent_run.run_id,
        "run_kind": _run_kind_value(parent_run),
        "child_run_id": child_run.run_id,
        "child_run_kind": _run_kind_value(child_run),
        "parent_status": _run_status_value(parent_run),
    }


def _rerun_config_mismatch(
    *,
    run_id: str,
    field: str,
    configured: str,
    recorded: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "field": field,
        "configured": configured,
        "recorded": recorded,
    }


def _rerun_path_check(
    *,
    path_value: object,
    role: str,
    original_filename: object | None = None,
) -> dict[str, Any]:
    path = str(path_value).strip() if path_value is not None else ""
    exists = bool(path) and Path(path).is_file()
    return {
        "role": role,
        "original_filename": str(original_filename)
        if original_filename is not None
        else None,
        "path": path or None,
        "status": "ok" if exists else "missing",
    }


def _event_file_sources(event_log: EventLog) -> list[dict[str, Any]]:
    sources = event_log.provenance.get("sources")
    if not isinstance(sources, list):
        return []
    return [
        dict(source)
        for source in sources
        if isinstance(source, dict)
        and str(source.get("role") or "").lower() == "event_file"
    ]


def _metadata_string(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return None


def _stable_sha256(value: dict[str, Any]) -> str:
    payload = json.dumps(
        value,
        default=str,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _rerun_diagnostic(
    *,
    code: str,
    source: str,
    impact: str,
    suggested_action: str,
    severity: str = "error",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "source": source,
        "code": code,
        "impact": impact,
        "suggested_action": suggested_action,
        "context": context or {},
    }


def _generate_run_analysis_report(
    run: ErpRun,
) -> tuple[dict, ErpRun, Path]:
    manifest_path = _run_artifact_manifest_path(run)
    if manifest_path is None:
        raise HTTPException(status_code=404, detail="Artifact manifest not found")

    output_directory = manifest_path.parent
    report_path = output_directory / "analysis_report.json"
    extra_sections = _analysis_report_extra_sections(run)
    write_analysis_report(
        report_path,
        dataset_id=run.dataset_id,
        run_id=run.run_id,
        run_kind=run.run_kind.value,
        artifact_manifest_path=manifest_path,
        config_snapshot=_erp_config_payload(run.config),
        extra_sections=extra_sections,
    )
    manifest_metadata = _append_artifact_manifest_entry(
        output_directory=output_directory,
        entry=_artifact_manifest_entry(
            logical_name="analysis_report",
            path=report_path,
            artifact_type="analysis_report_json",
            output_directory=output_directory,
        ),
    )
    manifest_path = Path(str(manifest_metadata["artifact_manifest_path"]))
    write_analysis_report(
        report_path,
        dataset_id=run.dataset_id,
        run_id=run.run_id,
        run_kind=run.run_kind.value,
        artifact_manifest_path=manifest_path,
        config_snapshot=_erp_config_payload(run.config),
        extra_sections=extra_sections,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    completed_run = replace(
        run,
        output_metadata={
            **run.output_metadata,
            "artifact_count": manifest_metadata["artifact_count"],
            "artifact_manifest_path": manifest_metadata["artifact_manifest_path"],
            "analysis_report_available": True,
            "analysis_report_path": str(report_path),
            "analysis_report_url": f"/artifacts/{run.run_id}/{report_path.name}",
        },
    )
    return report, completed_run, report_path


def _erp_analysis_report_sections(run: ErpRun) -> dict:
    dataset = registry_repository.get_dataset(run.dataset_id)
    recording = registry_repository.get_recording(run.dataset_id)
    event_log = registry_repository.get_event_log(run.dataset_id)
    epoch_run = run_repository.get_epoch_run(run.config.epoch_run_id)
    preprocessing_run = _preprocessing_run_for_erp_report(run, epoch_run)
    comparison_summary = _read_optional_json_path(
        run.output_metadata.get("comparison_summary_path")
    )

    comparison_statistics = _comparison_statistics_report_payload(comparison_summary)
    return {
        "dataset_metadata": _report_dataset_metadata(dataset, recording),
        "event_summary": _report_event_summary(event_log),
        "preprocessing_config": asdict(preprocessing_run.config)
        if preprocessing_run is not None
        else None,
        "epoch_config": asdict(epoch_run.config) if epoch_run is not None else None,
        "erp_config": _erp_config_payload(run.config),
        "warnings": _report_warning_summary(
            preprocessing_run=preprocessing_run,
            epoch_run=epoch_run,
            erp_run=run,
        ),
        "preview_plot": {
            "url": run.output_metadata.get("preview_plot_url"),
            "path": run.output_metadata.get("preview_plot_path"),
            "condition": run.output_metadata.get("preview_plot_condition"),
            "mode": run.output_metadata.get("preview_plot_mode"),
            "channel": run.output_metadata.get("preview_plot_channel"),
        },
        "comparison_summary": comparison_summary,
        "comparison_statistics": comparison_statistics,
    }


def _preprocessing_run_for_erp_report(
    run: ErpRun,
    epoch_run: EpochRun | None,
) -> PreprocessingRun | None:
    run_id = run.output_metadata.get("input_preprocessing_run_id")
    if not isinstance(run_id, str) and epoch_run is not None:
        run_id = epoch_run.output_metadata.get("input_preprocessing_run_id")
    if isinstance(run_id, str) and run_id:
        return run_repository.get_preprocessing_run(run_id)
    return None


def _report_dataset_metadata(
    dataset: IngestionDataset | None,
    recording: Recording | None,
) -> dict:
    metadata = dataset.metadata if dataset is not None else {}
    recording_metadata = recording.metadata if recording is not None else None
    return {
        "dataset_id": dataset.dataset_id if dataset is not None else None,
        "project_id": dataset.project_id if dataset is not None else None,
        "experiment_id": dataset.experiment_id if dataset is not None else None,
        "participant_label": metadata.get("participant_label"),
        "participant_group": metadata.get("participant_group"),
        "session_label": metadata.get("session_label"),
        "status": dataset.status.value if dataset is not None else None,
        "recording": {
            "recording_id": recording.recording_id if recording is not None else None,
            "sampling_rate_hz": recording_metadata.sampling_rate_hz
            if recording_metadata is not None
            else None,
            "duration_seconds": recording_metadata.duration_seconds
            if recording_metadata is not None
            else None,
            "channel_count": recording_metadata.channel_count
            if recording_metadata is not None
            else None,
            "file_format": recording_metadata.file_format
            if recording_metadata is not None
            else None,
            "source_files": [
                _source_file_metadata_payload(source_file).model_dump()
                for source_file in recording_metadata.source_files
            ]
            if recording_metadata is not None
            else [],
            "sidecar_discovery": recording_metadata.sidecar_discovery
            if recording_metadata is not None
            else {},
        },
    }


def _report_event_summary(event_log: EventLog | None) -> dict:
    if event_log is None:
        return {
            "event_log_id": None,
            "row_count": 0,
            "filter_count": 0,
            "event_count": 0,
            "condition_counts": {},
            "mapping": {},
        }

    condition_counts: dict[str, int] = {}
    for event in event_log.events:
        label = event.trial_type or "unlabeled"
        condition_counts[label] = condition_counts.get(label, 0) + 1

    return {
        "event_log_id": event_log.event_log_id,
        "row_count": event_log.row_count,
        "filter_count": event_log.filter_count,
        "event_count": len(event_log.events),
        "condition_counts": condition_counts,
        "mapping": event_log.mapping.__dict__,
        "condition_column": event_log.condition_column,
        "provenance": event_log.provenance,
        "source_columns": _event_source_column_summary(event_log),
    }


def _event_source_column_summary(event_log: EventLog) -> dict:
    column_names: set[str] = set()
    example_values: dict[str, str | None] = {}
    for event in event_log.events:
        for column_name, value in event.source_columns.items():
            column_names.add(column_name)
            if column_name not in example_values and value is not None:
                example_values[column_name] = value
    return {
        "column_names": sorted(column_names),
        "example_values": example_values,
    }


def _report_warning_summary(
    *,
    preprocessing_run: PreprocessingRun | None,
    epoch_run: EpochRun | None,
    erp_run: ErpRun,
) -> dict:
    return {
        "preprocessing": _run_warning_payload(preprocessing_run),
        "epoch": _run_warning_payload(epoch_run),
        "erp": _run_warning_payload(erp_run),
    }


def _run_warning_payload(
    run: PreprocessingRun | EpochRun | ErpRun | None,
) -> dict:
    if run is None:
        return {"run_id": None, "warnings": [], "diagnostics": {}}
    return {
        "run_id": run.run_id,
        "warnings": run.warnings,
        "diagnostics": _diagnostics_report_payload(run.diagnostics),
    }


def _analysis_report_extra_sections(
    run: PreprocessingRun | EpochRun | ErpRun,
) -> dict:
    extra_sections: dict[str, Any] = {}
    if isinstance(run, ErpRun):
        extra_sections.update(_erp_analysis_report_sections(run))
    batch_context = _batch_context_for_run(run)
    if batch_context is not None:
        extra_sections["batch"] = batch_context
    extra_sections["phase_d_metadata"] = _phase_d_metadata_for_run(run)
    return extra_sections


def _diagnostics_report_payload(diagnostics: dict) -> dict:
    payload = _run_diagnostics_response(diagnostics)
    if isinstance(payload, RunDiagnosticsResponse):
        return payload.model_dump()
    return payload if isinstance(payload, dict) else {}


def _read_optional_json_path(value: object) -> dict | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _comparison_statistics_report_payload(
    comparison_summary: dict | None,
) -> dict:
    statistics = (
        comparison_summary.get("statistics")
        if isinstance(comparison_summary, dict)
        else None
    )
    if not isinstance(statistics, dict):
        return {
            "available": False,
            "status": "missing",
            "implemented": False,
            "method": None,
            "result": None,
            "diagnostics": {"warnings": []},
        }
    result = statistics.get("result")
    return {
        "available": True,
        "schema_version": statistics.get("schema_version"),
        "status": statistics.get("status"),
        "implemented": statistics.get("implemented"),
        "phase": statistics.get("phase"),
        "method": statistics.get("method"),
        "design": statistics.get("design"),
        "input_metric": statistics.get("input_metric"),
        "observation_level": statistics.get("observation_level"),
        "condition_pair": statistics.get("condition_pair"),
        "sample": statistics.get("sample"),
        "result": result if isinstance(result, dict) else None,
        "assumptions": statistics.get("assumptions", []),
        "diagnostics": statistics.get("diagnostics", {"warnings": []}),
    }


def _comparison_statistics_warnings(
    run: PreprocessingRun | EpochRun | ErpRun,
) -> list[dict[str, Any]]:
    if not isinstance(run, ErpRun):
        return []
    comparison_summary = _read_optional_json_path(
        run.output_metadata.get("comparison_summary_path")
    )
    statistics = _comparison_statistics_report_payload(comparison_summary)
    diagnostics = statistics.get("diagnostics")
    if not isinstance(diagnostics, dict):
        return []
    warnings = diagnostics.get("warnings")
    if not isinstance(warnings, list):
        return []
    return [warning for warning in warnings if isinstance(warning, dict)]


def _export_bundle_extra_manifest_sections(
    run: PreprocessingRun | EpochRun | ErpRun,
) -> dict[str, Any]:
    if not isinstance(run, ErpRun):
        return {}
    comparison_summary = _read_optional_json_path(
        run.output_metadata.get("comparison_summary_path")
    )
    if comparison_summary is None:
        return {
            "comparison_summary": {"available": False},
            "comparison_statistics": {
                "available": False,
                "status": "missing",
                "implemented": False,
            },
        }
    return {
        "comparison_summary": {
            "available": True,
            "metric": comparison_summary.get("metric"),
            "condition_a": (
                comparison_summary.get("conditions", {})
                .get("a", {})
                .get("label")
            ),
            "condition_b": (
                comparison_summary.get("conditions", {})
                .get("b", {})
                .get("label")
            ),
            "difference": comparison_summary.get("difference"),
            "target": comparison_summary.get("target"),
            "window": comparison_summary.get("window"),
        },
        "comparison_statistics": _comparison_statistics_report_payload(
            comparison_summary
        ),
    }


def _export_bundle_response(run: PreprocessingRun | EpochRun | ErpRun) -> FileResponse:
    if isinstance(run, ErpRun):
        _, completed_run, analysis_report_path = _generate_run_analysis_report(run)
        run = completed_run
        run_repository.save_erp_run(completed_run)
        manifest_path = _run_artifact_manifest_path(completed_run)
    else:
        manifest_path = _run_artifact_manifest_path(run)
        if manifest_path is None:
            raise HTTPException(status_code=404, detail="Artifact manifest not found")
        output_directory = manifest_path.parent
        analysis_report_path = output_directory / "analysis_report.json"
        try:
            write_analysis_report(
                analysis_report_path,
                dataset_id=run.dataset_id,
                run_id=run.run_id,
                run_kind=_run_kind_value(run),
                artifact_manifest_path=manifest_path,
                config_snapshot=asdict(run.config),
                extra_sections=_analysis_report_extra_sections(run),
            )
        except (AnalysisReportError, ArtifactManifestError, QcSummaryError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    if manifest_path is None:
        raise HTTPException(status_code=404, detail="Artifact manifest not found")

    output_directory = manifest_path.parent
    export_bundle_path = output_directory / "export_bundle.zip"
    phase_d_metadata_path, phase_d_metadata = _write_phase_d_metadata_artifact(
        run,
        output_directory,
    )
    try:
        build_export_bundle(
            artifact_manifest_path=manifest_path,
            analysis_report_path=analysis_report_path,
            output_zip_path=export_bundle_path,
            extra_artifacts=[
                *_batch_export_artifacts_for_run(run),
                {
                    "logical_name": "phase_d_metadata",
                    "artifact_type": "phase_d_metadata_json",
                    "path": str(phase_d_metadata_path),
                    "archive_path": "diagnostics/phase_d_metadata.json",
                },
            ],
            diagnostics_warnings=[
                *phase_d_metadata["diagnostics"]["warnings"],
                *_comparison_statistics_warnings(run),
            ],
            extra_manifest_sections=_export_bundle_extra_manifest_sections(run),
        )
    except (AnalysisReportError, ArtifactManifestError, QcSummaryError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return FileResponse(
        export_bundle_path,
        media_type="application/zip",
        filename=f"neuroweave_{run.dataset_id}_{run.run_id}_export_bundle.zip",
    )


def _run_status_value(run: PreprocessingRun | EpochRun | ErpRun) -> str:
    return str(run.status.value if hasattr(run.status, "value") else run.status)


def _run_kind_value(run: PreprocessingRun | EpochRun | ErpRun) -> str:
    return str(run.run_kind.value if hasattr(run.run_kind, "value") else run.run_kind)


def _run_finished_sort_value(run: PreprocessingRun | EpochRun | ErpRun) -> str:
    return run.finished_at_utc or ""


def _qc_run_kind_priority(run: PreprocessingRun | EpochRun | ErpRun) -> int:
    priorities = {
        RunKind.PREPROCESSING: 0,
        RunKind.EPOCH: 1,
        RunKind.ERP: 2,
    }
    return priorities.get(run.run_kind, -1)


def _resolve_preprocessing_output_path(run: PreprocessingRun) -> Path | None:
    if not run.output_path:
        return None
    path = Path(run.output_path)
    return _first_existing_path(
        [
            path,
            path.with_name(RAW_PREPROCESSED_FILENAME),
            path.with_name(LEGACY_RAW_PREPROCESSED_FILENAME),
        ]
    )


def _resolve_epoch_output_path(run: EpochRun) -> Path | None:
    if not run.output_path:
        return None
    path = Path(run.output_path)
    return _first_existing_path(
        [
            path,
            path.with_name(EPOCHS_FILENAME),
            path.with_name(LEGACY_EPOCHS_FILENAME),
        ]
    )


def _first_existing_path(paths: list[Path]) -> Path | None:
    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        if path.is_file():
            return path
    return None


def _artifact_manifest_entry(
    logical_name: str,
    path: Path,
    artifact_type: str,
    output_directory: Path,
) -> dict[str, str | int]:
    if not path.is_file():
        raise ValueError(f"Artifact does not exist: {path}")

    resolved_path = path.resolve()
    output_root = output_directory.resolve()
    if not resolved_path.is_relative_to(output_root):
        raise ValueError(f"Artifact path escapes its output directory: {path}")

    return {
        "logical_name": logical_name,
        "artifact_type": artifact_type,
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "checksum_sha256": _sha256_file(path),
        "created_at_utc": _utc_now_iso(),
    }


def _write_json_file(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _validation_issue_response(issue: ValidationIssue) -> ValidationIssueResponse:
    return ValidationIssueResponse(
        severity=issue.severity.value,
        code=issue.code,
        message=issue.message,
        field=issue.field,
    )


def _validate_dataset(dataset: IngestionDataset) -> ValidationReport:
    recording = registry_repository.get_recording(dataset.dataset_id)
    event_log = registry_repository.get_event_log(dataset.dataset_id)
    return validate_ingestion_dataset(
        dataset=dataset,
        recording=recording,
        event_log=event_log,
    )


def _execute_batch_run(batch_id: str) -> None:
    batch = batch_repository.get_batch(batch_id)
    if batch is None or batch.status in {
        BatchStatus.COMPLETED,
        BatchStatus.FAILED,
        BatchStatus.PARTIAL,
        BatchStatus.CANCELLED,
    }:
        return

    if batch.status == BatchStatus.CANCELLING:
        _cancel_batch_pending_items(batch, reason="Batch cancelled before next item.")
        return

    batch = replace(
        batch,
        status=BatchStatus.RUNNING,
        updated_at_utc=_batch_updated_at(batch),
    )
    batch_repository.save_batch(batch)

    for item in batch.items:
        current_batch = batch_repository.get_batch(batch_id)
        if current_batch is None:
            return
        if current_batch.status in {BatchStatus.CANCELLING, BatchStatus.CANCELLED}:
            _cancel_batch_pending_items(
                current_batch,
                reason="Batch cancelled at worker checkpoint.",
            )
            return

        current_item = _batch_item_by_id(current_batch, item.item_id)
        if current_item is None or current_item.status in {
            BatchItemStatus.COMPLETED,
            BatchItemStatus.FAILED,
            BatchItemStatus.CANCELLED,
        }:
            continue

        _ensure_batch_preprocessing_run(current_batch, current_item)
        current_batch = batch_repository.get_batch(batch_id)
        if current_batch is None:
            return
        current_item = _batch_item_by_id(current_batch, item.item_id)
        if current_item is None:
            return
        if current_item.status == BatchItemStatus.FAILED:
            continue
        if current_batch.status in {BatchStatus.CANCELLING, BatchStatus.CANCELLED}:
            _cancel_current_batch_item(current_batch, current_item)
            return

        run_id = current_item.run_ids.get(RunKind.PREPROCESSING.value)
        if not run_id:
            failed_item = replace(
                current_item,
                status=BatchItemStatus.FAILED,
                errors=[
                    *current_item.errors,
                    "Batch preprocessing run id was not created.",
                ],
            )
            _save_batch_item(current_batch, failed_item)
            continue

        _execute_preprocessing_run(run_id)
        completed_batch = batch_repository.get_batch(batch_id)
        if completed_batch is None:
            return
        completed_item = _batch_item_by_id(completed_batch, item.item_id)
        if completed_item is None:
            return
        run = run_repository.get_preprocessing_run(run_id)
        if completed_batch.status in {
            BatchStatus.CANCELLING,
            BatchStatus.CANCELLED,
        } or (run is not None and run.status == PreprocessingRunStatus.CANCELLED):
            _cancel_current_batch_item(completed_batch, completed_item)
            return
        _save_batch_item(
            completed_batch,
            _batch_item_from_preprocessing_run(completed_item, run),
        )

    final_batch = batch_repository.get_batch(batch_id)
    if final_batch is None:
        return
    if final_batch.status in {BatchStatus.CANCELLING, BatchStatus.CANCELLED}:
        _cancel_batch_pending_items(
            final_batch,
            reason="Batch cancelled at final checkpoint.",
        )
        return
    saved_batch = batch_repository.save_batch(
        replace(
            final_batch,
            status=_batch_status_from_items(final_batch.items),
            updated_at_utc=_batch_updated_at(final_batch),
        )
    )
    _write_batch_summary_artifact(saved_batch)


def _ensure_batch_preprocessing_run(
    batch: BatchRunPlan,
    item: BatchSubjectRunPlan,
) -> BatchSubjectRunPlan:
    existing_run_id = item.run_ids.get(RunKind.PREPROCESSING.value)
    if existing_run_id:
        running_item = replace(item, status=BatchItemStatus.RUNNING)
        _save_batch_item(batch, running_item)
        return running_item

    if RunKind.PREPROCESSING not in item.planned_steps:
        failed_item = replace(
            item,
            status=BatchItemStatus.FAILED,
            errors=[
                *item.errors,
                "Batch worker MVP only supports preprocessing steps.",
            ],
        )
        _save_batch_item(batch, failed_item)
        return failed_item

    preprocessing_config = item.configs.preprocessing
    if preprocessing_config is None:
        failed_item = replace(
            item,
            status=BatchItemStatus.FAILED,
            errors=[*item.errors, "Preprocessing config is missing."],
        )
        _save_batch_item(batch, failed_item)
        return failed_item

    try:
        run = _create_batch_preprocessing_run(
            batch_id=batch.batch_id,
            item_id=item.item_id,
            dataset_id=item.dataset_id,
            config=preprocessing_config,
        )
    except ValueError as exc:
        failed_item = replace(
            item,
            status=BatchItemStatus.FAILED,
            errors=_dedupe_strings([*item.errors, str(exc)]),
        )
        _save_batch_item(batch, failed_item)
        return failed_item

    running_item = replace(
        item,
        status=BatchItemStatus.RUNNING,
        run_ids={**item.run_ids, RunKind.PREPROCESSING.value: run.run_id},
        errors=[],
    )
    _save_batch_item(batch, running_item)
    return running_item


def _create_batch_preprocessing_run(
    *,
    batch_id: str,
    item_id: str,
    dataset_id: str,
    config: PreprocessingConfig,
) -> PreprocessingRun:
    dataset = registry_repository.get_dataset(dataset_id)
    if dataset is None:
        raise ValueError("Dataset not found")

    report = _validate_dataset(dataset)
    if not report.valid:
        registry_repository.update_dataset(replace(dataset, status=report.status))
        raise ValueError("Dataset must be valid before batch preprocessing.")

    recording = registry_repository.get_recording(dataset_id)
    if recording is None:
        raise ValueError("Recording not found")

    uploaded_file = _find_uploaded_file(dataset_id, recording.file_id)
    if uploaded_file is None or uploaded_file.kind != UploadedFileKind.EEG:
        raise ValueError("EEG file not found")

    config_errors = _validate_preprocessing_config(config, recording)
    if config_errors:
        raise ValueError("; ".join(config_errors))

    run_id = _new_id("preprocess")
    output_path = _preprocessing_output_path(dataset_id, run_id)
    run = PreprocessingRun(
        run_id=run_id,
        dataset_id=dataset_id,
        config=config,
        status=PreprocessingRunStatus.PENDING,
        output_path=str(output_path),
        output_metadata={
            **_preprocessing_input_provenance(
                uploaded_file=uploaded_file,
                recording=recording,
            ),
            "batch_id": batch_id,
            "batch_item_id": item_id,
        },
    )
    run_repository.save_preprocessing_run(run)
    return run


def _batch_item_from_preprocessing_run(
    item: BatchSubjectRunPlan,
    run: PreprocessingRun | None,
) -> BatchSubjectRunPlan:
    if run is None:
        return replace(
            item,
            status=BatchItemStatus.FAILED,
            errors=[*item.errors, "Preprocessing run not found after execution."],
        )
    if run.status == PreprocessingRunStatus.COMPLETED:
        return replace(
            item,
            status=BatchItemStatus.COMPLETED,
            warnings=_dedupe_strings([*item.warnings, *run.warnings]),
            errors=[],
        )
    if run.status == PreprocessingRunStatus.CANCELLED:
        return replace(
            item,
            status=BatchItemStatus.CANCELLED,
            warnings=_dedupe_strings([*item.warnings, *run.warnings]),
            errors=run.errors,
        )
    return replace(
        item,
        status=BatchItemStatus.FAILED,
        warnings=_dedupe_strings([*item.warnings, *run.warnings]),
        errors=run.errors or [f"Preprocessing ended with status {run.status.value}."],
    )


def _cancel_current_batch_item(
    batch: BatchRunPlan,
    item: BatchSubjectRunPlan,
) -> None:
    run_id = item.run_ids.get(RunKind.PREPROCESSING.value)
    if run_id:
        _request_preprocessing_run_cancellation(run_id)
    cancelled_item = replace(
        item,
        status=BatchItemStatus.CANCELLED,
        warnings=_dedupe_strings(
            [*item.warnings, "Batch cancellation stopped this item."]
        ),
    )
    _save_batch_item(batch, cancelled_item)
    current_batch = batch_repository.get_batch(batch.batch_id)
    if current_batch is not None:
        _cancel_batch_pending_items(
            current_batch,
            reason="Batch cancellation stopped pending items.",
        )


def _cancel_batch_pending_items(batch: BatchRunPlan, *, reason: str) -> BatchRunPlan:
    cancelled_items = []
    for item in batch.items:
        if item.status in {
            BatchItemStatus.PENDING,
            BatchItemStatus.RUNNING,
            BatchItemStatus.CANCELLING,
        }:
            run_id = item.run_ids.get(RunKind.PREPROCESSING.value)
            if run_id:
                _request_preprocessing_run_cancellation(run_id)
            cancelled_items.append(
                replace(
                    item,
                    status=BatchItemStatus.CANCELLED,
                    warnings=_dedupe_strings([*item.warnings, reason]),
                )
            )
        else:
            cancelled_items.append(item)
    cancelled_batch = replace(
        batch,
        status=BatchStatus.CANCELLED,
        items=cancelled_items,
        updated_at_utc=_batch_updated_at(batch),
    )
    batch_repository.save_batch(cancelled_batch)
    _write_batch_summary_artifact(cancelled_batch)
    return cancelled_batch


def _batch_item_by_id(
    batch: BatchRunPlan,
    item_id: str,
) -> BatchSubjectRunPlan | None:
    for item in batch.items:
        if item.item_id == item_id:
            return item
    return None


def _retry_failed_batch_item(item: BatchSubjectRunPlan) -> BatchSubjectRunPlan:
    previous_error = " ".join(item.errors).strip() or item.previous_error
    previous_run_ids = item.run_ids or item.previous_run_ids
    return replace(
        item,
        status=BatchItemStatus.PENDING,
        attempt=item.attempt + 1,
        run_ids={},
        previous_run_ids=previous_run_ids,
        previous_error=previous_error,
        warnings=_dedupe_strings(
            [*item.warnings, "Retry queued after failed attempt."]
        ),
        errors=[],
    )


def _write_batch_summary_artifact(batch: BatchRunPlan) -> Path:
    summary_path = _batch_summary_artifact_path(batch.batch_id)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_file(summary_path, _batch_summary_payload(batch, summary_path))
    return summary_path


def _batch_summary_artifact_path(batch_id: str) -> Path:
    return batch_repository.batch_directory(batch_id) / "batch_summary.json"


def _batch_summary_payload(batch: BatchRunPlan, summary_path: Path) -> dict:
    return {
        "schema_version": BATCH_SUMMARY_SCHEMA_VERSION,
        "batch_id": batch.batch_id,
        "status": batch.status.value,
        "created_at_utc": batch.created_at_utc,
        "updated_at_utc": batch.updated_at_utc,
        "summary_artifact_path": str(summary_path),
        "template_snapshot": {
            "template_id": batch.template_snapshot.template_id,
            "template_name": batch.template_snapshot.template_name,
            "template_updated_at_utc": (
                batch.template_snapshot.template_updated_at_utc
            ),
            "captured_at_utc": batch.template_snapshot.captured_at_utc,
            "template_digest_sha256": (
                batch.template_snapshot.template_digest_sha256
            ),
        },
        "item_counts": _batch_item_counts(batch.items),
        "items": [_batch_summary_item_payload(item) for item in batch.items],
        "warnings": batch.warnings,
        "errors": batch.errors,
    }


def _batch_item_counts(items: list[BatchSubjectRunPlan]) -> dict[str, int]:
    counts = {
        "total": len(items),
        "pending": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
        "cancelling": 0,
        "cancelled": 0,
    }
    for item in items:
        counts[item.status.value] = counts.get(item.status.value, 0) + 1
    return counts


def _batch_summary_item_payload(item: BatchSubjectRunPlan) -> dict:
    return {
        "item_id": item.item_id,
        "dataset_id": item.dataset_id,
        "status": item.status.value,
        "attempt": item.attempt,
        "retry_of_item_id": item.retry_of_item_id,
        "run_ids": item.run_ids,
        "previous_run_ids": item.previous_run_ids,
        "previous_error": item.previous_error,
        "artifact_manifests": {
            kind: _run_artifact_manifest_link(run_id)
            for kind, run_id in item.run_ids.items()
        },
        "warnings": item.warnings,
        "errors": item.errors,
    }


def _run_artifact_manifest_link(run_id: str) -> dict:
    run = _find_run_by_id(run_id)
    manifest_path = _run_artifact_manifest_path(run) if run is not None else None
    return {
        "run_id": run_id,
        "run_kind": _run_kind_value(run) if run is not None else None,
        "run_status": _run_status_value(run) if run is not None else None,
        "artifact_manifest_path": str(manifest_path)
        if manifest_path is not None
        else None,
        "artifact_manifest_url": f"/artifacts/{run_id}/artifact_manifest.json"
        if manifest_path is not None
        else None,
    }


def _batch_context_for_run(
    run: PreprocessingRun | EpochRun | ErpRun,
) -> dict | None:
    batch_source_run = _batch_source_run_for_run(run)
    if batch_source_run is None:
        return None
    batch_id = batch_source_run.output_metadata.get("batch_id")
    if not isinstance(batch_id, str) or not batch_id:
        return None
    batch = batch_repository.get_batch(batch_id)
    if batch is None:
        return None

    summary_path = _write_batch_summary_artifact(batch)
    batch_item_id = batch_source_run.output_metadata.get("batch_item_id")
    item = (
        _batch_item_by_id(batch, batch_item_id)
        if isinstance(batch_item_id, str)
        else None
    )
    if item is None:
        item = _batch_item_for_run_id(batch, batch_source_run.run_id)

    return {
        "batch_id": batch.batch_id,
        "batch_status": batch.status.value,
        "batch_item_id": item.item_id if item is not None else batch_item_id,
        "batch_item_status": item.status.value if item is not None else None,
        "attempt": item.attempt if item is not None else None,
        "source_run_id": batch_source_run.run_id,
        "source_run_kind": _run_kind_value(batch_source_run),
        "summary_artifact": {
            "path": str(summary_path),
            "url": f"/batches/{batch.batch_id}/summary-artifact",
        },
        "subject_manifest": _run_artifact_manifest_link(batch_source_run.run_id),
        "template_snapshot": {
            "template_id": batch.template_snapshot.template_id,
            "template_name": batch.template_snapshot.template_name,
            "template_digest_sha256": (
                batch.template_snapshot.template_digest_sha256
            ),
        },
        "item_counts": _batch_item_counts(batch.items),
    }


def _batch_source_run_for_run(
    run: PreprocessingRun | EpochRun | ErpRun,
) -> PreprocessingRun | EpochRun | ErpRun | None:
    if isinstance(run.output_metadata.get("batch_id"), str):
        return run
    if isinstance(run, EpochRun):
        preprocessing_run = run_repository.get_preprocessing_run(
            run.config.preprocessing_run_id
        )
        if preprocessing_run is not None and isinstance(
            preprocessing_run.output_metadata.get("batch_id"),
            str,
        ):
            return preprocessing_run
    if isinstance(run, ErpRun):
        epoch_run = run_repository.get_epoch_run(run.config.epoch_run_id)
        if epoch_run is not None:
            return _batch_source_run_for_run(epoch_run)
    return None


def _batch_item_for_run_id(
    batch: BatchRunPlan,
    run_id: str,
) -> BatchSubjectRunPlan | None:
    for item in batch.items:
        if run_id in item.run_ids.values():
            return item
    return None


def _batch_export_artifacts_for_run(
    run: PreprocessingRun | EpochRun | ErpRun,
) -> list[dict[str, str]]:
    batch_context = _batch_context_for_run(run)
    if batch_context is None:
        return []
    summary = batch_context.get("summary_artifact")
    if not isinstance(summary, dict) or not isinstance(summary.get("path"), str):
        return []
    return [
        {
            "logical_name": "batch_summary",
            "artifact_type": "batch_summary_json",
            "path": summary["path"],
            "archive_path": "batch/batch_summary.json",
        }
    ]


def _write_phase_d_metadata_artifact(
    run: PreprocessingRun | EpochRun | ErpRun,
    output_directory: Path,
) -> tuple[Path, dict]:
    payload = _phase_d_metadata_for_run(run)
    path = output_directory / "phase_d_metadata.json"
    _write_json_file(path, payload)
    return path, payload


def _phase_d_metadata_for_run(run: PreprocessingRun | EpochRun | ErpRun) -> dict:
    dataset = registry_repository.get_dataset(run.dataset_id)
    recording = registry_repository.get_recording(run.dataset_id)
    event_log = registry_repository.get_event_log(run.dataset_id)
    recording_metadata = recording.metadata if recording is not None else None
    warnings = _phase_d_optional_metadata_warnings(
        recording=recording,
        event_log=event_log,
    )

    return {
        "schema_version": 1,
        "dataset": {
            "dataset_id": dataset.dataset_id if dataset is not None else run.dataset_id,
            "project_id": dataset.project_id if dataset is not None else None,
            "experiment_id": dataset.experiment_id if dataset is not None else None,
            "participant_id": dataset.participant_id if dataset is not None else None,
            "session_id": dataset.session_id if dataset is not None else None,
            "status": dataset.status.value if dataset is not None else None,
            "metadata": dataset.metadata if dataset is not None else {},
        },
        "recording": {
            "recording_id": recording.recording_id if recording is not None else None,
            "file_id": recording.file_id if recording is not None else None,
            "source_files": [
                _source_file_metadata_payload(source_file).model_dump()
                for source_file in recording_metadata.source_files
            ]
            if recording_metadata is not None
            else [],
            "sidecar_discovery": recording_metadata.sidecar_discovery
            if recording_metadata is not None
            else {},
        },
        "event_log": {
            "event_log_id": event_log.event_log_id if event_log is not None else None,
            "file_id": event_log.file_id if event_log is not None else None,
            "row_count": event_log.row_count if event_log is not None else 0,
            "filter_count": event_log.filter_count if event_log is not None else 0,
            "condition_column": event_log.condition_column
            if event_log is not None
            else None,
            "mapping": event_log.mapping.__dict__ if event_log is not None else {},
            "provenance": event_log.provenance if event_log is not None else {},
            "source_columns": _event_source_column_summary(event_log)
            if event_log is not None
            else {"column_names": [], "example_values": {}},
        },
        "run": {
            "run_id": run.run_id,
            "run_kind": _run_kind_value(run),
            "status": _run_status_value(run),
            "warnings": run.warnings,
            "diagnostics": _diagnostics_report_payload(run.diagnostics),
        },
        "batch": _batch_context_for_run(run),
        "diagnostics": {
            "warnings": warnings,
        },
    }


def _phase_d_optional_metadata_warnings(
    *,
    recording: Recording | None,
    event_log: EventLog | None,
) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    if recording is not None and not recording.metadata.source_files:
        warnings.append(
            _optional_metadata_warning(
                "recording_source_files_missing",
                "Recording source file metadata is not available for this export.",
            )
        )
    if recording is not None and not recording.metadata.sidecar_discovery:
        warnings.append(
            _optional_metadata_warning(
                "sidecar_discovery_missing",
                "BIDS sidecar discovery metadata is not available for this recording.",
            )
        )
    if event_log is not None and not event_log.provenance:
        warnings.append(
            _optional_metadata_warning(
                "event_provenance_missing",
                "Event log provenance metadata is not available for this export.",
            )
        )
    return warnings


def _optional_metadata_warning(code: str, impact: str) -> dict[str, str]:
    return {
        "code": code,
        "severity": "warning",
        "source": "export_bundle",
        "impact": impact,
        "suggested_action": (
            "Re-ingest or remap the dataset with Phase D metadata enabled if this "
            "metadata is required for review."
        ),
    }


def _save_batch_item(
    batch: BatchRunPlan,
    updated_item: BatchSubjectRunPlan,
) -> BatchRunPlan:
    updated_batch = replace(
        batch,
        items=[
            updated_item if item.item_id == updated_item.item_id else item
            for item in batch.items
        ],
        updated_at_utc=_batch_updated_at(batch),
    )
    batch_repository.save_batch(updated_batch)
    return updated_batch


def _batch_status_from_items(items: list[BatchSubjectRunPlan]) -> BatchStatus:
    if items and all(item.status == BatchItemStatus.CANCELLED for item in items):
        return BatchStatus.CANCELLED
    if items and all(item.status == BatchItemStatus.COMPLETED for item in items):
        return BatchStatus.COMPLETED
    has_completed = any(item.status == BatchItemStatus.COMPLETED for item in items)
    has_failed = any(item.status == BatchItemStatus.FAILED for item in items)
    if has_completed and has_failed:
        return BatchStatus.PARTIAL
    if has_failed:
        return BatchStatus.FAILED
    if any(item.status == BatchItemStatus.CANCELLED for item in items):
        return BatchStatus.CANCELLED
    return BatchStatus.COMPLETED


def _batch_updated_at(batch: BatchRunPlan) -> str:
    now = _utc_now_iso()
    return now if now >= batch.created_at_utc else batch.created_at_utc


def _execute_preprocessing_run(run_id: str) -> None:
    run = run_repository.get_preprocessing_run(run_id)
    if run is None:
        return
    if run.status == PreprocessingRunStatus.CANCELLED:
        return
    if run.status in {
        PreprocessingRunStatus.COMPLETED,
        PreprocessingRunStatus.FAILED,
    }:
        return
    if run.status == PreprocessingRunStatus.CANCELLING:
        cancelled_run = replace(
            run,
            status=PreprocessingRunStatus.CANCELLED,
            finished_at_utc=_utc_now_iso(),
            cancel_requested_at_utc=run.cancel_requested_at_utc,
        )
        run_repository.save_preprocessing_run(cancelled_run)
        return

    input_path = run.output_metadata.get("input_path")
    output_path = run.output_path
    if not isinstance(input_path, str) or not output_path:
        failed_run = replace(
            run,
            status=PreprocessingRunStatus.FAILED,
            finished_at_utc=_utc_now_iso(),
            errors=["Preprocessing run is missing input or output paths."],
        )
        run_repository.save_preprocessing_run(failed_run)
        return

    worker_artifacts = _preprocessing_worker_artifact_paths(run_id)
    worker_metadata = _preprocessing_worker_metadata(worker_artifacts)
    running_run = replace(
        run,
        status=PreprocessingRunStatus.RUNNING,
        started_at_utc=_utc_now_iso(),
        output_metadata={**run.output_metadata, **worker_metadata},
    )
    run_repository.save_preprocessing_run(running_run)

    try:
        metadata = _run_preprocessing_subprocess(
            run_id=run_id,
            input_path=input_path,
            output_path=output_path,
            config=run.config,
            worker_artifacts=worker_artifacts,
        )
        worker_exit_code = metadata.pop("_worker_exit_code", None)
        completed_run_base = replace(
            running_run,
            output_metadata={
                **running_run.output_metadata,
                "worker_exit_code": worker_exit_code,
            },
        )
        output_file_path = Path(output_path)
        completed_warnings = [str(warning) for warning in metadata.get("warnings", [])]
        completed_run = replace(
            completed_run_base,
            status=PreprocessingRunStatus.COMPLETED,
            finished_at_utc=_utc_now_iso(),
            output_metadata=_preprocessing_completed_provenance(
                run=completed_run_base,
                output_path=output_file_path,
                processing_metadata=metadata,
            ),
            warnings=completed_warnings,
            diagnostics=_diagnostics_from_warnings(
                completed_warnings,
                "preprocessing",
            ),
        )
        current_run = run_repository.get_preprocessing_run(run_id)
        if current_run and current_run.status == PreprocessingRunStatus.CANCELLING:
            cancelled_warnings = _dedupe_strings(
                [
                    *current_run.warnings,
                    *completed_run.warnings,
                    "Run cancelled after preprocessing completed; output was retained.",
                ]
            )
            cancelled_run = replace(
                completed_run,
                status=PreprocessingRunStatus.CANCELLED,
                finished_at_utc=_utc_now_iso(),
                cancel_requested_at_utc=current_run.cancel_requested_at_utc,
                warnings=cancelled_warnings,
                diagnostics=_diagnostics_from_warnings(
                    cancelled_warnings,
                    "preprocessing",
                ),
            )
            run_repository.save_preprocessing_run(cancelled_run)
        else:
            run_repository.save_preprocessing_run(completed_run)
    except PreprocessingError as exc:
        current_run = run_repository.get_preprocessing_run(run_id)
        current_warnings = current_run.warnings if current_run else []
        failed_output_metadata = dict(running_run.output_metadata)
        worker_exit_code = getattr(exc, "worker_exit_code", None)
        if worker_exit_code is not None:
            failed_output_metadata["worker_exit_code"] = worker_exit_code
        next_status = (
            PreprocessingRunStatus.CANCELLED
            if current_run and current_run.status == PreprocessingRunStatus.CANCELLING
            else PreprocessingRunStatus.FAILED
        )
        failed_warnings = _dedupe_strings([*current_warnings, *exc.processing_warnings])
        failed_run = replace(
            running_run,
            status=next_status,
            finished_at_utc=_utc_now_iso(),
            cancel_requested_at_utc=(
                current_run.cancel_requested_at_utc if current_run else None
            ),
            warnings=failed_warnings,
            diagnostics=_diagnostics_from_warnings(
                failed_warnings,
                "preprocessing",
            ),
            errors=[str(exc)],
            output_metadata=failed_output_metadata,
        )
        run_repository.save_preprocessing_run(failed_run)


def _run_preprocessing_subprocess(
    run_id: str,
    input_path: str,
    output_path: str,
    config: PreprocessingConfig,
    worker_artifacts: dict[str, Path],
) -> dict:
    result, returncode, stderr = _run_worker_cli_subprocess(
        job="preprocessing",
        payload={
            "schema_version": 1,
            "job": "preprocessing",
            "run_id": run_id,
            "input_path": input_path,
            "output_path": output_path,
            "config": _preprocessing_config_payload(config),
        },
        worker_artifacts=worker_artifacts,
        is_cancel_requested=lambda: _is_cancellation_requested(run_id),
        cancellation_error=lambda: PreprocessingError(
            "Preprocessing cancelled.",
            processing_warnings=[
                "Cancellation terminated preprocessing subprocess."
            ],
        ),
        process_label="Preprocessing",
        error_cls=WorkerSubprocessError,
    )

    if result.get("status") == "completed":
        metadata = result.get("metadata")
        if isinstance(metadata, dict):
            metadata["_worker_exit_code"] = returncode
            return metadata
        raise PreprocessingError("Preprocessing subprocess returned invalid metadata.")

    warnings = result.get("warnings", [])
    if not isinstance(warnings, list):
        warnings = []
    raise WorkerSubprocessError(
        str(result.get("error") or _worker_process_error("Preprocessing", returncode, stderr)),
        worker_exit_code=returncode,
        processing_warnings=[str(warning) for warning in warnings],
    )


def _preprocessing_config_payload(config: PreprocessingConfig) -> dict:
    return asdict(config)


def _preprocessing_config_from_payload(
    payload: PreprocessingConfigPayload,
) -> PreprocessingConfig:
    data = payload.model_dump()
    return PreprocessingConfig(
        artifact_schema_version=data["artifact_schema_version"],
        high_pass_hz=data["high_pass_hz"],
        low_pass_hz=data["low_pass_hz"],
        notch_hz=data["notch_hz"],
        resample_hz=data["resample_hz"],
        reference=data["reference"],
        manual_bad_channels=list(data["manual_bad_channels"]),
        bad_channel_detection=BadChannelDetectionConfig(
            **data["bad_channel_detection"]
        ),
        bad_channel_interpolation=BadChannelInterpolationConfig(
            **data["bad_channel_interpolation"]
        ),
        ica=IcaConfig(**data["ica"]),
        artifact_handling=ArtifactHandlingConfig(**data["artifact_handling"]),
        qc=PreprocessingQcConfig(**data["qc"]),
    )


def _preprocessing_worker_artifact_paths(run_id: str) -> dict[str, Path]:
    return _worker_artifact_paths(run_repository.preprocessing_run_directory(run_id))


def _preprocessing_worker_metadata(
    worker_artifacts: dict[str, Path],
) -> dict[str, str | int | None]:
    return _worker_metadata(worker_artifacts)


def _worker_artifact_paths(run_directory: Path) -> dict[str, Path]:
    return {
        "payload": run_directory / "worker_payload.json",
        "result": run_directory / "worker_result.json",
        "stdout": run_directory / "worker_stdout.log",
        "stderr": run_directory / "worker_stderr.log",
    }


def _worker_metadata(worker_artifacts: dict[str, Path]) -> dict[str, str | int | None]:
    return {
        "worker_schema_version": 1,
        "worker_payload_path": str(worker_artifacts["payload"]),
        "worker_result_path": str(worker_artifacts["result"]),
        "worker_stdout_path": str(worker_artifacts["stdout"]),
        "worker_stderr_path": str(worker_artifacts["stderr"]),
        "worker_exit_code": None,
    }


def _worker_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    package_paths = [
        str(REPO_ROOT / "packages" / "eeg-core" / "src"),
        str(REPO_ROOT / "packages" / "eeg-io" / "src"),
        str(REPO_ROOT / "packages" / "eeg-processing" / "src"),
    ]
    existing_pythonpath = env.get("PYTHONPATH")
    if existing_pythonpath:
        package_paths.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(package_paths)
    return env


def _worker_cli_command(job: str, payload_path: Path, result_path: Path) -> list[str]:
    worker_command = os.environ.get("NEUROWEAVE_WORKER_COMMAND")
    if worker_command:
        return [
            worker_command,
            "worker",
            job,
            "--payload",
            str(payload_path),
            "--result",
            str(result_path),
        ]
    if getattr(sys, "frozen", False):
        return [
            sys.executable,
            "worker",
            job,
            "--payload",
            str(payload_path),
            "--result",
            str(result_path),
        ]
    return [
        sys.executable,
        "-m",
        "eeg_processing.worker_cli",
        job,
        "--payload",
        str(payload_path),
        "--result",
        str(result_path),
    ]


def _run_worker_cli_subprocess(
    *,
    job: str,
    payload: dict,
    worker_artifacts: dict[str, Path],
    is_cancel_requested,
    cancellation_error,
    process_label: str,
    error_cls,
) -> tuple[dict, int | None, str]:
    payload_path = worker_artifacts["payload"]
    result_path = worker_artifacts["result"]
    stdout_path = worker_artifacts["stdout"]
    stderr_path = worker_artifacts["stderr"]
    _write_worker_payload(payload_path, payload)

    process = subprocess.Popen(
        _worker_cli_command(job, payload_path, result_path),
        cwd=REPO_ROOT,
        env=_worker_subprocess_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    while process.poll() is None:
        try:
            process.wait(timeout=0.1)
        except subprocess.TimeoutExpired:
            pass
        if is_cancel_requested():
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            stdout, stderr = process.communicate()
            _write_worker_streams(stdout_path, stderr_path, stdout, stderr)
            raise cancellation_error()

    stdout, stderr = process.communicate()
    _write_worker_streams(stdout_path, stderr_path, stdout, stderr)
    result = _load_worker_result(
        result_path=result_path,
        returncode=process.returncode,
        stderr=stderr,
        process_label=process_label,
        error_cls=error_cls,
    )
    return result, process.returncode, stderr


def _write_worker_payload(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_worker_streams(
    stdout_path: Path,
    stderr_path: Path,
    stdout: str,
    stderr: str,
) -> None:
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")


def _load_worker_result(
    *,
    result_path: Path,
    returncode: int | None,
    stderr: str,
    process_label: str,
    error_cls,
) -> dict:
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise error_cls(
            _worker_process_error(process_label, returncode, stderr),
            worker_exit_code=returncode,
        ) from exc
    except json.JSONDecodeError as exc:
        raise error_cls(
            f"{process_label} subprocess returned invalid JSON.",
            worker_exit_code=returncode,
        ) from exc

    if not isinstance(result, dict):
        raise error_cls(
            f"{process_label} subprocess returned a non-object result.",
            worker_exit_code=returncode,
        )
    return result


def _worker_process_error(
    process_label: str,
    returncode: int | None,
    stderr: str,
) -> str:
    message = f"{process_label} subprocess exited with code {returncode}."
    stderr = stderr.strip()
    if stderr:
        return f"{message} stderr: {stderr}"
    return message


def _execute_epoch_run(run_id: str) -> None:
    run = run_repository.get_epoch_run(run_id)
    if run is None:
        return
    if run.status == EpochRunStatus.CANCELLED:
        return
    if run.status in {
        EpochRunStatus.COMPLETED,
        EpochRunStatus.FAILED,
    }:
        return
    if run.status == EpochRunStatus.CANCELLING:
        cancelled_run = replace(
            run,
            status=EpochRunStatus.CANCELLED,
            finished_at_utc=_utc_now_iso(),
            cancel_requested_at_utc=run.cancel_requested_at_utc,
        )
        run_repository.save_epoch_run(cancelled_run)
        return

    preprocessing_run = run_repository.get_preprocessing_run(
        run.config.preprocessing_run_id
    )
    event_log = registry_repository.get_event_log(run.dataset_id)
    if (
        preprocessing_run is None
        or event_log is None
        or not preprocessing_run.output_path
        or not run.output_path
    ):
        failed_run = replace(
            run,
            status=EpochRunStatus.FAILED,
            finished_at_utc=_utc_now_iso(),
            errors=["Epoch run is missing preprocessing output or event data."],
        )
        run_repository.save_epoch_run(failed_run)
        return

    worker_artifacts = _epoching_worker_artifact_paths(run_id)
    worker_metadata = _epoching_worker_metadata(worker_artifacts)
    running_run = replace(
        run,
        status=EpochRunStatus.RUNNING,
        started_at_utc=_utc_now_iso(),
        output_metadata={**run.output_metadata, **worker_metadata},
    )
    run_repository.save_epoch_run(running_run)

    try:
        input_path = _resolve_preprocessing_output_path(preprocessing_run)
        if input_path is None:
            raise EpochingError("Preprocessing output file was not found.")
        metadata = _run_epoching_subprocess(
            run_id=run_id,
            input_path=str(input_path),
            output_path=run.output_path,
            event_log=event_log,
            config=run.config,
            preprocessing_run_id=preprocessing_run.run_id,
            worker_artifacts=worker_artifacts,
        )
        worker_exit_code = metadata.pop("_worker_exit_code", None)
        completed_run_base = replace(
            running_run,
            output_metadata={
                **running_run.output_metadata,
                "worker_exit_code": worker_exit_code,
            },
        )
        output_file_path = Path(run.output_path)
        completed_warnings = _dedupe_strings(
            [
                *running_run.warnings,
                *[str(warning) for warning in metadata.get("warnings", [])],
            ]
        )
        completed_run = replace(
            completed_run_base,
            status=EpochRunStatus.COMPLETED,
            finished_at_utc=_utc_now_iso(),
            output_metadata=_epoch_completed_provenance(
                run=completed_run_base,
                output_path=output_file_path,
                processing_metadata=metadata,
            ),
            warnings=completed_warnings,
            diagnostics=_diagnostics_from_warnings(completed_warnings, "epoch"),
        )
        current_run = run_repository.get_epoch_run(run_id)
        if current_run and current_run.status == EpochRunStatus.CANCELLING:
            cancelled_warnings = _dedupe_strings(
                [
                    *current_run.warnings,
                    *completed_run.warnings,
                    "Run cancelled after epoching completed; output was retained.",
                ]
            )
            cancelled_run = replace(
                completed_run,
                status=EpochRunStatus.CANCELLED,
                finished_at_utc=_utc_now_iso(),
                cancel_requested_at_utc=current_run.cancel_requested_at_utc,
                warnings=cancelled_warnings,
                diagnostics=_diagnostics_from_warnings(cancelled_warnings, "epoch"),
            )
            run_repository.save_epoch_run(cancelled_run)
        else:
            run_repository.save_epoch_run(completed_run)
    except EpochingError as exc:
        current_run = run_repository.get_epoch_run(run_id)
        current_warnings = current_run.warnings if current_run else []
        failed_output_metadata = dict(running_run.output_metadata)
        worker_exit_code = getattr(exc, "worker_exit_code", None)
        if worker_exit_code is not None:
            failed_output_metadata["worker_exit_code"] = worker_exit_code
        next_status = (
            EpochRunStatus.CANCELLED
            if current_run and current_run.status == EpochRunStatus.CANCELLING
            else EpochRunStatus.FAILED
        )
        failed_warnings = _dedupe_strings([*current_warnings, *exc.processing_warnings])
        failed_run = replace(
            running_run,
            status=next_status,
            finished_at_utc=_utc_now_iso(),
            cancel_requested_at_utc=(
                current_run.cancel_requested_at_utc if current_run else None
            ),
            warnings=failed_warnings,
            diagnostics=_diagnostics_from_warnings(failed_warnings, "epoch"),
            errors=[str(exc)],
            output_metadata=failed_output_metadata,
        )
        run_repository.save_epoch_run(failed_run)


def _run_epoching_subprocess(
    run_id: str,
    input_path: str,
    output_path: str,
    event_log: EventLog,
    config: EpochConfig,
    preprocessing_run_id: str,
    worker_artifacts: dict[str, Path],
) -> dict:
    result, returncode, stderr = _run_worker_cli_subprocess(
        job="epoching",
        payload={
            "schema_version": 1,
            "job": "epoching",
            "run_id": run_id,
            "input_path": input_path,
            "output_path": output_path,
            "event_log": asdict(event_log),
            "config": _epoch_config_payload(config),
        },
        worker_artifacts=worker_artifacts,
        is_cancel_requested=lambda: _is_epoch_cancellation_requested(run_id),
        cancellation_error=lambda: EpochingError(
            "Epoching cancelled.",
            processing_warnings=["Cancellation terminated epoching subprocess."],
        ),
        process_label="Epoching",
        error_cls=EpochWorkerSubprocessError,
    )

    if result.get("status") == "completed":
        metadata = result.get("metadata")
        if isinstance(metadata, dict):
            metadata["_worker_exit_code"] = returncode
            return metadata
        raise EpochingError("Epoching subprocess returned invalid metadata.")

    warnings = result.get("warnings", [])
    if not isinstance(warnings, list):
        warnings = []
    raise EpochWorkerSubprocessError(
        str(
            result.get("error")
            or _worker_process_error("Epoching", returncode, stderr)
        ),
        worker_exit_code=returncode,
        processing_warnings=[str(warning) for warning in warnings],
    )


def _epoch_config_payload(config: EpochConfig) -> dict:
    return {
        "preprocessing_run_id": config.preprocessing_run_id,
        "condition_field": config.condition_field,
        "tmin_seconds": config.tmin_seconds,
        "tmax_seconds": config.tmax_seconds,
        "baseline_start_seconds": config.baseline_start_seconds,
        "baseline_end_seconds": config.baseline_end_seconds,
        "reject_eeg_uv": config.reject_eeg_uv,
    }


def _epoching_worker_artifact_paths(run_id: str) -> dict[str, Path]:
    return _worker_artifact_paths(run_repository.epoch_run_directory(run_id))


def _epoching_worker_metadata(
    worker_artifacts: dict[str, Path],
) -> dict[str, str | int | None]:
    return _worker_metadata(worker_artifacts)


def _execute_erp_run(run_id: str) -> None:
    run = run_repository.get_erp_run(run_id)
    if run is None:
        return
    if run.status == ErpRunStatus.CANCELLED:
        return
    if run.status in {
        ErpRunStatus.COMPLETED,
        ErpRunStatus.FAILED,
    }:
        return
    if run.status == ErpRunStatus.CANCELLING:
        cancelled_run = replace(
            run,
            status=ErpRunStatus.CANCELLED,
            finished_at_utc=_utc_now_iso(),
            cancel_requested_at_utc=run.cancel_requested_at_utc,
        )
        run_repository.save_erp_run(cancelled_run)
        return

    epoch_run = run_repository.get_epoch_run(run.config.epoch_run_id)
    if epoch_run is None or not epoch_run.output_path or not run.output_path:
        failed_run = replace(
            run,
            status=ErpRunStatus.FAILED,
            finished_at_utc=_utc_now_iso(),
            errors=["ERP run is missing epoch output data."],
        )
        run_repository.save_erp_run(failed_run)
        return

    worker_artifacts = _erp_worker_artifact_paths(run_id)
    worker_metadata = _erp_worker_metadata(worker_artifacts)
    running_run = replace(
        run,
        status=ErpRunStatus.RUNNING,
        started_at_utc=_utc_now_iso(),
        output_metadata={**run.output_metadata, **worker_metadata},
    )
    run_repository.save_erp_run(running_run)

    try:
        output_path = Path(run.output_path)
        epochs_path = _resolve_epoch_output_path(epoch_run)
        if epochs_path is None:
            raise ErpError("Epoch output file was not found.")
        metadata = _run_erp_subprocess(
            run_id=run_id,
            epochs_path=str(epochs_path),
            output_directory=str(output_path.parent),
            config=run.config,
            worker_artifacts=worker_artifacts,
        )
        worker_exit_code = metadata.pop("_worker_exit_code", None)
        completed_run_base = replace(
            running_run,
            output_metadata={
                **running_run.output_metadata,
                "worker_exit_code": worker_exit_code,
            },
        )
        completed_warnings = _dedupe_strings(
            [
                *running_run.warnings,
                *[str(warning) for warning in metadata.get("warnings", [])],
            ]
        )
        completed_run = replace(
            completed_run_base,
            status=ErpRunStatus.COMPLETED,
            finished_at_utc=_utc_now_iso(),
            output_metadata=_erp_completed_provenance(
                run=completed_run_base,
                output_path=output_path,
                processing_metadata=metadata,
            ),
            warnings=completed_warnings,
            diagnostics=_diagnostics_from_warnings(completed_warnings, "erp"),
        )
        current_run = run_repository.get_erp_run(run_id)
        if current_run and current_run.status == ErpRunStatus.CANCELLING:
            cancelled_warnings = _dedupe_strings(
                [
                    *current_run.warnings,
                    *completed_run.warnings,
                    "Run cancelled after ERP generation completed; output was retained.",
                ]
            )
            cancelled_run = replace(
                completed_run,
                status=ErpRunStatus.CANCELLED,
                finished_at_utc=_utc_now_iso(),
                cancel_requested_at_utc=current_run.cancel_requested_at_utc,
                warnings=cancelled_warnings,
                diagnostics=_diagnostics_from_warnings(cancelled_warnings, "erp"),
            )
            run_repository.save_erp_run(cancelled_run)
        else:
            run_repository.save_erp_run(completed_run)
    except ErpError as exc:
        current_run = run_repository.get_erp_run(run_id)
        current_warnings = current_run.warnings if current_run else []
        failed_output_metadata = dict(running_run.output_metadata)
        worker_exit_code = getattr(exc, "worker_exit_code", None)
        if worker_exit_code is not None:
            failed_output_metadata["worker_exit_code"] = worker_exit_code
        next_status = (
            ErpRunStatus.CANCELLED
            if current_run and current_run.status == ErpRunStatus.CANCELLING
            else ErpRunStatus.FAILED
        )
        failed_warnings = _dedupe_strings([*current_warnings, *exc.processing_warnings])
        failed_run = replace(
            running_run,
            status=next_status,
            finished_at_utc=_utc_now_iso(),
            cancel_requested_at_utc=(
                current_run.cancel_requested_at_utc if current_run else None
            ),
            warnings=failed_warnings,
            diagnostics=_diagnostics_from_warnings(failed_warnings, "erp"),
            errors=[str(exc)],
            output_metadata=failed_output_metadata,
        )
        run_repository.save_erp_run(failed_run)


def _run_erp_subprocess(
    run_id: str,
    epochs_path: str,
    output_directory: str,
    config: ErpConfig,
    worker_artifacts: dict[str, Path],
) -> dict:
    result, returncode, stderr = _run_worker_cli_subprocess(
        job="erp",
        payload={
            "schema_version": 1,
            "job": "erp",
            "run_id": run_id,
            "epochs_path": epochs_path,
            "output_directory": output_directory,
            "config": _erp_config_payload(config),
        },
        worker_artifacts=worker_artifacts,
        is_cancel_requested=lambda: _is_erp_cancellation_requested(run_id),
        cancellation_error=lambda: ErpError(
            "ERP generation cancelled.",
            processing_warnings=[
                "Cancellation terminated ERP generation subprocess."
            ],
        ),
        process_label="ERP",
        error_cls=ErpWorkerSubprocessError,
    )

    if result.get("status") == "completed":
        metadata = result.get("metadata")
        if isinstance(metadata, dict):
            metadata["_worker_exit_code"] = returncode
            return metadata
        raise ErpError("ERP subprocess returned invalid metadata.")

    warnings = result.get("warnings", [])
    if not isinstance(warnings, list):
        warnings = []
    raise ErpWorkerSubprocessError(
        str(
            result.get("error")
            or _worker_process_error("ERP", returncode, stderr)
        ),
        worker_exit_code=returncode,
        processing_warnings=[str(warning) for warning in warnings],
    )


def _erp_config_payload(config: ErpConfig) -> dict:
    return {
        "epoch_run_id": config.epoch_run_id,
        "conditions": config.conditions,
        "picks": config.picks,
        "method": config.method,
        "plot_mode": config.plot_mode,
        "plot_channel": config.plot_channel,
    }


def _erp_worker_artifact_paths(run_id: str) -> dict[str, Path]:
    return _worker_artifact_paths(run_repository.erp_run_directory(run_id))


def _erp_worker_metadata(
    worker_artifacts: dict[str, Path],
) -> dict[str, str | int | None]:
    return _worker_metadata(worker_artifacts)


def _is_cancellation_requested(run_id: str) -> bool:
    run = run_repository.get_preprocessing_run(run_id)
    return run is not None and run.status in {
        PreprocessingRunStatus.CANCELLING,
        PreprocessingRunStatus.CANCELLED,
    }


def _is_epoch_cancellation_requested(run_id: str) -> bool:
    run = run_repository.get_epoch_run(run_id)
    return run is not None and run.status in {
        EpochRunStatus.CANCELLING,
        EpochRunStatus.CANCELLED,
    }


def _is_erp_cancellation_requested(run_id: str) -> bool:
    run = run_repository.get_erp_run(run_id)
    return run is not None and run.status in {
        ErpRunStatus.CANCELLING,
        ErpRunStatus.CANCELLED,
    }


def _validate_preprocessing_config(
    config: PreprocessingConfig,
    recording: Recording,
) -> list[str]:
    errors: list[str] = []
    sampling_rate = recording.metadata.sampling_rate_hz
    nyquist = sampling_rate / 2

    if (
        config.high_pass_hz is not None
        and config.low_pass_hz is not None
        and config.high_pass_hz >= config.low_pass_hz
    ):
        errors.append("high_pass_hz must be lower than low_pass_hz.")

    for field_name, value in (
        ("high_pass_hz", config.high_pass_hz),
        ("low_pass_hz", config.low_pass_hz),
        ("notch_hz", config.notch_hz),
    ):
        if value is not None and value >= nyquist:
            errors.append(
                f"{field_name} must be lower than the Nyquist frequency ({nyquist:g} Hz)."
            )

    if config.resample_hz is not None and config.resample_hz > sampling_rate:
        errors.append(
            f"resample_hz must not exceed the input sampling rate ({sampling_rate:g} Hz)."
        )

    if config.reference:
        reference = config.reference.strip().lower()
        if reference not in {"average", "avg", "none", "original"}:
            channel_names = set(recording.metadata.channel_names)
            requested_channels = [
                channel.strip()
                for channel in config.reference.split(",")
                if channel.strip()
            ]
            if not requested_channels:
                errors.append("reference must be average, none, or existing channel names.")
            else:
                missing_channels = [
                    channel
                    for channel in requested_channels
                    if channel not in channel_names
                ]
                if missing_channels:
                    errors.append(
                        "reference contains unknown channels: "
                        + ", ".join(missing_channels)
                    )

    channel_names = set(recording.metadata.channel_names)
    for field_name, requested_channels in (
        ("manual_bad_channels", config.manual_bad_channels),
        ("ica.eog_channels", config.ica.eog_channels),
        ("ica.ecg_channels", config.ica.ecg_channels),
        ("artifact_handling.eog_channels", config.artifact_handling.eog_channels),
        ("artifact_handling.ecg_channels", config.artifact_handling.ecg_channels),
    ):
        missing_channels = [
            channel for channel in requested_channels if channel not in channel_names
        ]
        if missing_channels:
            errors.append(
                f"{field_name} contains unknown channels: "
                + ", ".join(missing_channels)
            )

    if (
        config.bad_channel_detection.enabled
        and config.bad_channel_detection.method == "none"
    ):
        errors.append(
            "bad_channel_detection.method must not be none when detection is enabled."
        )

    if not config.bad_channel_detection.enabled and config.bad_channel_detection.method != "none":
        errors.append(
            "bad_channel_detection.enabled must be true when a detection method is selected."
        )

    if not config.ica.enabled and config.ica.exclude_components:
        errors.append("ica.enabled must be true when exclude_components is provided.")

    if config.ica.enabled:
        if any(component < 0 for component in config.ica.exclude_components):
            errors.append("ica.exclude_components must contain non-negative integers.")
        if isinstance(config.ica.n_components, float):
            if config.ica.n_components > 1 and not config.ica.n_components.is_integer():
                errors.append("ica.n_components as a float must be at most 1.")
            elif config.ica.n_components.is_integer():
                eeg_channel_count = len(recording.metadata.channel_names)
                if int(config.ica.n_components) > eeg_channel_count:
                    errors.append(
                        f"ica.n_components must not exceed the channel count ({eeg_channel_count})."
                    )
        if isinstance(config.ica.n_components, int):
            eeg_channel_count = len(recording.metadata.channel_names)
            if config.ica.n_components > eeg_channel_count:
                errors.append(
                    f"ica.n_components must not exceed the channel count ({eeg_channel_count})."
                )

    return errors


def _validate_epoch_config(
    config: EpochConfig,
    dataset: IngestionDataset,
    preprocessing_run: PreprocessingRun | None,
    event_log: EventLog | None,
    recording: Recording | None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if dataset.status != DatasetStatus.VALID:
        errors.append("Dataset must be valid before epoching.")

    if preprocessing_run is None:
        errors.append("Preprocessing run not found.")
    else:
        if preprocessing_run.dataset_id != dataset.dataset_id:
            errors.append("Preprocessing run must belong to the selected dataset.")
        if preprocessing_run.status != PreprocessingRunStatus.COMPLETED:
            errors.append("Preprocessing run must be completed before epoching.")
        if not preprocessing_run.output_path:
            errors.append("Preprocessing run is missing an output path.")
        elif _resolve_preprocessing_output_path(preprocessing_run) is None:
            errors.append("Preprocessing output file was not found.")

    if event_log is None or not event_log.events:
        errors.append("Dataset must have mapped events before epoching.")

    if recording is None:
        errors.append("Recording metadata is required before epoching.")

    if config.tmin_seconds >= config.tmax_seconds:
        errors.append("tmin_seconds must be lower than tmax_seconds.")
    if config.tmax_seconds <= 0:
        errors.append("tmax_seconds must be greater than 0.")

    baseline_errors = _validate_epoch_baseline(config)
    errors.extend(baseline_errors)

    if config.condition_field not in SUPPORTED_CONDITION_FIELDS:
        errors.append(f"Unsupported condition field: {config.condition_field}.")

    if config.reject_eeg_uv is not None and config.reject_eeg_uv <= 0:
        errors.append("reject_eeg_uv must be greater than 0.")

    if errors:
        return errors, warnings

    assert event_log is not None
    candidate_events = [
        event
        for event in event_log.events
        if _epoch_condition_label(getattr(event, config.condition_field)) is not None
    ]
    if not candidate_events:
        return [
            f"No usable events found for condition field: {config.condition_field}."
        ], warnings

    output_duration = _epoch_output_duration_seconds(
        preprocessing_run=preprocessing_run,
        recording=recording,
    )
    output_sampling_rate = _epoch_output_sampling_rate_hz(
        preprocessing_run=preprocessing_run,
        recording=recording,
    )
    if output_sampling_rate is None or output_sampling_rate <= 0:
        return ["Epoch validation requires a positive output sampling rate."], warnings
    if output_duration is None or output_duration <= 0:
        return ["Epoch validation requires a positive output duration."], warnings

    out_of_bounds_count = 0
    for event in candidate_events:
        start_seconds = event.onset_seconds + config.tmin_seconds
        end_seconds = event.onset_seconds + config.tmax_seconds
        if start_seconds < 0 or end_seconds > output_duration:
            out_of_bounds_count += 1

    if out_of_bounds_count == len(candidate_events):
        return ["All candidate epoch windows are outside the recording bounds."], warnings

    if out_of_bounds_count:
        warnings.append(
            f"{out_of_bounds_count} candidate events fall outside the epoch window bounds and will be skipped."
        )

    return errors, warnings


def _validate_erp_config(
    config: ErpConfig,
    dataset_id: str,
    epoch_run: EpochRun | None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if epoch_run is None:
        errors.append("Epoch run not found.")
    else:
        if epoch_run.dataset_id != dataset_id:
            errors.append("Epoch run must belong to the selected dataset.")
        if epoch_run.status != EpochRunStatus.COMPLETED:
            errors.append("Epoch run must be completed before ERP generation.")
        if not epoch_run.output_path:
            errors.append("Epoch run is missing an output path.")
        elif _resolve_epoch_output_path(epoch_run) is None:
            errors.append("Epoch output file was not found.")

    if config.method != "mean":
        errors.append("ERP method must be 'mean'.")

    if config.plot_mode not in {"gfp", "channel"}:
        errors.append("ERP plot_mode must be 'gfp' or 'channel'.")
    if config.plot_mode == "channel" and not config.plot_channel:
        errors.append("ERP plot_channel is required when plot_mode is 'channel'.")

    if config.conditions is not None:
        conditions = [condition.strip() for condition in config.conditions]
        if not all(conditions):
            errors.append("ERP condition labels must not be empty.")
        if len(set(conditions)) != len(conditions):
            errors.append("ERP condition labels must be unique.")

    if config.picks is not None:
        picks = [pick.strip() for pick in config.picks]
        if not all(picks):
            errors.append("ERP picks must not be empty.")
        if len(set(picks)) != len(picks):
            errors.append("ERP picks must be unique.")

    return errors, warnings


def _validate_comparison_config(
    config_payload: ComparisonConfigPayload,
    run: ErpRun,
) -> list[str]:
    errors: list[str] = []
    if run.status != ErpRunStatus.COMPLETED:
        errors.append("ERP run must be completed before comparison summary.")
    if not run.output_path:
        errors.append("ERP run is missing metadata output path.")
    elif not Path(run.output_path).is_file():
        errors.append("ERP metadata file was not found.")
    if config_payload.metric != "mean_amplitude_uv":
        errors.append("Comparison metric must be 'mean_amplitude_uv'.")
    if config_payload.window_start_seconds >= config_payload.window_end_seconds:
        errors.append("window_start_seconds must be lower than window_end_seconds.")
    if config_payload.condition_a == config_payload.condition_b:
        errors.append("Comparison conditions must be different.")
    if config_payload.use_gfp and config_payload.channel:
        errors.append("Use either GFP or a channel, not both.")
    if not config_payload.use_gfp and not config_payload.channel:
        errors.append("A channel is required when use_gfp is false.")
    subject_ids = [
        observation.subject_id.strip()
        for observation in config_payload.paired_observations
    ]
    if any(not subject_id for subject_id in subject_ids):
        errors.append("Paired observation subject_id values must not be empty.")
    if len(subject_ids) != len(set(subject_ids)):
        errors.append("Paired observation subject_id values must be unique.")
    return errors


def _validate_epoch_baseline(config: EpochConfig) -> list[str]:
    errors: list[str] = []
    baseline_start = config.baseline_start_seconds
    baseline_end = config.baseline_end_seconds

    if baseline_start is None and baseline_end is None:
        return errors
    if baseline_start is None or baseline_end is None:
        return [
            "baseline_start_seconds and baseline_end_seconds must both be set or both be null."
        ]
    if baseline_start > baseline_end:
        errors.append(
            "baseline_start_seconds must be lower than or equal to baseline_end_seconds."
        )
    if baseline_start < config.tmin_seconds or baseline_end > config.tmax_seconds:
        errors.append("Baseline range must be inside the epoch time window.")
    return errors


def _epoch_output_duration_seconds(
    preprocessing_run: PreprocessingRun | None,
    recording: Recording | None,
) -> float | None:
    if preprocessing_run is not None:
        duration = preprocessing_run.output_metadata.get("output_duration_seconds")
        if isinstance(duration, (int, float)) and not isinstance(duration, bool):
            return float(duration)
    if recording is not None:
        return recording.metadata.duration_seconds
    return None


def _epoch_output_sampling_rate_hz(
    preprocessing_run: PreprocessingRun | None,
    recording: Recording | None,
) -> float | None:
    if preprocessing_run is not None:
        sampling_rate = preprocessing_run.output_metadata.get("output_sampling_rate_hz")
        if isinstance(sampling_rate, (int, float)) and not isinstance(
            sampling_rate,
            bool,
        ):
            return float(sampling_rate)
    if recording is not None:
        return recording.metadata.sampling_rate_hz
    return None


def _epoch_condition_label(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value).lower()

    label = str(value).strip()
    if not label:
        return None
    return label


def _find_uploaded_file(
    dataset_id: str,
    file_id: str,
) -> IngestionUploadedFile | None:
    for uploaded_file in registry_repository.list_uploaded_files(dataset_id):
        if uploaded_file.file_id == file_id:
            return uploaded_file
    return None


def _resolve_event_mapping(
    dataset: IngestionDataset,
    request_mapping: EventColumnMappingPayload | None,
    preset: str | None = None,
) -> EventColumnMapping:
    if request_mapping is not None:
        return EventColumnMapping(**request_mapping.model_dump())
    if preset is not None:
        return event_mapping_preset(preset)

    experiment = registry_repository.get_experiment(dataset.experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return experiment.default_event_mapping


def _event_row_filter_from_payload(
    payload: EventRowFilterPayload | None,
) -> EventRowFilter | None:
    if payload is None:
        return None
    return EventRowFilter(
        include=[
            EventRowFilterCondition(column=condition.column, equals=condition.equals)
            for condition in payload.include
        ],
        exclude=[
            EventRowFilterCondition(column=condition.column, equals=condition.equals)
            for condition in payload.exclude
        ],
    )


def _event_condition_column_from_payload(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if stripped.lower() in {"", "n/a", "na", "none", "null"}:
        return None
    return stripped


def _event_log_provenance(
    *,
    dataset_id: str,
    uploaded_file: IngestionUploadedFile,
    preset: str | None,
    preset_applied: bool,
    mapping: EventColumnMapping,
    row_filter: EventRowFilter | None,
    condition_column: str | None,
) -> dict:
    payload = build_event_log_provenance_payload(
        dataset_id=dataset_id,
        event_log_id=uploaded_file.file_id,
        event_file={
            "file_id": uploaded_file.file_id,
            "original_filename": uploaded_file.original_filename,
            "stored_path": uploaded_file.stored_path,
            "content_type": uploaded_file.content_type,
            "size_bytes": uploaded_file.size_bytes,
            "checksum_sha256": uploaded_file.checksum_sha256,
        },
        preset=preset,
        preset_applied=preset_applied,
        mapping_snapshot=asdict(mapping),
        row_filter_snapshot=asdict(row_filter) if row_filter is not None else None,
        created_at_utc=_utc_now_iso(),
    )
    payload["condition_column"] = condition_column
    payload["sources"].extend(
        _source_file_payload_from_upload(
            source_file,
            role="bids_sidecar",
            sidecar_type=_sidecar_type_for_path(Path(source_file.stored_path)),
        )
        for source_file in registry_repository.list_uploaded_files(dataset_id)
        if source_file.kind == UploadedFileKind.METADATA
    )
    return payload


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def _diagnostics_from_warnings(warnings: list[str], source: str) -> dict:
    return diagnostic_warnings_from_strings(warnings, source=source)


def _store_upload_file(file: UploadFile, destination_directory: Path) -> Path:
    destination_directory.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename(file.filename or "uploaded_eeg")
    destination = _available_upload_path(destination_directory / filename)
    with destination.open("wb") as destination_file:
        shutil.copyfileobj(file.file, destination_file)
    return destination


def _safe_filename(filename: str) -> str:
    return Path(filename).name.replace("\x00", "") or "uploaded_eeg"


def _available_upload_path(path: Path) -> Path:
    if not path.exists():
        return path

    parent = path.parent
    for index in range(1, 10_000):
        candidate = parent / _indexed_upload_filename(path.name, index)
        if not candidate.exists():
            return candidate
    raise HTTPException(status_code=409, detail="Could not allocate upload filename")


def _indexed_upload_filename(filename: str, index: int) -> str:
    lower_name = filename.lower()
    for suffix in (
        "_raw.fif.gz",
        "raw.fif.gz",
        "_sss.fif.gz",
        "_tsss.fif.gz",
        "_meg.fif.gz",
        "_eeg.fif.gz",
        "_ieeg.fif.gz",
        "_raw.fif",
        "raw.fif",
        "_sss.fif",
        "_tsss.fif",
        "_meg.fif",
        "_eeg.fif",
        "_ieeg.fif",
    ):
        if lower_name.endswith(suffix):
            prefix = filename[: -len(suffix)]
            return f"{prefix}-{index}{filename[-len(suffix):]}"

    path = Path(filename)
    return f"{path.stem}-{index}{path.suffix}"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
