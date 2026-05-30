import React, { useEffect, useMemo, useRef, useState } from "react";
import ReactDOM from "react-dom/client";
import "./styles.css";

type LoadState<T> =
  | { status: "idle" | "loading"; data: T | null; error: null }
  | { status: "success"; data: T; error: null }
  | { status: "error"; data: T | null; error: string };

type HealthResponse = {
  status: string;
  service: string;
};

type SampleDataset = {
  id: string;
  filename: string;
  format: string;
};

type SampleDatasetsResponse = {
  samples: SampleDataset[];
};

type DatasetMetadata = {
  id: string;
  format: string;
  channels: number;
  sampling_rate: number;
  duration_seconds: number;
  channel_names: string[];
  channel_details?: ChannelMetadata[];
  line_frequency_hz?: number | null;
  reference?: string | null;
};

type ChannelMetadata = {
  name: string;
  type: string | null;
  units: string | null;
  status: string | null;
  status_description: string | null;
};

type Project = {
  project_id: string;
  name: string;
  description: string | null;
  metadata: Record<string, MetadataValue>;
};

type ProjectsResponse = {
  projects: Project[];
};

type Experiment = {
  experiment_id: string;
  project_id: string;
  name: string;
  task_name: string | null;
  default_event_mapping: EventColumnMapping;
  metadata: Record<string, MetadataValue>;
};

type ExperimentsResponse = {
  experiments: Experiment[];
};

type Dataset = {
  dataset_id: string;
  project_id: string;
  experiment_id: string;
  participant_id: string;
  session_id: string;
  status: string;
  recording_id: string | null;
  event_log_id: string | null;
  metadata: Record<string, MetadataValue>;
};

type DatasetsResponse = {
  datasets: Dataset[];
};

type EventColumnMapping = {
  onset_seconds: string | null;
  duration_seconds: string | null;
  trial_type: string | null;
  stimulus: string | null;
  response: string | null;
  correct: string | null;
  reaction_time_seconds: string | null;
};

type EventMappingPreset = "" | "psychopy" | "bids_events" | "eeglab_annotations";

type EventRowFilterCondition = {
  column: string;
  equals: string | null;
};

type EventRowFilter = {
  include: EventRowFilterCondition[];
  exclude: EventRowFilterCondition[];
};

type EventRowFilterForm = {
  include: string;
  exclude: string;
};

type EventPreview = {
  columns: string[];
  delimiter: string;
  preview_rows: Record<string, string | null>[];
  row_count: number;
};

type EventUploadResponse = {
  dataset: Dataset;
  preview: EventPreview;
};

type NormalizedEvent = {
  onset_seconds: number;
  source_row: number;
  duration_seconds: number | null;
  trial_type: string | null;
  stimulus: string | null;
  response: string | null;
  correct: boolean | null;
  reaction_time_seconds: number | null;
  source_columns?: Record<string, string | null>;
};

type EventLogResponse = {
  event_log_id: string;
  dataset_id: string;
  file_id: string;
  mapping: EventColumnMapping;
  row_count: number;
  filter_count: number;
  condition_column?: string | null;
  events: NormalizedEvent[];
};

type ValidationIssue = {
  severity: "error" | "warning";
  code: string;
  message: string;
  field: string | null;
};

type ValidationReport = {
  dataset_id: string;
  status: string;
  valid: boolean;
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
  issues: ValidationIssue[];
};

type PreprocessingConfig = {
  artifact_schema_version: number;
  high_pass_hz: number | null;
  low_pass_hz: number | null;
  notch_hz: number | null;
  resample_hz: number | null;
  reference: string | null;
  manual_bad_channels: string[];
  bad_channel_detection: {
    enabled: boolean;
    method: "none" | "flat" | "deviation" | "ransac";
    minimum_correlation: number | null;
    zscore_threshold: number | null;
  };
  bad_channel_interpolation: {
    enabled: boolean;
    reset_bads: boolean;
  };
  artifact_handling: {
    eog_enabled: boolean;
    ecg_enabled: boolean;
    eog_channels: string[];
    ecg_channels: string[];
    create_annotations: boolean;
  };
  ica: {
    enabled: boolean;
    method: "fastica" | "infomax" | "picard";
    n_components: number | null;
    random_state: number;
    max_iter: number | "auto";
    exclude_components: number[];
    eog_channels: string[];
    ecg_channels: string[];
  };
};

type BadChannelDetectionMethod =
  PreprocessingConfig["bad_channel_detection"]["method"];
type IcaMethod = PreprocessingConfig["ica"]["method"];

type PreprocessingRun = {
  run_id: string;
  dataset_id: string;
  run_kind: string;
  schema_version: number;
  config: PreprocessingConfig;
  status: string;
  started_at_utc: string | null;
  finished_at_utc: string | null;
  cancel_requested_at_utc: string | null;
  output_path: string | null;
  output_metadata: Record<string, MetadataValue>;
  warnings: string[];
  diagnostics: RunDiagnostics;
  errors: string[];
};

type PreprocessingRunsResponse = {
  runs: PreprocessingRun[];
};

type EpochConfig = {
  preprocessing_run_id: string;
  condition_field: string;
  tmin_seconds: number;
  tmax_seconds: number;
  baseline_start_seconds: number | null;
  baseline_end_seconds: number | null;
  reject_eeg_uv: number | null;
};

type EpochRun = {
  run_id: string;
  dataset_id: string;
  run_kind: string;
  schema_version: number;
  config: EpochConfig;
  status: string;
  started_at_utc: string | null;
  finished_at_utc: string | null;
  cancel_requested_at_utc: string | null;
  output_path: string | null;
  output_metadata: Record<string, MetadataValue>;
  warnings: string[];
  diagnostics: RunDiagnostics;
  errors: string[];
};

type EpochRunsResponse = {
  runs: EpochRun[];
};

type ErpConfig = {
  epoch_run_id: string;
  conditions: string[] | null;
  picks: string[] | null;
  method: string;
  plot_mode: string;
  plot_channel: string | null;
};

type ErpRun = {
  run_id: string;
  dataset_id: string;
  run_kind: string;
  schema_version: number;
  config: ErpConfig;
  status: string;
  started_at_utc: string | null;
  finished_at_utc: string | null;
  cancel_requested_at_utc: string | null;
  output_path: string | null;
  output_metadata: Record<string, MetadataValue>;
  warnings: string[];
  diagnostics: RunDiagnostics;
  errors: string[];
};

type ErpRunsResponse = {
  runs: ErpRun[];
};

type WorkflowTemplateFieldPolicyEntry = {
  path: string;
  reason: string;
  source_value: unknown;
  source_value_summary: string | null;
  default_action: string | null;
};

type WorkflowTemplateFieldPolicy = {
  excluded_fields: WorkflowTemplateFieldPolicyEntry[];
  review_required_fields: WorkflowTemplateFieldPolicyEntry[];
  channel_specific_fields: string[];
};

type WorkflowTemplateEpochConfig = Omit<EpochConfig, "preprocessing_run_id">;

type WorkflowTemplateErpConfig = Omit<ErpConfig, "epoch_run_id">;

type WorkflowTemplateWorkflow = {
  preprocessing: PreprocessingConfig | null;
  epoch: WorkflowTemplateEpochConfig | null;
  erp: WorkflowTemplateErpConfig | null;
};

type WorkflowTemplateValidation = {
  valid: boolean;
  stale: boolean;
  errors: string[];
  warnings: string[];
  stale_reasons: string[];
};

type WorkflowTemplate = {
  schema_version: number;
  template_kind: string;
  template_id: string;
  name: string;
  description: string | null;
  created_at_utc: string;
  updated_at_utc: string;
  created_from: {
    dataset_id: string | null;
    preprocessing_run_id: string | null;
    epoch_run_id: string | null;
    erp_run_id: string | null;
  };
  workflow: WorkflowTemplateWorkflow;
  field_policy: WorkflowTemplateFieldPolicy;
  validation: WorkflowTemplateValidation;
  notes: string[];
  extra: Record<string, unknown>;
};

type WorkflowTemplatesResponse = {
  templates: WorkflowTemplate[];
};

type WorkflowTemplateApplyPreview = {
  template_id: string;
  target_dataset_id: string;
  status: "ready" | "requires_review" | "invalid";
  configs: WorkflowTemplateWorkflow;
  excluded_fields: WorkflowTemplateFieldPolicyEntry[];
  review_required_fields: WorkflowTemplateFieldPolicyEntry[];
  errors: string[];
  warnings: string[];
};

type BatchDatasetSelection = {
  dataset_ids: string[];
  project_id: string | null;
  experiment_id: string | null;
};

type BatchRunBindings = {
  preprocessing_run_id: string | null;
  epoch_run_id: string | null;
  erp_run_id: string | null;
};

type BatchSubjectRunPlan = {
  item_id: string;
  dataset_id: string;
  status: string;
  attempt: number;
  retry_of_item_id: string | null;
  configs: WorkflowTemplateWorkflow;
  bindings: BatchRunBindings;
  planned_steps: string[];
  run_ids: Record<string, string>;
  previous_run_ids: Record<string, string>;
  previous_error: string | null;
  excluded_fields: WorkflowTemplateFieldPolicyEntry[];
  review_required_fields: WorkflowTemplateFieldPolicyEntry[];
  warnings: string[];
  errors: string[];
};

type BatchRunPlan = {
  schema_version: number;
  batch_id: string;
  status: string;
  created_at_utc: string;
  updated_at_utc: string;
  request: {
    template_id: string;
    dataset_selection: BatchDatasetSelection;
    requested_by: string | null;
    continue_on_error: boolean;
    dry_run: boolean;
    metadata: Record<string, MetadataValue>;
  };
  template_snapshot: {
    template_id: string;
    template_name: string;
    template_updated_at_utc: string;
    captured_at_utc: string;
    template_digest_sha256: string;
    template: WorkflowTemplate;
  };
  items: BatchSubjectRunPlan[];
  warnings: string[];
  errors: string[];
};

type BatchRunsResponse = {
  batches: BatchRunPlan[];
};

type BatchItemFilter = "all" | "pending" | "completed" | "failed";

type DiagnosticWarning = {
  severity: "error" | "warning";
  source:
    | "bids"
    | "event_mapping"
    | "validation"
    | "worker"
    | "artifact"
    | "export_bundle"
    | "batch";
  code: string;
  impact: string | null;
  suggested_action: string | null;
};

type RunDiagnostics = {
  warnings?: DiagnosticWarning[];
};

type ComparisonConfig = {
  condition_a: string;
  condition_b: string;
  channel: string | null;
  use_gfp: boolean;
  window_start_seconds: number;
  window_end_seconds: number;
  metric: string;
};

type ComparisonSummaryResponse = {
  summary: Record<string, unknown>;
  erp_run: ErpRun;
};

type AnalysisReportResponse = {
  report: Record<string, unknown>;
  erp_run: ErpRun;
  report_url: string;
  report_path: string;
};

type ArtifactIntegrityItem = {
  logical_name: string;
  artifact_type: string;
  path: string;
  expected_size_bytes: number | null;
  expected_checksum_sha256: string | null;
  status: "ok" | "missing" | "mismatch";
  actual_size_bytes: number | null;
  actual_checksum_sha256: string | null;
};

type ArtifactIntegrityPayload = {
  schema_version: number;
  manifest_path: string;
  artifact_root: string;
  artifact_count: number;
  status: "ok" | "missing" | "mismatch";
  status_counts: {
    ok: number;
    missing: number;
    mismatch: number;
  };
  artifacts: ArtifactIntegrityItem[];
};

type ArtifactIntegrityResponse = {
  run_id: string;
  dataset_id: string;
  run_kind: string;
  integrity: ArtifactIntegrityPayload;
};

type QcSummaryResponse = {
  dataset_id: string;
  run_id: string;
  run_kind: string;
  summary: QcSummaryPayload;
};

type QcSummaryPayload = {
  schema_version: number;
  run_kind: string;
  artifact_manifest?: {
    artifact_count?: number;
    missing_artifacts?: { logical_name?: string; path?: string; exists?: boolean }[];
  };
  preprocessing?: Record<string, unknown>;
  epoch?: Record<string, unknown>;
  erp?: Record<string, unknown>;
  batch?: Record<string, unknown>;
  phase_d?: Record<string, unknown>;
};

type DatasetContext = {
  dataset: Dataset;
  eventLog: EventLogResponse | null;
  validation: ValidationReport | null;
  qcSummary: QcSummaryResponse | null;
  preprocessingRuns: PreprocessingRun[];
  epochRuns: EpochRun[];
  erpRuns: ErpRun[];
};

type MetadataValue = string | number | boolean | null;

type NoticeState = {
  tone: "ok" | "error" | "neutral";
  message: string;
} | null;

type MappingKey = keyof EventColumnMapping;
type ThemeMode = "dark" | "light";
type WorkspaceMode = "setup" | "analysis";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const THEME_STORAGE_KEY = "neuroweave-theme";
const ACTIVE_DATASET_STORAGE_KEY = "neuroweave-active-dataset";
const WORKSPACE_MODE_STORAGE_KEY = "neuroweave-workspace-mode";
const SUPPORTED_EEG_EXTENSIONS = [".fif", ".edf", ".bdf", ".set", ".vhdr"];
const SUPPORTED_EVENT_EXTENSIONS = [".csv", ".tsv"];
const EEG_EXAMPLE_PATH = "tests/fixtures/eeg/sample_resting_raw.fif";
const EVENT_EXAMPLE_PATH = "tests/fixtures/events/psychopy_minimal.csv";

const MAPPING_FIELDS: { key: MappingKey; label: string; required?: boolean }[] = [
  { key: "onset_seconds", label: "Onset", required: true },
  { key: "duration_seconds", label: "Duration" },
  { key: "trial_type", label: "Trial Type" },
  { key: "stimulus", label: "Stimulus" },
  { key: "response", label: "Response" },
  { key: "correct", label: "Correct" },
  { key: "reaction_time_seconds", label: "RT" },
];

const EMPTY_MAPPING: Record<MappingKey, string> = {
  onset_seconds: "",
  duration_seconds: "",
  trial_type: "",
  stimulus: "",
  response: "",
  correct: "",
  reaction_time_seconds: "",
};

const EVENT_MAPPING_PRESETS: {
  value: EventMappingPreset;
  label: string;
  mapping: Partial<Record<MappingKey, string>>;
}[] = [
  { value: "", label: "Custom", mapping: {} },
  {
    value: "psychopy",
    label: "PsychoPy",
    mapping: {
      onset_seconds: "stim_onset",
      duration_seconds: "stim_duration",
      trial_type: "condition",
      response: "key_resp.keys",
      correct: "key_resp.corr",
      reaction_time_seconds: "key_resp.rt",
    },
  },
  {
    value: "bids_events",
    label: "BIDS Events",
    mapping: {
      onset_seconds: "onset",
      duration_seconds: "duration",
      trial_type: "trial_type",
      stimulus: "stimulus",
      response: "response",
      correct: "correct",
      reaction_time_seconds: "response_time",
    },
  },
  {
    value: "eeglab_annotations",
    label: "EEGLAB Annotations",
    mapping: {
      onset_seconds: "onset",
      duration_seconds: "duration",
      trial_type: "type",
    },
  },
];

const EMPTY_ROW_FILTER: EventRowFilterForm = {
  include: "",
  exclude: "",
};

const DEFAULT_PREPROCESSING_CONFIG = {
  high_pass_hz: "1",
  low_pass_hz: "40",
  notch_hz: "",
  resample_hz: "",
  reference: "average",
  manual_bad_channels: [] as string[],
  bad_channel_interpolation: {
    enabled: false,
    reset_bads: true,
  },
  artifact_handling: {
    eog_enabled: false,
    ecg_enabled: false,
    eog_channels: "",
    ecg_channels: "",
    create_annotations: false,
  },
  bad_channel_detection: {
    enabled: false,
    method: "deviation",
    zscore_threshold: "5",
    minimum_correlation: "",
  },
  ica: {
    enabled: false,
    method: "fastica",
    n_components: "",
    random_state: "97",
    max_iter: "auto",
    exclude_components: "",
    eog_channels: "",
    ecg_channels: "",
  },
};

const CONDITION_FIELDS = ["trial_type", "stimulus", "response", "correct"] as const;

const DEFAULT_EPOCH_CONFIG = {
  preprocessing_run_id: "",
  condition_field: "trial_type",
  tmin_seconds: "-0.2",
  tmax_seconds: "0.8",
  baseline_enabled: true,
  baseline_start_seconds: "-0.2",
  baseline_end_seconds: "0",
  reject_eeg_uv: "",
};

const DEFAULT_ERP_CONFIG = {
  epoch_run_id: "",
  conditions: "",
  picks: "",
  method: "mean",
  plot_mode: "gfp",
  plot_channel: "",
};

const DEFAULT_COMPARISON_CONFIG = {
  erp_run_id: "",
  condition_a: "",
  condition_b: "",
  use_gfp: true,
  channel: "",
  window_start_seconds: "-0.05",
  window_end_seconds: "0.2",
  metric: "mean_amplitude_uv",
};

function App() {
  const [theme, setTheme] = useState<ThemeMode>(getInitialTheme);
  const [health, setHealth] = useState<LoadState<HealthResponse>>({
    status: "idle",
    data: null,
    error: null,
  });
  const [samples, setSamples] = useState<LoadState<SampleDataset[]>>({
    status: "idle",
    data: null,
    error: null,
  });
  const [projects, setProjects] = useState<LoadState<Project[]>>({
    status: "idle",
    data: null,
    error: null,
  });
  const [experiments, setExperiments] = useState<LoadState<Experiment[]>>({
    status: "idle",
    data: null,
    error: null,
  });
  const [datasets, setDatasets] = useState<LoadState<Dataset[]>>({
    status: "idle",
    data: null,
    error: null,
  });
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [selectedExperimentId, setSelectedExperimentId] = useState("");
  const [activeDatasetId, setActiveDatasetId] = useState(getInitialActiveDatasetId);
  const [selectedSampleId, setSelectedSampleId] = useState<string | null>(null);
  const [metadata, setMetadata] = useState<LoadState<DatasetMetadata>>({
    status: "idle",
    data: null,
    error: null,
  });
  const [projectForm, setProjectForm] = useState({
    name: "Memory EEG",
    description: "",
  });
  const [experimentForm, setExperimentForm] = useState({
    name: "Oddball task",
    task_name: "",
  });
  const [datasetForm, setDatasetForm] = useState({
    participant_label: "sub-001",
    participant_group: "",
    session_label: "ses-001",
  });
  const [eegFile, setEegFile] = useState<File | null>(null);
  const [eventFile, setEventFile] = useState<File | null>(null);
  const [uploadedEegFilename, setUploadedEegFilename] = useState<string | null>(
    null,
  );
  const [uploadedEventFilename, setUploadedEventFilename] = useState<string | null>(
    null,
  );
  const [eventPreview, setEventPreview] = useState<EventPreview | null>(null);
  const [mapping, setMapping] = useState<Record<MappingKey, string>>(EMPTY_MAPPING);
  const [eventMappingPreset, setEventMappingPreset] =
    useState<EventMappingPreset>("");
  const [eventRowFilter, setEventRowFilter] =
    useState<EventRowFilterForm>(EMPTY_ROW_FILTER);
  const [eventLog, setEventLog] = useState<EventLogResponse | null>(null);
  const [validation, setValidation] = useState<ValidationReport | null>(null);
  const [qcSummary, setQcSummary] = useState<LoadState<QcSummaryResponse | null>>({
    status: "idle",
    data: null,
    error: null,
  });
  const [preprocessingConfig, setPreprocessingConfig] = useState(
    DEFAULT_PREPROCESSING_CONFIG,
  );
  const [preprocessingRuns, setPreprocessingRuns] = useState<
    LoadState<PreprocessingRun[]>
  >({
    status: "idle",
    data: null,
    error: null,
  });
  const [epochConfig, setEpochConfig] = useState(DEFAULT_EPOCH_CONFIG);
  const [epochRuns, setEpochRuns] = useState<LoadState<EpochRun[]>>({
    status: "idle",
    data: null,
    error: null,
  });
  const [erpConfig, setErpConfig] = useState(DEFAULT_ERP_CONFIG);
  const [erpRuns, setErpRuns] = useState<LoadState<ErpRun[]>>({
    status: "idle",
    data: null,
    error: null,
  });
  const [artifactIntegrity, setArtifactIntegrity] = useState<
    Record<string, LoadState<ArtifactIntegrityPayload>>
  >({});
  const [workflowTemplates, setWorkflowTemplates] = useState<
    LoadState<WorkflowTemplate[]>
  >({
    status: "idle",
    data: null,
    error: null,
  });
  const [selectedWorkflowTemplateId, setSelectedWorkflowTemplateId] =
    useState("");
  const [lastWorkflowTemplatePreview, setLastWorkflowTemplatePreview] =
    useState<WorkflowTemplateApplyPreview | null>(null);
  const [batchRuns, setBatchRuns] = useState<LoadState<BatchRunPlan[]>>({
    status: "idle",
    data: null,
    error: null,
  });
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const [batchItemFilter, setBatchItemFilter] =
    useState<BatchItemFilter>("all");
  const [batchPreprocessingRuns, setBatchPreprocessingRuns] = useState<
    Record<string, PreprocessingRun>
  >({});
  const [comparisonConfig, setComparisonConfig] = useState(
    DEFAULT_COMPARISON_CONFIG,
  );
  const [notice, setNotice] = useState<NoticeState>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [workspaceMode, setWorkspaceMode] =
    useState<WorkspaceMode>(getInitialWorkspaceMode);
  const workspaceModeChosenRef = useRef(false);

  const selectedProject = useMemo(
    () =>
      projects.data?.find((project) => project.project_id === selectedProjectId) ??
      null,
    [projects.data, selectedProjectId],
  );
  const selectedExperiment = useMemo(
    () =>
      experiments.data?.find(
        (experiment) => experiment.experiment_id === selectedExperimentId,
      ) ?? null,
    [experiments.data, selectedExperimentId],
  );
  const activeDataset = useMemo(
    () =>
      datasets.data?.find((dataset) => dataset.dataset_id === activeDatasetId) ??
      null,
    [datasets.data, activeDatasetId],
  );
  const selectedSample = useMemo(
    () => samples.data?.find((sample) => sample.id === selectedSampleId) ?? null,
    [samples.data, selectedSampleId],
  );
  const completedPreprocessingRuns = useMemo(
    () =>
      (preprocessingRuns.data ?? []).filter(
        (run) => run.status === "completed" && Boolean(run.output_path),
      ),
    [preprocessingRuns.data],
  );
  const completedEpochRuns = useMemo(
    () =>
      (epochRuns.data ?? []).filter(
        (run) => run.status === "completed" && Boolean(run.output_path),
      ),
    [epochRuns.data],
  );
  const completedErpRuns = useMemo(
    () =>
      (erpRuns.data ?? []).filter((run) => {
        const conditionCount = run.output_metadata.condition_count;
        return (
          run.status === "completed" &&
          typeof conditionCount === "number" &&
          conditionCount >= 2
        );
      }),
    [erpRuns.data],
  );
  const batchEligibleDatasets = useMemo(
    () =>
      (datasets.data ?? []).filter(
        (dataset) =>
          dataset.status === "valid" &&
          (!activeDataset ||
            (dataset.project_id === activeDataset.project_id &&
              dataset.experiment_id === activeDataset.experiment_id)),
      ),
    [activeDataset, datasets.data],
  );
  const datasetsById = useMemo(
    () =>
      Object.fromEntries(
        (datasets.data ?? []).map((dataset) => [dataset.dataset_id, dataset]),
      ),
    [datasets.data],
  );
  const selectedBatch = useMemo(
    () =>
      batchRuns.data?.find((batch) => batch.batch_id === selectedBatchId) ??
      batchRuns.data?.[0] ??
      null,
    [batchRuns.data, selectedBatchId],
  );

  function chooseWorkspaceMode(mode: WorkspaceMode) {
    workspaceModeChosenRef.current = true;
    setWorkspaceMode(mode);
  }

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  useEffect(() => {
    if (activeDatasetId) {
      window.localStorage.setItem(ACTIVE_DATASET_STORAGE_KEY, activeDatasetId);
    } else {
      window.localStorage.removeItem(ACTIVE_DATASET_STORAGE_KEY);
    }
  }, [activeDatasetId]);

  useEffect(() => {
    window.localStorage.setItem(WORKSPACE_MODE_STORAGE_KEY, workspaceMode);
  }, [workspaceMode]);

  useEffect(() => {
    void refreshWorkspace();
    void refreshWorkflowTemplates();
    void refreshBatches();
  }, []);

  useEffect(() => {
    if (!selectedProjectId) {
      setExperiments({ status: "success", data: [], error: null });
      setSelectedExperimentId("");
      return;
    }

    let isCurrent = true;
    setExperiments({ status: "loading", data: null, error: null });
    fetchJson<ExperimentsResponse>(
      `/projects/${encodeURIComponent(selectedProjectId)}/experiments`,
    )
      .then((data) => {
        if (!isCurrent) {
          return;
        }
        setExperiments({ status: "success", data: data.experiments, error: null });
        setSelectedExperimentId((current) =>
          data.experiments.some(
            (experiment) => experiment.experiment_id === current,
          )
            ? current
            : data.experiments[0]?.experiment_id ?? "",
        );
      })
      .catch((error: unknown) => {
        if (isCurrent) {
          setExperiments({
            status: "error",
            data: null,
            error: getErrorMessage(error),
          });
        }
      });

    return () => {
      isCurrent = false;
    };
  }, [selectedProjectId]);

  useEffect(() => {
    if (!selectedSampleId) {
      setMetadata({ status: "idle", data: null, error: null });
      return;
    }

    let isCurrent = true;
    setMetadata({ status: "loading", data: null, error: null });

    fetchJson<DatasetMetadata>(
      `/datasets/samples/${encodeURIComponent(selectedSampleId)}/metadata`,
    )
      .then((data) => {
        if (isCurrent) {
          setMetadata({ status: "success", data, error: null });
        }
      })
      .catch((error: unknown) => {
        if (isCurrent) {
          setMetadata({
            status: "error",
            data: null,
            error: getErrorMessage(error),
          });
        }
      });

    return () => {
      isCurrent = false;
    };
  }, [selectedSampleId]);

  useEffect(() => {
    if (!activeDatasetId) {
      setEventLog(null);
      setEventPreview(null);
      setMapping(EMPTY_MAPPING);
      setEventMappingPreset("");
      setEventRowFilter(EMPTY_ROW_FILTER);
      setValidation(null);
      setQcSummary({ status: "idle", data: null, error: null });
      setPreprocessingRuns({ status: "idle", data: null, error: null });
      setEpochRuns({ status: "idle", data: null, error: null });
      setErpRuns({ status: "idle", data: null, error: null });
      setComparisonConfig(DEFAULT_COMPARISON_CONFIG);
      return;
    }

    let isCurrent = true;
    setPreprocessingRuns({ status: "loading", data: null, error: null });
    setEpochRuns({ status: "loading", data: null, error: null });
    setErpRuns({ status: "loading", data: null, error: null });
    setQcSummary({ status: "loading", data: null, error: null });
    setEventPreview(null);
    setMapping(EMPTY_MAPPING);
    setEventMappingPreset("");
    setEventRowFilter(EMPTY_ROW_FILTER);

    loadDatasetContext(activeDatasetId)
      .then((context) => {
        if (!isCurrent) {
          return;
        }
        updateDatasetInState(context.dataset);
        setEventLog(context.eventLog);
        setValidation(context.validation);
        setQcSummary({ status: "success", data: context.qcSummary, error: null });
        setPreprocessingRuns({
          status: "success",
          data: context.preprocessingRuns,
          error: null,
        });
        setEpochRuns({ status: "success", data: context.epochRuns, error: null });
        setErpRuns({ status: "success", data: context.erpRuns, error: null });
      })
      .catch((error: unknown) => {
        if (!isCurrent) {
          return;
        }
        const message = getErrorMessage(error);
        setEventLog(null);
        setValidation(null);
        setQcSummary({ status: "error", data: null, error: message });
        setPreprocessingRuns({ status: "error", data: null, error: message });
        setEpochRuns({ status: "error", data: null, error: message });
        setErpRuns({ status: "error", data: null, error: message });
        setNotice({ tone: "error", message });
      });

    return () => {
      isCurrent = false;
    };
  }, [activeDatasetId]);

  useEffect(() => {
    setEpochConfig((current) => {
      if (
        current.preprocessing_run_id &&
        completedPreprocessingRuns.some(
          (run) => run.run_id === current.preprocessing_run_id,
        )
      ) {
        return current;
      }
      return {
        ...current,
        preprocessing_run_id: completedPreprocessingRuns[0]?.run_id ?? "",
      };
    });
  }, [completedPreprocessingRuns]);

  useEffect(() => {
    setErpConfig((current) => {
      if (
        current.epoch_run_id &&
        completedEpochRuns.some((run) => run.run_id === current.epoch_run_id)
      ) {
        return current;
      }
      return {
        ...current,
        epoch_run_id: completedEpochRuns[0]?.run_id ?? "",
      };
    });
  }, [completedEpochRuns]);

  useEffect(() => {
    setComparisonConfig((current) => {
      const selectedRun =
        completedErpRuns.find((run) => run.run_id === current.erp_run_id) ??
        completedErpRuns[0] ??
        null;
      if (!selectedRun) {
        return { ...current, erp_run_id: "", condition_a: "", condition_b: "" };
      }
      const labels = getErpConditionLabels(selectedRun);
      const conditionA = labels.includes(current.condition_a)
        ? current.condition_a
        : labels[0] ?? "";
      const conditionB = labels.includes(current.condition_b)
        ? current.condition_b
        : labels.find((label) => label !== conditionA) ?? "";
      return {
        ...current,
        erp_run_id: selectedRun.run_id,
        condition_a: conditionA,
        condition_b: conditionB,
      };
    });
  }, [completedErpRuns]);

  useEffect(() => {
    if (workflowTemplates.status !== "success") {
      return;
    }
    setSelectedWorkflowTemplateId((current) =>
      workflowTemplates.data.some((template) => template.template_id === current)
        ? current
        : workflowTemplates.data[0]?.template_id ?? "",
    );
  }, [workflowTemplates]);

  useEffect(() => {
    if (batchRuns.status !== "success") {
      return;
    }
    setSelectedBatchId((current) =>
      batchRuns.data.some((batch) => batch.batch_id === current)
        ? current
        : batchRuns.data[0]?.batch_id ?? "",
    );
  }, [batchRuns]);

  useEffect(() => {
    if (!selectedBatch) {
      return;
    }
    void refreshBatchRunOutputs(selectedBatch);
  }, [selectedBatch]);

  useEffect(() => {
    const hasActiveRun =
      preprocessingRuns.data?.some((run) =>
        ["pending", "running", "cancelling"].includes(run.status),
      ) ?? false;
    if (!activeDatasetId || !hasActiveRun) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void refreshPreprocessingRuns(activeDatasetId, { silent: true });
    }, 2000);

    return () => window.clearInterval(intervalId);
  }, [activeDatasetId, preprocessingRuns.data]);

  useEffect(() => {
    const hasActiveRun =
      epochRuns.data?.some((run) =>
        ["pending", "running", "cancelling"].includes(run.status),
      ) ?? false;
    if (!activeDatasetId || !hasActiveRun) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void refreshEpochRuns(activeDatasetId, { silent: true });
    }, 2000);

    return () => window.clearInterval(intervalId);
  }, [activeDatasetId, epochRuns.data]);

  useEffect(() => {
    const hasActiveRun =
      erpRuns.data?.some((run) =>
        ["pending", "running", "cancelling"].includes(run.status),
      ) ?? false;
    if (!activeDatasetId || !hasActiveRun) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void refreshErpRuns(activeDatasetId, { silent: true });
    }, 2000);

    return () => window.clearInterval(intervalId);
  }, [activeDatasetId, erpRuns.data]);

  useEffect(() => {
    if (!selectedBatch || !isActiveBatchStatus(selectedBatch.status)) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void refreshBatchDetail(selectedBatch.batch_id, { silent: true });
    }, 2000);

    return () => window.clearInterval(intervalId);
  }, [selectedBatch]);

  async function refreshWorkspace() {
    setNotice(null);
    setHealth({ status: "loading", data: null, error: null });
    setSamples({ status: "loading", data: null, error: null });
    setProjects({ status: "loading", data: null, error: null });
    setDatasets({ status: "loading", data: null, error: null });
    setBatchRuns({ status: "loading", data: null, error: null });

    const [
      healthResult,
      samplesResult,
      projectsResult,
      datasetsResult,
      batchesResult,
    ] = await Promise.allSettled([
      fetchJson<HealthResponse>("/health"),
      fetchJson<SampleDatasetsResponse>("/datasets/samples"),
      fetchJson<ProjectsResponse>("/projects"),
      fetchJson<DatasetsResponse>("/datasets"),
      fetchJson<BatchRunsResponse>("/batches"),
    ]);

    if (healthResult.status === "fulfilled") {
      setHealth({ status: "success", data: healthResult.value, error: null });
    } else {
      setHealth({
        status: "error",
        data: null,
        error: getErrorMessage(healthResult.reason),
      });
    }

    if (samplesResult.status === "fulfilled") {
      setSamples({
        status: "success",
        data: samplesResult.value.samples,
        error: null,
      });
      setSelectedSampleId((current) =>
        current ??
        samplesResult.value.samples[0]?.id ??
        null,
      );
    } else {
      setSamples({
        status: "error",
        data: null,
        error: getErrorMessage(samplesResult.reason),
      });
    }

    if (projectsResult.status === "fulfilled") {
      const projectData = projectsResult.value.projects;
      setProjects({ status: "success", data: projectData, error: null });
      setSelectedProjectId((current) =>
        projectData.some((project) => project.project_id === current)
          ? current
          : projectData[0]?.project_id ?? "",
      );
    } else {
      setProjects({
        status: "error",
        data: null,
        error: getErrorMessage(projectsResult.reason),
      });
    }

    if (datasetsResult.status === "fulfilled") {
      const datasetData = datasetsResult.value.datasets;
      setDatasets({ status: "success", data: datasetData, error: null });
      setActiveDatasetId((current) =>
        datasetData.some((dataset) => dataset.dataset_id === current)
          ? current
          : datasetData[0]?.dataset_id ?? "",
      );
    } else {
      setDatasets({
        status: "error",
        data: null,
        error: getErrorMessage(datasetsResult.reason),
      });
    }

    if (batchesResult.status === "fulfilled") {
      setBatchRuns({
        status: "success",
        data: batchesResult.value.batches,
        error: null,
      });
    } else {
      setBatchRuns({
        status: "error",
        data: null,
        error: getErrorMessage(batchesResult.reason),
      });
    }
  }

  async function createProject(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectForm.name.trim()) {
      setNotice({ tone: "error", message: "Project name is required." });
      return;
    }

    await runAction("project", async () => {
      const project = await postJson<Project>("/projects", {
        name: projectForm.name.trim(),
        description: projectForm.description.trim() || null,
      });
      setProjectForm({ name: "", description: "" });
      setSelectedProjectId(project.project_id);
      await refreshProjects();
      setNotice({ tone: "ok", message: "Project created." });
    });
  }

  async function createExperiment(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) {
      setNotice({ tone: "error", message: "Select a project first." });
      return;
    }
    if (!experimentForm.name.trim()) {
      setNotice({ tone: "error", message: "Experiment name is required." });
      return;
    }

    await runAction("experiment", async () => {
      const experiment = await postJson<Experiment>(
        `/projects/${encodeURIComponent(selectedProjectId)}/experiments`,
        {
          name: experimentForm.name.trim(),
          task_name: experimentForm.task_name.trim() || null,
        },
      );
      setExperimentForm({ name: "", task_name: "" });
      setSelectedExperimentId(experiment.experiment_id);
      await refreshExperiments(selectedProjectId);
      setNotice({ tone: "ok", message: "Experiment created." });
    });
  }

  async function createDataset(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId || !selectedExperimentId) {
      setNotice({ tone: "error", message: "Select project and experiment first." });
      return;
    }
    if (!datasetForm.participant_label.trim() || !datasetForm.session_label.trim()) {
      setNotice({
        tone: "error",
        message: "Participant and session labels are required.",
      });
      return;
    }

    await runAction("dataset", async () => {
      const dataset = await postJson<Dataset>("/datasets", {
        project_id: selectedProjectId,
        experiment_id: selectedExperimentId,
        participant_label: datasetForm.participant_label.trim(),
        participant_group: datasetForm.participant_group.trim() || null,
        session_label: datasetForm.session_label.trim(),
      });
      setActiveDatasetId(dataset.dataset_id);
      setEventPreview(null);
      setEventLog(null);
      setUploadedEegFilename(null);
      setUploadedEventFilename(null);
      setValidation(null);
      setQcSummary({ status: "success", data: null, error: null });
      setPreprocessingRuns({ status: "success", data: [], error: null });
      setEpochRuns({ status: "success", data: [], error: null });
      setErpRuns({ status: "success", data: [], error: null });
      setEpochConfig(DEFAULT_EPOCH_CONFIG);
      setErpConfig(DEFAULT_ERP_CONFIG);
      setComparisonConfig(DEFAULT_COMPARISON_CONFIG);
      await refreshDatasets();
      setNotice({ tone: "ok", message: "Dataset created." });
    });
  }

  function chooseEegFile(file: File | null) {
    if (file && !hasSupportedExtension(file, SUPPORTED_EEG_EXTENSIONS)) {
      setEegFile(null);
      setNotice({
        tone: "error",
        message:
          "Unsupported EEG file. Choose a FIF, EDF, BDF, SET, or BrainVision VHDR file.",
      });
      return;
    }

    setEegFile(file);
  }

  function chooseEventFile(file: File | null) {
    if (file && !hasSupportedExtension(file, SUPPORTED_EVENT_EXTENSIONS)) {
      setEventFile(null);
      setNotice({
        tone: "error",
        message: "Unsupported event log. Choose a CSV or TSV file.",
      });
      return;
    }

    setEventFile(file);
  }

  async function uploadEegFile() {
    if (!activeDatasetId || !eegFile) {
      setNotice({
        tone: "error",
        message:
          "Select an active dataset and choose a supported EEG file before uploading.",
      });
      return;
    }

    await runAction("eeg-upload", async () => {
      const uploadedFilename = eegFile.name;
      const formData = new FormData();
      formData.append("file", eegFile);
      const response = await requestJson<{ dataset: Dataset }>(
        `/datasets/${encodeURIComponent(activeDatasetId)}/files/eeg`,
        {
          method: "POST",
          body: formData,
        },
      );
      setEegFile(null);
      setUploadedEegFilename(uploadedFilename);
      updateDatasetInState(response.dataset);
      setValidation(null);
      setNotice({ tone: "ok", message: "EEG file uploaded." });
    });
  }

  async function uploadEventFile() {
    if (!activeDatasetId || !eventFile) {
      setNotice({
        tone: "error",
        message:
          "Select an active dataset and choose a CSV or TSV event log before uploading.",
      });
      return;
    }

    await runAction("event-upload", async () => {
      const uploadedFilename = eventFile.name;
      const formData = new FormData();
      formData.append("file", eventFile);
      const response = await requestJson<EventUploadResponse>(
        `/datasets/${encodeURIComponent(activeDatasetId)}/files/events`,
        {
          method: "POST",
          body: formData,
        },
      );
      setEventFile(null);
      setUploadedEventFilename(uploadedFilename);
      setEventPreview(response.preview);
      setEventLog(null);
      setValidation(null);
      setMapping(
        getInitialMapping(
          response.preview.columns,
          selectedExperiment?.default_event_mapping ?? null,
        ),
      );
      setEventMappingPreset("");
      setEventRowFilter(EMPTY_ROW_FILTER);
      updateDatasetInState(response.dataset);
      setNotice({ tone: "ok", message: "Event log uploaded." });
    });
  }

  async function submitEventMapping() {
    if (!activeDatasetId) {
      setNotice({ tone: "error", message: "Select a dataset first." });
      return;
    }
    if (!eventMappingPreset && !mapping.onset_seconds) {
      setNotice({ tone: "error", message: "Map an onset column first." });
      return;
    }

    await runAction("event-mapping", async () => {
      const rowFilterPayload = normalizeRowFilterPayload(eventRowFilter);
      const eventLogResponse = await postJson<EventLogResponse>(
        `/datasets/${encodeURIComponent(activeDatasetId)}/events/mapping`,
        {
          ...(eventMappingPreset
            ? { preset: eventMappingPreset }
            : { mapping: normalizeMappingPayload(mapping) }),
          ...(rowFilterPayload ? { row_filter: rowFilterPayload } : {}),
        },
      );
      setEventLog(eventLogResponse);
      setValidation(null);
      setNotice({ tone: "ok", message: "Event mapping saved." });
    });
  }

  async function validateDataset() {
    if (!activeDatasetId) {
      setNotice({ tone: "error", message: "Select a dataset first." });
      return;
    }

    await runAction("validation", async () => {
      const report = await fetchJson<ValidationReport>(
        `/datasets/${encodeURIComponent(activeDatasetId)}/validation`,
      );
      setValidation(report);
      updateDatasetInState({
        ...(activeDataset as Dataset),
        status: report.status,
      });
      await refreshDatasets();
      setNotice({
        tone: report.valid ? "ok" : "error",
        message: report.valid ? "Dataset is valid." : "Dataset has blocking errors.",
      });
    });
  }

  async function beginPreprocessingHandoff() {
    if (!activeDataset || (validation?.valid !== true && activeDataset.status !== "valid")) {
      setNotice({
        tone: "error",
        message: "Validate a dataset before starting preprocessing.",
      });
      return;
    }

    const configError = getPreprocessingConfigError(preprocessingConfig);
    if (configError) {
      setNotice({ tone: "error", message: configError });
      return;
    }

    await runAction("preprocessing", async () => {
      const run = await postJson<PreprocessingRun>(
        `/datasets/${encodeURIComponent(activeDataset.dataset_id)}/preprocessing-runs`,
        normalizePreprocessingConfig(preprocessingConfig),
      );
      setPreprocessingRuns((current) => ({
        status: "success",
        data: [run, ...(current.data ?? [])],
        error: null,
      }));
      setNotice({
        tone: "neutral",
        message: `Preprocessing run ${run.run_id} queued.`,
      });
    });
  }

  async function beginEpochRun() {
    if (!activeDataset) {
      setNotice({ tone: "error", message: "Select a dataset first." });
      return;
    }

    const configError = getEpochConfigError(epochConfig);
    if (configError) {
      setNotice({ tone: "error", message: configError });
      return;
    }

    await runAction("epoch", async () => {
      const run = await postJson<EpochRun>(
        `/datasets/${encodeURIComponent(activeDataset.dataset_id)}/epoch-runs`,
        normalizeEpochConfig(epochConfig),
      );
      setEpochRuns((current) => ({
        status: "success",
        data: [run, ...(current.data ?? [])],
        error: null,
      }));
      setNotice({
        tone: "neutral",
        message: `Epoch run ${run.run_id} queued.`,
      });
    });
  }

  async function beginErpRun() {
    if (!activeDataset) {
      setNotice({ tone: "error", message: "Select a dataset first." });
      return;
    }

    const configError = getErpConfigError(erpConfig);
    if (configError) {
      setNotice({ tone: "error", message: configError });
      return;
    }

    await runAction("erp", async () => {
      const run = await postJson<ErpRun>(
        `/datasets/${encodeURIComponent(activeDataset.dataset_id)}/erp-runs`,
        normalizeErpConfig(erpConfig),
      );
      setErpRuns((current) => ({
        status: "success",
        data: [run, ...(current.data ?? [])],
        error: null,
      }));
      setNotice({
        tone: "neutral",
        message: `ERP run ${run.run_id} queued.`,
      });
    });
  }

  async function saveWorkflowTemplateFromRun(
    kind: "preprocessing" | "epoch" | "erp",
    run: PreprocessingRun | EpochRun | ErpRun,
  ) {
    if (run.status !== "completed") {
      setNotice({
        tone: "error",
        message: "Templates can only be saved from completed runs.",
      });
      return;
    }

    const runKeyByKind = {
      preprocessing: "preprocessing_run_id",
      epoch: "epoch_run_id",
      erp: "erp_run_id",
    } as const;

    await runAction(`template-save-${run.run_id}`, async () => {
      const template = await postJson<WorkflowTemplate>("/workflow-templates/from-run", {
        name: `${kind} template from ${run.run_id}`,
        description: `Created from completed ${kind} run ${run.run_id}.`,
        [runKeyByKind[kind]]: run.run_id,
      });
      await refreshWorkflowTemplates({ silent: true });
      setSelectedWorkflowTemplateId(template.template_id);
      setLastWorkflowTemplatePreview(null);
      const policySummary = formatTemplatePolicySummary(template.field_policy);
      setNotice({
        tone: "ok",
        message: `Workflow template saved.${policySummary ? ` ${policySummary}` : ""}`,
      });
    });
  }

  async function applySelectedWorkflowTemplate() {
    if (!activeDatasetId) {
      setNotice({ tone: "error", message: "Select a dataset first." });
      return;
    }
    if (!selectedWorkflowTemplateId) {
      setNotice({ tone: "error", message: "Select a workflow template first." });
      return;
    }

    const selectedPreprocessingRunId =
      epochConfig.preprocessing_run_id || completedPreprocessingRuns[0]?.run_id || null;
    const selectedEpochRunId =
      erpConfig.epoch_run_id || completedEpochRuns[0]?.run_id || null;

    await runAction("template-apply", async () => {
      const preview = await postJson<WorkflowTemplateApplyPreview>(
        `/workflow-templates/${encodeURIComponent(
          selectedWorkflowTemplateId,
        )}/apply-preview`,
        {
          target_dataset_id: activeDatasetId,
          preprocessing_run_id: selectedPreprocessingRunId,
          epoch_run_id: selectedEpochRunId,
        },
      );
      setLastWorkflowTemplatePreview(preview);

      if (preview.status === "invalid") {
        setNotice({
          tone: "error",
          message: preview.errors[0] ?? "Template preview is invalid.",
        });
        return;
      }

      if (preview.configs.preprocessing) {
        setPreprocessingConfig(
          preprocessingTemplateToForm(preview.configs.preprocessing),
        );
      }
      if (preview.configs.epoch) {
        setEpochConfig(
          epochTemplateToForm(
            preview.configs.epoch,
            selectedPreprocessingRunId ?? "",
          ),
        );
      }
      if (preview.configs.erp) {
        setErpConfig(
          erpTemplateToForm(preview.configs.erp, selectedEpochRunId ?? ""),
        );
      }

      setNotice({
        tone: preview.status === "ready" ? "ok" : "neutral",
        message:
          preview.status === "ready"
            ? "Workflow template applied to the current dataset config."
            : "Workflow template applied with review-needed fields shown.",
      });
    });
  }

  async function beginBatchRun() {
    if (!selectedWorkflowTemplateId) {
      setNotice({ tone: "error", message: "Select a workflow template first." });
      return;
    }
    if (batchEligibleDatasets.length === 0) {
      setNotice({
        tone: "error",
        message: "No valid datasets are available for this batch.",
      });
      return;
    }

    await runAction("batch-create", async () => {
      const batch = await postJson<BatchRunPlan>("/batches", {
        template_id: selectedWorkflowTemplateId,
        dataset_selection: {
          dataset_ids: batchEligibleDatasets.map((dataset) => dataset.dataset_id),
          project_id: (activeDataset?.project_id ?? selectedProjectId) || null,
          experiment_id:
            (activeDataset?.experiment_id ?? selectedExperimentId) || null,
        },
      });
      setBatchRuns((current) => ({
        status: "success",
        data: [
          batch,
          ...(current.data ?? []).filter((item) => item.batch_id !== batch.batch_id),
        ],
        error: null,
      }));
      setSelectedBatchId(batch.batch_id);
      await refreshBatchRunOutputs(batch);
      setNotice({
        tone: "neutral",
        message: `Batch ${batch.batch_id} queued for ${batch.items.length} dataset(s).`,
      });
    });
  }

  async function cancelBatchRun(batchId: string) {
    await runAction(`batch-cancel-${batchId}`, async () => {
      const batch = await requestJson<BatchRunPlan>(
        `/batches/${encodeURIComponent(batchId)}/cancel`,
        { method: "POST" },
      );
      updateBatchInState(batch);
      setNotice({
        tone: batch.status === "cancelled" ? "ok" : "neutral",
        message: `Batch ${batch.batch_id} ${batch.status}.`,
      });
    });
  }

  async function retryBatchItem(batchId: string, itemId: string) {
    await runAction(`batch-retry-${itemId}`, async () => {
      const batch = await requestJson<BatchRunPlan>(
        `/batches/${encodeURIComponent(batchId)}/items/${encodeURIComponent(
          itemId,
        )}/retry`,
        { method: "POST" },
      );
      updateBatchInState(batch);
      setSelectedBatchId(batch.batch_id);
      await refreshBatchRunOutputs(batch);
      setNotice({
        tone: "neutral",
        message: `Retry queued for ${itemId}.`,
      });
    });
  }

  async function beginComparisonSummary() {
    const configError = getComparisonConfigError(comparisonConfig);
    if (configError) {
      setNotice({ tone: "error", message: configError });
      return;
    }

    await runAction("comparison", async () => {
      const response = await postJson<ComparisonSummaryResponse>(
        `/erp-runs/${encodeURIComponent(
          comparisonConfig.erp_run_id,
        )}/comparison-summary`,
        normalizeComparisonConfig(comparisonConfig),
      );
      setErpRuns((current) => ({
        status: "success",
        data: (current.data ?? []).map((run) =>
          run.run_id === response.erp_run.run_id ? response.erp_run : run,
        ),
        error: null,
      }));
      setNotice({
        tone: "ok",
        message: "Comparison summary generated.",
      });
    });
  }

  async function downloadErpExportBundle(run: ErpRun) {
    if (!isErpExportReady(run)) {
      setNotice({
        tone: "error",
        message: "ERP export is available after a completed run writes artifacts.",
      });
      return;
    }

    await runAction(`export-${run.run_id}`, async () => {
      const response = await requestBlob(
        `/erp-runs/${encodeURIComponent(run.run_id)}/export-bundle`,
      );
      downloadBlob(
        response.blob,
        response.filename ?? `neuroweave_${run.dataset_id}_${run.run_id}.zip`,
      );
      setNotice({
        tone: "ok",
        message: `Export bundle downloaded for ${run.run_id}.`,
      });
    });
  }

  async function generateErpAnalysisReport(run: ErpRun) {
    if (!isErpExportReady(run)) {
      setNotice({
        tone: "error",
        message: "Report is available after a completed ERP run writes artifacts.",
      });
      return;
    }

    await runAction(`report-${run.run_id}`, async () => {
      const response = await postJson<AnalysisReportResponse>(
        `/erp-runs/${encodeURIComponent(run.run_id)}/analysis-report`,
        {},
      );
      setErpRuns((current) => ({
        status: "success",
        data: (current.data ?? []).map((item) =>
          item.run_id === response.erp_run.run_id ? response.erp_run : item,
        ),
        error: null,
      }));
      setNotice({
        tone: "ok",
        message: `Analysis report generated for ${run.run_id}.`,
      });
    });
  }

  function openErpAnalysisReport(run: ErpRun) {
    const reportUrl = run.output_metadata.analysis_report_url;
    if (typeof reportUrl !== "string" || !reportUrl) {
      setNotice({
        tone: "error",
        message: "Generate the analysis report before opening it.",
      });
      return;
    }
    window.open(`${API_BASE_URL}${reportUrl}`, "_blank", "noopener,noreferrer");
  }

  async function checkArtifactIntegrity(run: ErpRun) {
    if (!isErpExportReady(run)) {
      setNotice({
        tone: "error",
        message: "Artifact integrity check requires a completed run manifest.",
      });
      return;
    }

    setArtifactIntegrity((current) => ({
      ...current,
      [run.run_id]: { status: "loading", data: null, error: null },
    }));
    try {
      const response = await requestJson<ArtifactIntegrityResponse>(
        `/runs/${encodeURIComponent(run.run_id)}/artifact-integrity`,
      );
      setArtifactIntegrity((current) => ({
        ...current,
        [run.run_id]: {
          status: "success",
          data: response.integrity,
          error: null,
        },
      }));
      setNotice({
        tone: response.integrity.status === "ok" ? "ok" : "error",
        message: `Artifact integrity ${response.integrity.status}.`,
      });
    } catch (error: unknown) {
      setArtifactIntegrity((current) => ({
        ...current,
        [run.run_id]: {
          status: "error",
          data: null,
          error: getErrorMessage(error),
        },
      }));
      setNotice({ tone: "error", message: getErrorMessage(error) });
    }
  }

  async function cancelPreprocessingRun(runId: string) {
    await runAction(`cancel-${runId}`, async () => {
      const run = await requestJson<PreprocessingRun>(
        `/preprocessing-runs/${encodeURIComponent(runId)}/cancel`,
        { method: "POST" },
      );
      setPreprocessingRuns((current) => ({
        status: "success",
        data: (current.data ?? []).map((item) =>
          item.run_id === run.run_id ? run : item,
        ),
        error: null,
      }));
      setNotice({
        tone: run.status === "cancelled" ? "ok" : "neutral",
        message: `Preprocessing run ${run.run_id} ${run.status}.`,
      });
    });
  }

  async function runAction(action: string, callback: () => Promise<void>) {
    setBusyAction(action);
    setNotice(null);
    try {
      await callback();
    } catch (error: unknown) {
      setNotice({ tone: "error", message: getErrorMessage(error) });
    } finally {
      setBusyAction(null);
    }
  }

  async function refreshProjects() {
    const response = await fetchJson<ProjectsResponse>("/projects");
    setProjects({ status: "success", data: response.projects, error: null });
  }

  async function refreshExperiments(projectId: string) {
    const response = await fetchJson<ExperimentsResponse>(
      `/projects/${encodeURIComponent(projectId)}/experiments`,
    );
    setExperiments({ status: "success", data: response.experiments, error: null });
  }

  async function refreshDatasets() {
    const response = await fetchJson<DatasetsResponse>("/datasets");
    setDatasets({ status: "success", data: response.datasets, error: null });
  }

  async function refreshWorkflowTemplates(
    options: { silent?: boolean } = {},
  ): Promise<void> {
    if (!options.silent) {
      setWorkflowTemplates({ status: "loading", data: null, error: null });
    }
    try {
      const response = await fetchJson<WorkflowTemplatesResponse>(
        "/workflow-templates",
      );
      setWorkflowTemplates({
        status: "success",
        data: response.templates,
        error: null,
      });
    } catch (error: unknown) {
      setWorkflowTemplates({
        status: "error",
        data: null,
        error: getErrorMessage(error),
      });
    }
  }

  async function refreshBatches(options: { silent?: boolean } = {}): Promise<void> {
    if (!options.silent) {
      setBatchRuns({ status: "loading", data: null, error: null });
    }
    try {
      const response = await fetchJson<BatchRunsResponse>("/batches");
      setBatchRuns({
        status: "success",
        data: response.batches,
        error: null,
      });
      const selected =
        response.batches.find((batch) => batch.batch_id === selectedBatchId) ??
        response.batches[0] ??
        null;
      if (selected) {
        await refreshBatchRunOutputs(selected);
      }
    } catch (error: unknown) {
      setBatchRuns({
        status: "error",
        data: null,
        error: getErrorMessage(error),
      });
    }
  }

  async function refreshBatchDetail(
    batchId: string,
    options: { silent?: boolean } = {},
  ): Promise<void> {
    try {
      const batch = await fetchJson<BatchRunPlan>(
        `/batches/${encodeURIComponent(batchId)}`,
      );
      updateBatchInState(batch);
      await refreshBatchRunOutputs(batch);
    } catch (error: unknown) {
      if (!options.silent) {
        setNotice({ tone: "error", message: getErrorMessage(error) });
      }
    }
  }

  async function refreshBatchRunOutputs(batch: BatchRunPlan): Promise<void> {
    const runIds = batch.items
      .map((item) => item.run_ids.preprocessing)
      .filter((runId): runId is string => Boolean(runId));
    if (runIds.length === 0) {
      return;
    }
    const responses = await Promise.allSettled(
      runIds.map((runId) =>
        fetchJson<PreprocessingRun>(
          `/preprocessing-runs/${encodeURIComponent(runId)}`,
        ),
      ),
    );
    const nextRuns: Record<string, PreprocessingRun> = {};
    responses.forEach((response) => {
      if (response.status === "fulfilled") {
        nextRuns[response.value.run_id] = response.value;
      }
    });
    if (Object.keys(nextRuns).length === 0) {
      return;
    }
    setBatchPreprocessingRuns((current) => ({ ...current, ...nextRuns }));
  }

  async function loadDatasetContext(datasetId: string): Promise<DatasetContext> {
    const encodedDatasetId = encodeURIComponent(datasetId);
    const [
      dataset,
      eventLog,
      validation,
      preprocessingResponse,
      epochResponse,
      erpResponse,
      qcSummary,
    ] = await Promise.all([
      fetchJson<Dataset>(`/datasets/${encodedDatasetId}`),
      fetchOptionalJson<EventLogResponse>(`/datasets/${encodedDatasetId}/events`),
      fetchOptionalJson<ValidationReport>(
        `/datasets/${encodedDatasetId}/validation`,
      ),
      fetchJson<PreprocessingRunsResponse>(
        `/datasets/${encodedDatasetId}/preprocessing-runs`,
      ),
      fetchJson<EpochRunsResponse>(`/datasets/${encodedDatasetId}/epoch-runs`),
      fetchJson<ErpRunsResponse>(`/datasets/${encodedDatasetId}/erp-runs`),
      fetchOptionalJson<QcSummaryResponse>(`/datasets/${encodedDatasetId}/qc-summary`),
    ]);

    return {
      dataset,
      eventLog,
      validation,
      qcSummary,
      preprocessingRuns: preprocessingResponse.runs,
      epochRuns: epochResponse.runs,
      erpRuns: erpResponse.runs,
    };
  }

  async function refreshPreprocessingRuns(
    datasetId: string,
    options: { silent?: boolean } = {},
  ) {
    if (!options.silent) {
      setPreprocessingRuns({ status: "loading", data: null, error: null });
    }
    try {
      const response = await fetchJson<PreprocessingRunsResponse>(
        `/datasets/${encodeURIComponent(datasetId)}/preprocessing-runs`,
      );
      setPreprocessingRuns({
        status: "success",
        data: response.runs,
        error: null,
      });
      await refreshQcSummary(datasetId, { silent: true });
    } catch (error: unknown) {
      setPreprocessingRuns({
        status: "error",
        data: null,
        error: getErrorMessage(error),
      });
    }
  }

  async function refreshEpochRuns(
    datasetId: string,
    options: { silent?: boolean } = {},
  ) {
    if (!options.silent) {
      setEpochRuns({ status: "loading", data: null, error: null });
    }
    try {
      const response = await fetchJson<EpochRunsResponse>(
        `/datasets/${encodeURIComponent(datasetId)}/epoch-runs`,
      );
      setEpochRuns({
        status: "success",
        data: response.runs,
        error: null,
      });
      await refreshQcSummary(datasetId, { silent: true });
    } catch (error: unknown) {
      setEpochRuns({
        status: "error",
        data: null,
        error: getErrorMessage(error),
      });
    }
  }

  async function refreshErpRuns(
    datasetId: string,
    options: { silent?: boolean } = {},
  ) {
    if (!options.silent) {
      setErpRuns({ status: "loading", data: null, error: null });
    }
    try {
      const response = await fetchJson<ErpRunsResponse>(
        `/datasets/${encodeURIComponent(datasetId)}/erp-runs`,
      );
      setErpRuns({
        status: "success",
        data: response.runs,
        error: null,
      });
      await refreshQcSummary(datasetId, { silent: true });
    } catch (error: unknown) {
      setErpRuns({
        status: "error",
        data: null,
        error: getErrorMessage(error),
      });
    }
  }

  async function refreshQcSummary(
    datasetId: string,
    options: { silent?: boolean } = {},
  ) {
    if (!options.silent) {
      setQcSummary({ status: "loading", data: null, error: null });
    }
    try {
      const summary = await fetchOptionalJson<QcSummaryResponse>(
        `/datasets/${encodeURIComponent(datasetId)}/qc-summary`,
      );
      setQcSummary({ status: "success", data: summary, error: null });
    } catch (error: unknown) {
      setQcSummary({
        status: "error",
        data: null,
        error: getErrorMessage(error),
      });
    }
  }

  function updateDatasetInState(dataset: Dataset) {
    setDatasets((current) => {
      const data = current.data ?? [];
      const nextData = data.some((item) => item.dataset_id === dataset.dataset_id)
        ? data.map((item) =>
            item.dataset_id === dataset.dataset_id ? dataset : item,
          )
        : [dataset, ...data];
      return { status: "success", data: nextData, error: null };
    });
  }

  function updateBatchInState(batch: BatchRunPlan) {
    setBatchRuns((current) => {
      const data = current.data ?? [];
      const nextData = data.some((item) => item.batch_id === batch.batch_id)
        ? data.map((item) => (item.batch_id === batch.batch_id ? batch : item))
        : [batch, ...data];
      return { status: "success", data: nextData, error: null };
    });
  }

  const activeDatasetCount = datasets.data?.length ?? 0;

  return (
    <main className="shell">
      <section className="workspace" aria-labelledby="workspace-title">
        <header className="workspace-header">
          <div>
            <p className="eyebrow">NeuroWeave</p>
            <h1 id="workspace-title">EEG research workbench</h1>
            <p className="subtle">
              {activeDataset
                ? `${activeDataset.dataset_id} / ${activeDataset.status}`
                : "No active dataset"}
            </p>
          </div>
          <div className="workspace-actions">
            <div className="theme-toggle" aria-label="Theme">
              <button
                aria-pressed={theme === "dark"}
                className="theme-toggle-button"
                onClick={() => setTheme("dark")}
                type="button"
              >
                Dark
              </button>
              <button
                aria-pressed={theme === "light"}
                className="theme-toggle-button"
                onClick={() => setTheme("light")}
                type="button"
              >
                Light
              </button>
            </div>
            <button className="primary-button" type="button" onClick={refreshWorkspace}>
              Refresh
            </button>
          </div>
        </header>

        <div className="status-strip">
          <StatusTile
            label="API"
            value={getHealthLabel(health)}
            tone={health.status === "success" ? "ok" : health.status}
          />
          <StatusTile
            label="Projects"
            value={getProjectCountLabel(projects)}
            tone={projects.status === "success" ? "ok" : projects.status}
          />
          <StatusTile
            label="Datasets"
            value={`${activeDatasetCount} registered`}
            tone={datasets.status === "success" ? "ok" : datasets.status}
          />
          <StatusTile label="API URL" value={API_BASE_URL} tone="neutral" />
        </div>

        {notice ? (
          <div className={`notice notice-${notice.tone}`}>{notice.message}</div>
        ) : null}

        <nav className="workspace-mode-tabs" aria-label="Workspace mode">
          <button
            aria-pressed={workspaceMode === "setup"}
            className="workspace-mode-button"
            onClick={() => chooseWorkspaceMode("setup")}
            type="button"
          >
            Setup
          </button>
          <button
            aria-pressed={workspaceMode === "analysis"}
            className="workspace-mode-button"
            onClick={() => chooseWorkspaceMode("analysis")}
            type="button"
          >
            Analysis
          </button>
          {workspaceMode === "analysis" ? (
            <span className="workspace-mode-context">Study Setup</span>
          ) : null}
        </nav>

        {workspaceMode === "setup" ? (
          <section
            className="setup-workspace"
            aria-label="Study and dataset setup"
            data-testid="setup-workspace"
          >
            <div className="setup-column">
              <section className="panel setup-panel" aria-labelledby="setup-title">
                <div className="panel-header">
                  <h2 id="setup-title">Study Setup</h2>
                </div>
                <StudySetup
                  busyAction={busyAction}
                  experimentForm={experimentForm}
                  experiments={experiments}
                  onCreateExperiment={createExperiment}
                  onCreateProject={createProject}
                  onExperimentFormChange={setExperimentForm}
                  onProjectFormChange={setProjectForm}
                  onSelectExperiment={setSelectedExperimentId}
                  onSelectProject={setSelectedProjectId}
                  projectForm={projectForm}
                  projects={projects}
                  selectedExperimentId={selectedExperimentId}
                  selectedProjectId={selectedProjectId}
                />
              </section>

              <section className="panel dataset-panel" aria-labelledby="datasets-title">
                <div className="panel-header compact-header">
                  <div>
                    <h2 id="datasets-title">Dataset Queue</h2>
                    <p className="subtle">
                      {selectedProject
                        ? selectedExperiment
                          ? `${selectedProject.name} / ${selectedExperiment.name}`
                          : selectedProject.name
                        : "Select study context"}
                    </p>
                  </div>
                </div>
                <DatasetSection
                  activeDatasetId={activeDatasetId}
                  busyAction={busyAction}
                  datasetForm={datasetForm}
                  datasets={datasets}
                  onCreateDataset={createDataset}
                  onDatasetFormChange={setDatasetForm}
                  onSelectDataset={(datasetId) => {
                    setActiveDatasetId(datasetId);
                    setEventPreview(null);
                    setEventLog(null);
                    setUploadedEegFilename(null);
                    setUploadedEventFilename(null);
                    setValidation(null);
                    setEpochConfig(DEFAULT_EPOCH_CONFIG);
                  }}
                  selectedExperimentId={selectedExperimentId}
                  selectedProjectId={selectedProjectId}
                />
              </section>
            </div>

            <div className="setup-column">
              <section
                className="panel active-context-panel"
                aria-labelledby="setup-active-context-title"
              >
                <div className="panel-header">
                  <div>
                    <h2 id="setup-active-context-title">Active Dataset</h2>
                    <p className="subtle">
                      {activeDataset
                        ? `${activeDataset.dataset_id} / ${activeDataset.status}`
                        : "Create or select a dataset"}
                    </p>
                  </div>
                  {activeDataset ? (
                    <button
                      className="primary-button"
                      onClick={() => chooseWorkspaceMode("analysis")}
                      type="button"
                    >
                      Continue Analysis
                    </button>
                  ) : null}
                </div>
                <ActiveDatasetSummary
                  activeDataset={activeDataset}
                  eventLog={eventLog}
                  selectedExperiment={selectedExperiment}
                  selectedProject={selectedProject}
                  validation={validation}
                />
              </section>

              <section className="panel" aria-labelledby="sample-list-title">
                <div className="panel-header">
                  <h2 id="sample-list-title">Sample Metadata</h2>
                  {selectedSample ? (
                    <span className="file-pill">{selectedSample.filename}</span>
                  ) : null}
                </div>
                <div className="sample-grid">
                  <SampleList
                    onSelect={setSelectedSampleId}
                    samples={samples}
                    selectedSampleId={selectedSampleId}
                  />
                  <MetadataView metadata={metadata} selectedSample={selectedSample} />
                </div>
              </section>
            </div>
          </section>
        ) : (
          <section
            className="analysis-workspace"
            aria-label="Analysis workspace"
            data-testid="analysis-workspace"
          >
            <section
              className="panel active-context-panel"
              aria-labelledby="active-context-title"
            >
              <div className="panel-header">
                <div>
                  <h2 id="active-context-title">Active Dataset</h2>
                  <p className="subtle">
                    {activeDataset
                      ? `${activeDataset.dataset_id} / ${activeDataset.status}`
                      : "Create or select a dataset"}
                  </p>
                </div>
                {activeDataset ? (
                  <span className={`status-badge badge-${activeDataset.status}`}>
                    {activeDataset.status}
                  </span>
                ) : (
                  <button
                    className="secondary-button"
                    onClick={() => chooseWorkspaceMode("setup")}
                    type="button"
                  >
                    Open Setup
                  </button>
                )}
              </div>
              <ActiveDatasetSummary
                activeDataset={activeDataset}
                eventLog={eventLog}
                selectedExperiment={selectedExperiment}
                selectedProject={selectedProject}
                validation={validation}
              />
            </section>

            <section className="workflow-stack">
              <section className="panel" aria-labelledby="workflow-template-title">
                <div className="panel-header">
                  <div>
                    <h2 id="workflow-template-title">Workflow Templates</h2>
                    <p className="subtle">
                      {activeDataset
                        ? "Save completed runs and preview reusable config on this dataset"
                        : "Create or select a dataset"}
                    </p>
                  </div>
                </div>
                <WorkflowTemplatePanel
                  activeDataset={activeDataset}
                  busyAction={busyAction}
                  lastPreview={lastWorkflowTemplatePreview}
                  onApplyTemplate={applySelectedWorkflowTemplate}
                  onSelectTemplate={(templateId) => {
                    setSelectedWorkflowTemplateId(templateId);
                    setLastWorkflowTemplatePreview(null);
                  }}
                  selectedTemplateId={selectedWorkflowTemplateId}
                  templates={workflowTemplates}
                />
              </section>

              <section className="panel" aria-labelledby="batch-runs-title">
                <div className="panel-header">
                  <div>
                    <h2 id="batch-runs-title">Batch Runs</h2>
                    <p className="subtle">
                      {activeDataset
                        ? "Per-subject preprocessing progress and outputs"
                        : "Create or select a dataset"}
                    </p>
                  </div>
                </div>
                <BatchRunsPanel
                  activeDataset={activeDataset}
                  batchEligibleDatasets={batchEligibleDatasets}
                  batchFilter={batchItemFilter}
                  batchRuns={batchRuns}
                  busyAction={busyAction}
                  onCancelBatch={cancelBatchRun}
                  onCreateBatch={beginBatchRun}
                  onFilterChange={setBatchItemFilter}
                  onRefreshBatches={() => refreshBatches({ silent: false })}
                  onRetryItem={retryBatchItem}
                  onSelectBatch={setSelectedBatchId}
                  datasetsById={datasetsById}
                  preprocessingRunsById={batchPreprocessingRuns}
                  selectedBatch={selectedBatch}
                  selectedBatchId={selectedBatchId}
                  selectedTemplateId={selectedWorkflowTemplateId}
                />
              </section>

              <section className="panel" aria-labelledby="intake-title">
                <div className="panel-header">
                  <div>
                    <h2 id="intake-title">Ingestion And Preprocessing</h2>
                    <p className="subtle">
                      {activeDataset
                        ? "Files, event mapping, validation, and preprocessing runs"
                        : "Create or select a dataset"}
                    </p>
                  </div>
                </div>
                <IntakeSection
                  activeDataset={activeDataset}
                  busyAction={busyAction}
                  eegFile={eegFile}
                  eventFile={eventFile}
                  eventLog={eventLog}
                  eventPreview={eventPreview}
                  eventMappingPreset={eventMappingPreset}
                  eventRowFilter={eventRowFilter}
                  mapping={mapping}
                  onBeginPreprocessing={beginPreprocessingHandoff}
                  onEegFileChange={chooseEegFile}
                  onEventFileChange={chooseEventFile}
                  onEventMappingPresetChange={(preset) => {
                    setEventMappingPreset(preset);
                    if (preset && eventPreview) {
                      setMapping(mappingFromPreset(preset, eventPreview.columns));
                    }
                  }}
                  onMappingChange={setMapping}
                  onRowFilterChange={setEventRowFilter}
                  onPreprocessingConfigChange={setPreprocessingConfig}
                  onCancelPreprocessingRun={cancelPreprocessingRun}
                  onSaveTemplateFromRun={(run) =>
                    saveWorkflowTemplateFromRun("preprocessing", run)
                  }
                  onSubmitEventMapping={submitEventMapping}
                  onUploadEeg={uploadEegFile}
                  onUploadEvent={uploadEventFile}
                  onValidate={validateDataset}
                  metadata={metadata}
                  preprocessingConfig={preprocessingConfig}
                  preprocessingRuns={preprocessingRuns}
                  uploadedEegFilename={uploadedEegFilename}
                  uploadedEventFilename={uploadedEventFilename}
                  validation={validation}
                />
              </section>

              <section className="panel" aria-labelledby="epoch-title">
                <div className="panel-header">
                  <div>
                    <h2 id="epoch-title">Epoch Controls</h2>
                    <p className="subtle">
                      {activeDataset
                        ? "Create epochs from completed preprocessing output"
                        : "Create or select a dataset"}
                    </p>
                  </div>
                </div>
                <EpochSection
                  activeDataset={activeDataset}
                  busyAction={busyAction}
                  completedPreprocessingRuns={completedPreprocessingRuns}
                  epochConfig={epochConfig}
                  epochRuns={epochRuns}
                  onEpochConfigChange={setEpochConfig}
                  onSaveTemplateFromRun={(run) =>
                    saveWorkflowTemplateFromRun("epoch", run)
                  }
                  onStartEpochRun={beginEpochRun}
                />
              </section>

              <section className="panel" aria-labelledby="erp-title">
                <div className="panel-header">
                  <div>
                    <h2 id="erp-title">ERP Preview</h2>
                    <p className="subtle">
                      {activeDataset
                        ? "Generate condition averages and plot previews"
                        : "Create or select a dataset"}
                    </p>
                  </div>
                </div>
                <ErpSection
                  activeDataset={activeDataset}
                  busyAction={busyAction}
                  comparisonConfig={comparisonConfig}
                  completedEpochRuns={completedEpochRuns}
                  completedErpRuns={completedErpRuns}
                  erpConfig={erpConfig}
                  erpRuns={erpRuns}
                  artifactIntegrity={artifactIntegrity}
                  onComparisonConfigChange={setComparisonConfig}
                  onDownloadErpExportBundle={downloadErpExportBundle}
                  onErpConfigChange={setErpConfig}
                  onGenerateErpAnalysisReport={generateErpAnalysisReport}
                  onCheckArtifactIntegrity={checkArtifactIntegrity}
                  onOpenErpAnalysisReport={openErpAnalysisReport}
                  onSaveTemplateFromRun={(run) =>
                    saveWorkflowTemplateFromRun("erp", run)
                  }
                  onStartComparisonSummary={beginComparisonSummary}
                  onStartErpRun={beginErpRun}
                />
              </section>

              <section className="panel" aria-labelledby="qc-title">
                <div className="panel-header">
                  <div>
                    <h2 id="qc-title">QC Dashboard</h2>
                    <p className="subtle">
                      {activeDataset
                        ? "Summaries from manifest-backed run artifacts"
                        : "Create or select a dataset"}
                    </p>
                  </div>
                </div>
                <QcDashboard
                  onPreprocessingConfigChange={setPreprocessingConfig}
                  preprocessingConfig={preprocessingConfig}
                  qcSummary={qcSummary}
                />
              </section>
            </section>
          </section>
        )}
      </section>
    </main>
  );
}

function WorkflowTemplatePanel({
  activeDataset,
  busyAction,
  lastPreview,
  onApplyTemplate,
  onSelectTemplate,
  selectedTemplateId,
  templates,
}: {
  activeDataset: Dataset | null;
  busyAction: string | null;
  lastPreview: WorkflowTemplateApplyPreview | null;
  onApplyTemplate: () => void;
  onSelectTemplate: (templateId: string) => void;
  selectedTemplateId: string;
  templates: LoadState<WorkflowTemplate[]>;
}) {
  if (templates.status === "loading" || templates.status === "idle") {
    return <p className="muted">Loading workflow templates...</p>;
  }

  if (templates.status === "error") {
    return <p className="error-text">{templates.error}</p>;
  }

  const templateData = templates.data ?? [];
  const selectedTemplate =
    templateData.find((template) => template.template_id === selectedTemplateId) ??
    null;
  const excludedFields =
    lastPreview?.template_id === selectedTemplateId
      ? lastPreview.excluded_fields
      : selectedTemplate?.field_policy.excluded_fields ?? [];
  const reviewRequiredFields =
    lastPreview?.template_id === selectedTemplateId
      ? lastPreview.review_required_fields
      : selectedTemplate?.field_policy.review_required_fields ?? [];
  const statusLabel = lastPreview
    ? `preview ${lastPreview.status}`
    : selectedTemplate?.validation.stale
      ? "stale"
      : selectedTemplate?.validation.valid
        ? "valid"
        : "not validated";

  return (
    <div className="template-panel" data-testid="workflow-template-panel">
      <div className="template-controls">
        <label className="wide-field">
          <span>Template</span>
          <select
            data-testid="workflow-template-select"
            disabled={templateData.length === 0}
            onChange={(event) => onSelectTemplate(event.target.value)}
            value={selectedTemplateId}
          >
            <option value="">Select workflow template</option>
            {templateData.map((template) => (
              <option key={template.template_id} value={template.template_id}>
                {template.name}
              </option>
            ))}
          </select>
        </label>
        <button
          className="primary-button"
          data-testid="apply-workflow-template-button"
          disabled={
            !activeDataset ||
            !selectedTemplate ||
            busyAction === "template-apply"
          }
          onClick={onApplyTemplate}
          type="button"
        >
          {busyAction === "template-apply" ? "Previewing..." : "Apply Preview"}
        </button>
      </div>

      {templateData.length === 0 ? (
        <p className="muted">
          Save a template from a completed preprocessing, epoch, or ERP run.
        </p>
      ) : null}

      {selectedTemplate ? (
        <div className="template-summary">
          <div className="run-meta">
            <span>{statusLabel}</span>
            <span>{formatTemplateWorkflowSummary(selectedTemplate.workflow)}</span>
            <span>{selectedTemplate.template_id}</span>
          </div>
          {selectedTemplate.validation.stale_reasons.length > 0 ? (
            <p className="run-warning">
              {selectedTemplate.validation.stale_reasons.join(" ")}
            </p>
          ) : null}
          {lastPreview?.template_id === selectedTemplateId ? (
            <TemplatePreviewMessages preview={lastPreview} />
          ) : null}
        </div>
      ) : null}

      <div className="template-policy-grid">
        <TemplatePolicyList
          emptyText="No excluded subject-specific fields."
          entries={excludedFields}
          title="Excluded Subject-Specific Fields"
        />
        <TemplatePolicyList
          emptyText="No fields need review."
          entries={reviewRequiredFields}
          title="Review-Needed Fields"
        />
      </div>
    </div>
  );
}

function TemplatePreviewMessages({
  preview,
}: {
  preview: WorkflowTemplateApplyPreview;
}) {
  if (preview.errors.length === 0 && preview.warnings.length === 0) {
    return <p className="muted">Preview returned no errors or warnings.</p>;
  }

  return (
    <div className="template-message-list">
      {preview.errors.map((message) => (
        <p className="error-text" key={`error-${message}`}>
          {message}
        </p>
      ))}
      {preview.warnings.map((message) => (
        <p className="muted" key={`warning-${message}`}>
          {message}
        </p>
      ))}
    </div>
  );
}

function TemplatePolicyList({
  emptyText,
  entries,
  title,
}: {
  emptyText: string;
  entries: WorkflowTemplateFieldPolicyEntry[];
  title: string;
}) {
  return (
    <div className="template-policy-list">
      <h3>{title}</h3>
      {entries.length === 0 ? <p className="muted">{emptyText}</p> : null}
      {entries.map((entry) => (
        <div className="template-policy-entry" key={`${entry.path}-${entry.reason}`}>
          <strong>{entry.path}</strong>
          <span>
            {entry.reason}
            {entry.default_action ? ` / ${entry.default_action}` : ""}
          </span>
          {entry.source_value_summary ? <small>{entry.source_value_summary}</small> : null}
        </div>
      ))}
    </div>
  );
}

function BatchRunsPanel({
  activeDataset,
  batchEligibleDatasets,
  batchFilter,
  batchRuns,
  busyAction,
  onCancelBatch,
  onCreateBatch,
  onFilterChange,
  onRefreshBatches,
  onRetryItem,
  onSelectBatch,
  datasetsById,
  preprocessingRunsById,
  selectedBatch,
  selectedBatchId,
  selectedTemplateId,
}: {
  activeDataset: Dataset | null;
  batchEligibleDatasets: Dataset[];
  batchFilter: BatchItemFilter;
  batchRuns: LoadState<BatchRunPlan[]>;
  busyAction: string | null;
  onCancelBatch: (batchId: string) => void;
  onCreateBatch: () => void;
  onFilterChange: (filter: BatchItemFilter) => void;
  onRefreshBatches: () => void;
  onRetryItem: (batchId: string, itemId: string) => void;
  onSelectBatch: (batchId: string) => void;
  datasetsById: Record<string, Dataset>;
  preprocessingRunsById: Record<string, PreprocessingRun>;
  selectedBatch: BatchRunPlan | null;
  selectedBatchId: string;
  selectedTemplateId: string;
}) {
  if (batchRuns.status === "loading" || batchRuns.status === "idle") {
    return <p className="muted">Loading batch runs...</p>;
  }

  if (batchRuns.status === "error") {
    return <p className="error-text">{batchRuns.error}</p>;
  }

  const batches = batchRuns.data ?? [];
  const selectedItems = selectedBatch?.items ?? [];
  const filteredItems = selectedItems.filter((item) =>
    batchItemMatchesFilter(item, batchFilter),
  );
  const batchSummary = selectedBatch ? summarizeBatchItems(selectedBatch.items) : null;
  const canCreateBatch =
    Boolean(activeDataset) &&
    Boolean(selectedTemplateId) &&
    batchEligibleDatasets.length > 0;

  return (
    <div className="batch-panel" data-testid="batch-runs-panel">
      <div className="batch-controls">
        <label className="wide-field">
          <span>Batch</span>
          <select
            data-testid="batch-select"
            disabled={batches.length === 0}
            onChange={(event) => onSelectBatch(event.target.value)}
            value={selectedBatchId}
          >
            <option value="">Select batch</option>
            {batches.map((batch) => (
              <option key={batch.batch_id} value={batch.batch_id}>
                {batch.batch_id} / {batch.status}
              </option>
            ))}
          </select>
        </label>
        <button
          className="primary-button"
          data-testid="start-batch-button"
          disabled={!canCreateBatch || busyAction === "batch-create"}
          onClick={onCreateBatch}
          type="button"
        >
          {busyAction === "batch-create" ? "Queueing..." : "Start Batch"}
        </button>
        <button className="secondary-button" onClick={onRefreshBatches} type="button">
          Refresh
        </button>
      </div>

      <div className="run-meta batch-summary-meta">
        <span>{batchEligibleDatasets.length} dataset(s)</span>
        <span>{selectedBatch?.status ?? "no batch"}</span>
        {batchSummary ? <span>{batchSummary}</span> : null}
        {selectedBatch ? <span>{selectedBatch.template_snapshot.template_name}</span> : null}
      </div>

      <div className="batch-filter-tabs" aria-label="Batch item status filter">
        {(["all", "pending", "completed", "failed"] as BatchItemFilter[]).map(
          (filter) => (
            <button
              aria-pressed={batchFilter === filter}
              className="workspace-mode-button"
              key={filter}
              onClick={() => onFilterChange(filter)}
              type="button"
            >
              {filter}
            </button>
          ),
        )}
      </div>

      {selectedBatch ? (
        <>
          {isActiveBatchStatus(selectedBatch.status) ? (
            <p className="muted">Polling batch detail until execution settles.</p>
          ) : null}
          {isActiveBatchStatus(selectedBatch.status) ? (
            <button
              className="secondary-button compact-button"
              disabled={busyAction === `batch-cancel-${selectedBatch.batch_id}`}
              onClick={() => onCancelBatch(selectedBatch.batch_id)}
              type="button"
            >
              {busyAction === `batch-cancel-${selectedBatch.batch_id}`
                ? "Cancelling..."
                : "Cancel Batch"}
            </button>
          ) : null}
          <BatchSubjectTable
            datasetsById={datasetsById}
            filter={batchFilter}
            items={filteredItems}
            batchId={selectedBatch.batch_id}
            busyAction={busyAction}
            onRetryItem={onRetryItem}
            preprocessingRunsById={preprocessingRunsById}
          />
        </>
      ) : (
        <p className="muted">
          No batch runs yet. Select a template and start a batch for valid datasets.
        </p>
      )}
    </div>
  );
}

function BatchSubjectTable({
  batchId,
  busyAction,
  datasetsById,
  filter,
  items,
  onRetryItem,
  preprocessingRunsById,
}: {
  batchId: string;
  busyAction: string | null;
  datasetsById: Record<string, Dataset>;
  filter: BatchItemFilter;
  items: BatchSubjectRunPlan[];
  onRetryItem: (batchId: string, itemId: string) => void;
  preprocessingRunsById: Record<string, PreprocessingRun>;
}) {
  if (items.length === 0) {
    return <p className="muted">No {filter} subject items.</p>;
  }

  return (
    <div className="batch-table-wrap" data-testid="batch-run-table">
      <table className="batch-run-table">
        <thead>
          <tr>
            <th>Dataset / Subject</th>
            <th>Status</th>
            <th>Current Step</th>
            <th>Output</th>
            <th>Warnings</th>
            <th>Errors</th>
            <th>Retry</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const preprocessingRunId = item.run_ids.preprocessing;
            const preprocessingRun = preprocessingRunId
              ? preprocessingRunsById[preprocessingRunId]
              : null;
            const dataset = datasetsById[item.dataset_id] ?? null;
            return (
              <tr key={item.item_id}>
                <td>
                  <strong>{item.dataset_id}</strong>
                  <small>{dataset?.participant_id ?? item.item_id}</small>
                </td>
                <td>
                  <span className={`status-badge badge-${item.status}`}>
                    {item.status}
                  </span>
                </td>
                <td>{formatBatchCurrentStep(item, preprocessingRun)}</td>
                <td>
                  <BatchOutputCell item={item} run={preprocessingRun} />
                </td>
                <td>{formatBatchMessages(item.warnings, preprocessingRun?.warnings)}</td>
                <td>{formatBatchMessages(item.errors, preprocessingRun?.errors)}</td>
                <td>
                  <BatchRetryCell
                    batchId={batchId}
                    busyAction={busyAction}
                    item={item}
                    onRetryItem={onRetryItem}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function BatchOutputCell({
  item,
  run,
}: {
  item: BatchSubjectRunPlan;
  run: PreprocessingRun | null;
}) {
  const runId = item.run_ids.preprocessing;
  const outputPath = run?.output_path;
  if (!runId && !outputPath) {
    return <span className="muted">No output yet</span>;
  }
  return (
    <span className="batch-output">
      <strong>{runId ?? "pending run"}</strong>
      <small>{outputPath ?? "Output pending"}</small>
    </span>
  );
}

function BatchRetryCell({
  batchId,
  busyAction,
  item,
  onRetryItem,
}: {
  batchId: string;
  busyAction: string | null;
  item: BatchSubjectRunPlan;
  onRetryItem: (batchId: string, itemId: string) => void;
}) {
  const previousRunId = item.previous_run_ids.preprocessing;
  const isRetrying = busyAction === `batch-retry-${item.item_id}`;
  return (
    <div className="batch-retry-cell">
      <span>Attempt {item.attempt}</span>
      {previousRunId ? <small>Previous run: {previousRunId}</small> : null}
      {item.previous_error ? <small>Previous error: {item.previous_error}</small> : null}
      {item.status === "failed" ? (
        <button
          className="secondary-button compact-button"
          data-testid={`retry-batch-item-${item.item_id}`}
          disabled={isRetrying}
          onClick={() => onRetryItem(batchId, item.item_id)}
          type="button"
        >
          {isRetrying ? "Retrying..." : "Retry"}
        </button>
      ) : null}
    </div>
  );
}

function ActiveDatasetSummary({
  activeDataset,
  eventLog,
  selectedExperiment,
  selectedProject,
  validation,
}: {
  activeDataset: Dataset | null;
  eventLog: EventLogResponse | null;
  selectedExperiment: Experiment | null;
  selectedProject: Project | null;
  validation: ValidationReport | null;
}) {
  const stageItems = [
    {
      label: "Study",
      state: selectedProject && selectedExperiment ? "ready" : "waiting",
      value: selectedExperiment?.name ?? selectedProject?.name ?? "No selection",
    },
    {
      label: "Dataset",
      state: activeDataset ? "ready" : "waiting",
      value: activeDataset?.dataset_id ?? "No dataset",
    },
    {
      label: "Files",
      state:
        activeDataset?.status === "needs_mapping" ||
        activeDataset?.status === "valid" ||
        activeDataset?.status === "invalid"
          ? "ready"
          : "waiting",
      value: activeDataset ? activeDataset.status : "Pending",
    },
    {
      label: "Events",
      state: eventLog ? "ready" : "waiting",
      value: eventLog ? `${eventLog.events.length} normalized` : "Unmapped",
    },
    {
      label: "Validation",
      state:
        validation?.valid || activeDataset?.status === "valid" ? "ready" : "waiting",
      value:
        validation?.valid || activeDataset?.status === "valid"
          ? "Ready"
          : validation
            ? `${validation.errors.length} errors`
            : "Not run",
    },
  ];

  return (
    <div className="active-context-grid">
      <dl className="context-table">
        <div>
          <dt>Project</dt>
          <dd>{selectedProject?.name ?? "Unselected"}</dd>
        </div>
        <div>
          <dt>Experiment</dt>
          <dd>{selectedExperiment?.name ?? "Unselected"}</dd>
        </div>
        <div>
          <dt>Participant</dt>
          <dd>{activeDataset?.metadata.participant_label ?? "None"}</dd>
        </div>
        <div>
          <dt>Session</dt>
          <dd>{activeDataset?.metadata.session_label ?? "None"}</dd>
        </div>
      </dl>
      <div className="stage-rail" aria-label="Dataset readiness">
        {stageItems.map((item, index) => (
          <div
            className="stage-item"
            data-state={item.state}
            key={item.label}
          >
            <span>{String(index + 1).padStart(2, "0")}</span>
            <strong>{item.label}</strong>
            <small data-testid={`stage-${item.label.toLowerCase()}-value`}>
              {item.value}
            </small>
          </div>
        ))}
      </div>
    </div>
  );
}

function StudySetup({
  busyAction,
  experimentForm,
  experiments,
  onCreateExperiment,
  onCreateProject,
  onExperimentFormChange,
  onProjectFormChange,
  onSelectExperiment,
  onSelectProject,
  projectForm,
  projects,
  selectedExperimentId,
  selectedProjectId,
}: {
  busyAction: string | null;
  experimentForm: { name: string; task_name: string };
  experiments: LoadState<Experiment[]>;
  onCreateExperiment: (event: React.FormEvent<HTMLFormElement>) => void;
  onCreateProject: (event: React.FormEvent<HTMLFormElement>) => void;
  onExperimentFormChange: (form: { name: string; task_name: string }) => void;
  onProjectFormChange: (form: { name: string; description: string }) => void;
  onSelectExperiment: (experimentId: string) => void;
  onSelectProject: (projectId: string) => void;
  projectForm: { name: string; description: string };
  projects: LoadState<Project[]>;
  selectedExperimentId: string;
  selectedProjectId: string;
}) {
  return (
    <div className="setup-stack">
      <form className="form-stack" onSubmit={onCreateProject}>
        <h3>Project</h3>
        <label>
          <span>Name</span>
          <input
            data-testid="project-name-input"
            onChange={(event) =>
              onProjectFormChange({ ...projectForm, name: event.target.value })
            }
            placeholder="Memory EEG"
            type="text"
            value={projectForm.name}
          />
        </label>
        <label>
          <span>Description</span>
          <textarea
            onChange={(event) =>
              onProjectFormChange({
                ...projectForm,
                description: event.target.value,
              })
            }
            placeholder="Optional"
            rows={2}
            value={projectForm.description}
          />
        </label>
        <button
          className="secondary-button"
          data-testid="create-project-button"
          disabled={busyAction === "project"}
          type="submit"
        >
          Create Project
        </button>
      </form>

      <label>
        <span>Selected Project</span>
        <select
          data-testid="selected-project-select"
          onChange={(event) => onSelectProject(event.target.value)}
          value={selectedProjectId}
        >
          <option value="">Select project</option>
          {(projects.data ?? []).map((project) => (
            <option key={project.project_id} value={project.project_id}>
              {project.name}
            </option>
          ))}
        </select>
      </label>
      <LoadMessage state={projects} empty="No projects yet." />

      <form className="form-stack divided" onSubmit={onCreateExperiment}>
        <h3>Experiment</h3>
        <label>
          <span>Name</span>
          <input
            data-testid="experiment-name-input"
            onChange={(event) =>
              onExperimentFormChange({
                ...experimentForm,
                name: event.target.value,
              })
            }
            placeholder="Oddball task"
            type="text"
            value={experimentForm.name}
          />
        </label>
        <label>
          <span>Task Name</span>
          <input
            onChange={(event) =>
              onExperimentFormChange({
                ...experimentForm,
                task_name: event.target.value,
              })
            }
            placeholder="Optional"
            type="text"
            value={experimentForm.task_name}
          />
        </label>
        <button
          className="secondary-button"
          data-testid="create-experiment-button"
          disabled={busyAction === "experiment" || !selectedProjectId}
          type="submit"
        >
          Create Experiment
        </button>
      </form>

      <label>
        <span>Selected Experiment</span>
        <select
          data-testid="selected-experiment-select"
          disabled={!selectedProjectId}
          onChange={(event) => onSelectExperiment(event.target.value)}
          value={selectedExperimentId}
        >
          <option value="">Select experiment</option>
          {(experiments.data ?? []).map((experiment) => (
            <option key={experiment.experiment_id} value={experiment.experiment_id}>
              {experiment.name}
            </option>
          ))}
        </select>
      </label>
      <LoadMessage state={experiments} empty="No experiments for this project." />
    </div>
  );
}

function DatasetSection({
  activeDatasetId,
  busyAction,
  datasetForm,
  datasets,
  onCreateDataset,
  onDatasetFormChange,
  onSelectDataset,
  selectedExperimentId,
  selectedProjectId,
}: {
  activeDatasetId: string;
  busyAction: string | null;
  datasetForm: {
    participant_label: string;
    participant_group: string;
    session_label: string;
  };
  datasets: LoadState<Dataset[]>;
  onCreateDataset: (event: React.FormEvent<HTMLFormElement>) => void;
  onDatasetFormChange: (form: {
    participant_label: string;
    participant_group: string;
    session_label: string;
  }) => void;
  onSelectDataset: (datasetId: string) => void;
  selectedExperimentId: string;
  selectedProjectId: string;
}) {
  const disabled = !selectedProjectId || !selectedExperimentId;
  const datasetData = datasets.data ?? [];

  return (
    <div className="dataset-layout">
      <form className="dataset-form" onSubmit={onCreateDataset}>
        <label>
          <span>Participant</span>
          <input
            data-testid="dataset-participant-input"
            disabled={disabled}
            onChange={(event) =>
              onDatasetFormChange({
                ...datasetForm,
                participant_label: event.target.value,
              })
            }
            placeholder="sub-001"
            type="text"
            value={datasetForm.participant_label}
          />
        </label>
        <label>
          <span>Group</span>
          <input
            data-testid="dataset-session-input"
            disabled={disabled}
            onChange={(event) =>
              onDatasetFormChange({
                ...datasetForm,
                participant_group: event.target.value,
              })
            }
            placeholder="Optional"
            type="text"
            value={datasetForm.participant_group}
          />
        </label>
        <label>
          <span>Session</span>
          <input
            disabled={disabled}
            onChange={(event) =>
              onDatasetFormChange({
                ...datasetForm,
                session_label: event.target.value,
              })
            }
            placeholder="ses-001"
            type="text"
            value={datasetForm.session_label}
          />
        </label>
        <button
          className="primary-button"
          data-testid="create-dataset-button"
          disabled={disabled || busyAction === "dataset"}
          type="submit"
        >
          Create Dataset
        </button>
      </form>

      <div className="dataset-list" aria-live="polite">
        {datasets.status === "loading" || datasets.status === "idle" ? (
          <p className="muted">Loading datasets...</p>
        ) : null}
        {datasets.status === "error" ? (
          <p className="error-text">{datasets.error}</p>
        ) : null}
        {datasets.status === "success" && datasetData.length === 0 ? (
          <p className="muted">No registered datasets yet.</p>
        ) : null}
        {datasetData.map((dataset) => (
          <button
            className="dataset-row"
            data-active={dataset.dataset_id === activeDatasetId}
            data-testid={`dataset-row-${dataset.dataset_id}`}
            key={dataset.dataset_id}
            onClick={() => onSelectDataset(dataset.dataset_id)}
            type="button"
          >
            <span>
              <strong>{dataset.metadata.participant_label ?? dataset.dataset_id}</strong>
              <small>
                {dataset.metadata.session_label ?? dataset.session_id} /{" "}
                {dataset.dataset_id}
              </small>
            </span>
            <em>{dataset.status}</em>
          </button>
        ))}
      </div>
    </div>
  );
}

function IntakeSection({
  activeDataset,
  busyAction,
  eegFile,
  eventFile,
  eventLog,
  eventMappingPreset,
  eventPreview,
  eventRowFilter,
  mapping,
  onBeginPreprocessing,
  onEegFileChange,
  onEventFileChange,
  onEventMappingPresetChange,
  onMappingChange,
  onRowFilterChange,
  onPreprocessingConfigChange,
  onCancelPreprocessingRun,
  onSaveTemplateFromRun,
  onSubmitEventMapping,
  onUploadEeg,
  onUploadEvent,
  onValidate,
  metadata,
  preprocessingConfig,
  preprocessingRuns,
  uploadedEegFilename,
  uploadedEventFilename,
  validation,
}: {
  activeDataset: Dataset | null;
  busyAction: string | null;
  eegFile: File | null;
  eventFile: File | null;
  eventLog: EventLogResponse | null;
  eventMappingPreset: EventMappingPreset;
  eventPreview: EventPreview | null;
  eventRowFilter: EventRowFilterForm;
  mapping: Record<MappingKey, string>;
  onBeginPreprocessing: () => void;
  onEegFileChange: (file: File | null) => void;
  onEventFileChange: (file: File | null) => void;
  onEventMappingPresetChange: (preset: EventMappingPreset) => void;
  onMappingChange: (mapping: Record<MappingKey, string>) => void;
  onRowFilterChange: (filter: EventRowFilterForm) => void;
  onPreprocessingConfigChange: (
    config: typeof DEFAULT_PREPROCESSING_CONFIG,
  ) => void;
  onCancelPreprocessingRun: (runId: string) => void;
  onSaveTemplateFromRun: (run: PreprocessingRun) => void;
  onSubmitEventMapping: () => void;
  onUploadEeg: () => void;
  onUploadEvent: () => void;
  onValidate: () => void;
  metadata: LoadState<DatasetMetadata>;
  preprocessingConfig: typeof DEFAULT_PREPROCESSING_CONFIG;
  preprocessingRuns: LoadState<PreprocessingRun[]>;
  uploadedEegFilename: string | null;
  uploadedEventFilename: string | null;
  validation: ValidationReport | null;
}) {
  const disabled = !activeDataset;
  const canContinue = validation?.valid === true || activeDataset?.status === "valid";
  const configError = getPreprocessingConfigError(preprocessingConfig);
  const channelNames = metadata.status === "success" ? metadata.data.channel_names : [];
  const eegStatus = getUploadStatus({
    disabled,
    selectedFilename: eegFile?.name ?? null,
    uploadedFilename: uploadedEegFilename,
    uploadedId: activeDataset?.recording_id ?? null,
    emptyText: "No EEG file selected",
    uploadedText: "EEG recording uploaded",
  });
  const eventStatus = getUploadStatus({
    disabled,
    selectedFilename: eventFile?.name ?? null,
    uploadedFilename: uploadedEventFilename,
    uploadedId: activeDataset?.event_log_id ?? null,
    emptyText: "No event log selected",
    uploadedText: "Event log uploaded",
  });

  return (
    <div className="intake-stack">
      <section className="tool-section" aria-labelledby="files-title">
        <div className="tool-section-header">
          <span>01</span>
          <h3 id="files-title">Files</h3>
        </div>
        <div className="upload-grid">
          <div className="upload-group">
            <div className="upload-heading">
              <h4>EEG Recording</h4>
              <span className="upload-state" data-state={eegStatus.state}>
                {eegStatus.label}
              </span>
            </div>
            <p className="upload-help">
              Supported formats: FIF, EDF, BDF, EEGLAB SET, BrainVision VHDR.
            </p>
            <p className="upload-example">
              Example: <code>{EEG_EXAMPLE_PATH}</code>
            </p>
            <input
              accept={SUPPORTED_EEG_EXTENSIONS.join(",")}
              data-testid="eeg-file-input"
              disabled={disabled}
              onChange={(event) => onEegFileChange(event.target.files?.[0] ?? null)}
              type="file"
            />
            <p className="upload-status" data-testid="eeg-upload-status">
              {eegStatus.detail}
            </p>
            <button
              className="secondary-button"
              data-testid="upload-eeg-button"
              disabled={disabled || !eegFile || busyAction === "eeg-upload"}
              onClick={onUploadEeg}
              type="button"
            >
              Upload EEG
            </button>
            <p className="upload-next-step">
              Next: upload the matching event log, then review event mapping.
            </p>
          </div>
          <div className="upload-group">
            <div className="upload-heading">
              <h4>Event Log</h4>
              <span className="upload-state" data-state={eventStatus.state}>
                {eventStatus.label}
              </span>
            </div>
            <p className="upload-help">
              Supported formats: CSV or TSV. Include an onset column plus optional
              duration, trial_type, response, correct, and reaction time columns.
            </p>
            <p className="upload-example">
              Example: <code>{EVENT_EXAMPLE_PATH}</code>
            </p>
            <input
              accept=".csv,.tsv,text/csv,text/tab-separated-values"
              data-testid="event-file-input"
              disabled={disabled}
              onChange={(event) => onEventFileChange(event.target.files?.[0] ?? null)}
              type="file"
            />
            <p className="upload-status" data-testid="event-upload-status">
              {eventStatus.detail}
            </p>
            <button
              className="secondary-button"
              data-testid="upload-events-button"
              disabled={disabled || !eventFile || busyAction === "event-upload"}
              onClick={onUploadEvent}
              type="button"
            >
              Upload Events
            </button>
            <p className="upload-next-step">
              Next: confirm the previewed columns and save the event mapping.
            </p>
          </div>
        </div>
      </section>

      <section className="tool-section" aria-labelledby="mapping-title">
        <div className="tool-section-header">
          <span>02</span>
          <h3 id="mapping-title">Event Mapping</h3>
        </div>
        {eventPreview ? (
          <div className="mapping-layout">
            <div>
              <div className="mapping-controls">
                <label>
                  <span>Preset</span>
                  <select
                    data-testid="mapping-preset-select"
                    onChange={(event) =>
                      onEventMappingPresetChange(
                        event.target.value as EventMappingPreset,
                      )
                    }
                    value={eventMappingPreset}
                  >
                    {EVENT_MAPPING_PRESETS.map((preset) => (
                      <option key={preset.value || "custom"} value={preset.value}>
                        {preset.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="mapping-grid">
                {MAPPING_FIELDS.map((field) => (
                  <label key={field.key}>
                    <span>
                      {field.label}
                      {field.required ? " *" : ""}
                    </span>
                    <select
                      data-testid={`mapping-${field.key}-select`}
                      disabled={Boolean(eventMappingPreset)}
                      onChange={(event) =>
                        onMappingChange({
                          ...mapping,
                          [field.key]: event.target.value,
                        })
                      }
                      value={mapping[field.key]}
                    >
                      <option value="">Unmapped</option>
                      {eventPreview.columns.map((column) => (
                        <option key={column} value={column}>
                          {column}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
              <div className="row-filter-grid">
                <label>
                  <span>Include</span>
                  <input
                    data-testid="row-filter-include-input"
                    onChange={(event) =>
                      onRowFilterChange({
                        ...eventRowFilter,
                        include: event.target.value,
                      })
                    }
                    placeholder="trial_type=target"
                    type="text"
                    value={eventRowFilter.include}
                  />
                </label>
                <label>
                  <span>Exclude</span>
                  <input
                    data-testid="row-filter-exclude-input"
                    onChange={(event) =>
                      onRowFilterChange({
                        ...eventRowFilter,
                        exclude: event.target.value,
                      })
                    }
                    placeholder="status=reject"
                    type="text"
                    value={eventRowFilter.exclude}
                  />
                </label>
              </div>
              <button
                className="primary-button"
                data-testid="save-mapping-button"
                disabled={
                  (!eventMappingPreset && !mapping.onset_seconds) ||
                  busyAction === "event-mapping"
                }
                onClick={onSubmitEventMapping}
                type="button"
              >
                Save Mapping
              </button>
            </div>

            <EventPreviewTable preview={eventPreview} />
          </div>
        ) : (
          <p className="muted">Upload a CSV or TSV event log to preview columns.</p>
        )}
      </section>

      <section className="tool-section" aria-labelledby="validation-title">
        <div className="tool-section-header">
          <span>03</span>
          <h3 id="validation-title">Validation</h3>
        </div>
        <div className="validation-bar">
          <button
            className="primary-button"
            data-testid="validate-dataset-button"
            disabled={disabled || busyAction === "validation"}
            onClick={onValidate}
            type="button"
          >
            Validate Dataset
          </button>
          {eventLog ? (
            <span className="muted">
              {eventLog.events.length} normalized / {eventLog.row_count} rows
              {eventLog.filter_count > 0
                ? ` / ${eventLog.filter_count} filtered`
                : ""}
            </span>
          ) : (
            <span className="muted">No mapped event log yet</span>
          )}
        </div>
        {validation ? <ValidationPanel report={validation} /> : null}
      </section>

      <section
        className="tool-section preprocessing-section"
        aria-labelledby="preprocessing-title"
      >
        <div className="tool-section-header">
          <span>04</span>
          <h3 id="preprocessing-title">Preprocessing</h3>
          <small>{canContinue ? "ready" : "blocked"}</small>
        </div>
        <div className="preprocessing-copy">
          {canContinue ? (
            <p className="muted">Configure filters and create a run.</p>
          ) : (
            <p className="muted">Validation must pass before preprocessing starts.</p>
          )}
          {configError ? <p className="error-text">{configError}</p> : null}
        </div>
        <div className="preprocessing-grid">
          <label>
            <span>High-pass Hz</span>
            <input
              disabled={!canContinue}
              min="0"
              onChange={(event) =>
                onPreprocessingConfigChange({
                  ...preprocessingConfig,
                  high_pass_hz: event.target.value,
                })
              }
              step="0.1"
              type="number"
              value={preprocessingConfig.high_pass_hz}
            />
          </label>
          <label>
            <span>Low-pass Hz</span>
            <input
              disabled={!canContinue}
              min="0.1"
              onChange={(event) =>
                onPreprocessingConfigChange({
                  ...preprocessingConfig,
                  low_pass_hz: event.target.value,
                })
              }
              step="0.1"
              type="number"
              value={preprocessingConfig.low_pass_hz}
            />
          </label>
          <label>
            <span>Notch Hz</span>
            <input
              disabled={!canContinue}
              min="0.1"
              onChange={(event) =>
                onPreprocessingConfigChange({
                  ...preprocessingConfig,
                  notch_hz: event.target.value,
                })
              }
              placeholder="Optional"
              step="0.1"
              type="number"
              value={preprocessingConfig.notch_hz}
            />
          </label>
          <label>
            <span>Resample Hz</span>
            <input
              data-testid="resample-hz-input"
              disabled={!canContinue}
              min="0.1"
              onChange={(event) =>
                onPreprocessingConfigChange({
                  ...preprocessingConfig,
                  resample_hz: event.target.value,
                })
              }
              placeholder="Optional"
              step="0.1"
              type="number"
              value={preprocessingConfig.resample_hz}
            />
          </label>
          <label>
            <span>Reference</span>
            <select
              data-testid="reference-select"
              disabled={!canContinue}
              onChange={(event) =>
                onPreprocessingConfigChange({
                  ...preprocessingConfig,
                  reference: event.target.value,
                })
              }
              value={preprocessingConfig.reference}
            >
              <option value="">Unchanged</option>
              <option value="average">Average</option>
            </select>
          </label>
          <label>
            <span>Manual bad channels</span>
            <select
              disabled={!canContinue || channelNames.length === 0}
              multiple
              onChange={(event) =>
                onPreprocessingConfigChange({
                  ...preprocessingConfig,
                  manual_bad_channels: Array.from(
                    event.currentTarget.selectedOptions,
                    (option) => option.value,
                  ),
                })
              }
              size={Math.min(Math.max(channelNames.length, 2), 8)}
              value={preprocessingConfig.manual_bad_channels}
            >
              {channelNames.map((channelName) => (
                <option key={channelName} value={channelName}>
                  {channelName}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Interpolate bads</span>
            <input
              checked={preprocessingConfig.bad_channel_interpolation.enabled}
              disabled={
                !canContinue || preprocessingConfig.manual_bad_channels.length === 0
              }
              onChange={(event) =>
                onPreprocessingConfigChange({
                  ...preprocessingConfig,
                  bad_channel_interpolation: {
                    ...preprocessingConfig.bad_channel_interpolation,
                    enabled: event.target.checked,
                  },
                })
              }
              type="checkbox"
            />
          </label>
          <label>
            <span>Clear bad labels</span>
            <input
              checked={preprocessingConfig.bad_channel_interpolation.reset_bads}
              disabled={
                !canContinue ||
                !preprocessingConfig.bad_channel_interpolation.enabled
              }
              onChange={(event) =>
                onPreprocessingConfigChange({
                  ...preprocessingConfig,
                  bad_channel_interpolation: {
                    ...preprocessingConfig.bad_channel_interpolation,
                    reset_bads: event.target.checked,
                  },
                })
              }
              type="checkbox"
            />
          </label>
          <label>
            <span>Bad-channel report</span>
            <input
              checked={preprocessingConfig.bad_channel_detection.enabled}
              disabled={!canContinue}
              onChange={(event) =>
                onPreprocessingConfigChange({
                  ...preprocessingConfig,
                  bad_channel_detection: {
                    ...preprocessingConfig.bad_channel_detection,
                    enabled: event.target.checked,
                  },
                })
              }
              type="checkbox"
            />
          </label>
          <label>
            <span>Detection method</span>
            <select
              disabled={
                !canContinue || !preprocessingConfig.bad_channel_detection.enabled
              }
              onChange={(event) =>
                onPreprocessingConfigChange({
                  ...preprocessingConfig,
                  bad_channel_detection: {
                    ...preprocessingConfig.bad_channel_detection,
                    method: event.target.value,
                  },
                })
              }
              value={preprocessingConfig.bad_channel_detection.method}
            >
              <option value="deviation">Deviation</option>
              <option value="flat">Flat</option>
              <option value="ransac">RANSAC</option>
            </select>
          </label>
          <label>
            <span>Z-score threshold</span>
            <input
              disabled={
                !canContinue ||
                !preprocessingConfig.bad_channel_detection.enabled ||
                preprocessingConfig.bad_channel_detection.method === "flat"
              }
              min="0.1"
              onChange={(event) =>
                onPreprocessingConfigChange({
                  ...preprocessingConfig,
                  bad_channel_detection: {
                    ...preprocessingConfig.bad_channel_detection,
                    zscore_threshold: event.target.value,
                  },
                })
              }
              step="0.1"
              type="number"
              value={preprocessingConfig.bad_channel_detection.zscore_threshold}
            />
          </label>
          <label>
            <span>Min correlation</span>
            <input
              disabled={
                !canContinue ||
                !preprocessingConfig.bad_channel_detection.enabled ||
                preprocessingConfig.bad_channel_detection.method !== "deviation"
              }
              max="1"
              min="0"
              onChange={(event) =>
                onPreprocessingConfigChange({
                  ...preprocessingConfig,
                  bad_channel_detection: {
                    ...preprocessingConfig.bad_channel_detection,
                    minimum_correlation: event.target.value,
                  },
                })
              }
              placeholder="Optional"
              step="0.05"
              type="number"
              value={preprocessingConfig.bad_channel_detection.minimum_correlation}
            />
          </label>
          <label>
            <span>EOG report</span>
            <input
              checked={preprocessingConfig.artifact_handling.eog_enabled}
              disabled={!canContinue}
              onChange={(event) =>
                onPreprocessingConfigChange({
                  ...preprocessingConfig,
                  artifact_handling: {
                    ...preprocessingConfig.artifact_handling,
                    eog_enabled: event.target.checked,
                  },
                })
              }
              type="checkbox"
            />
          </label>
          <label>
            <span>EOG channels</span>
            <input
              disabled={
                !canContinue || !preprocessingConfig.artifact_handling.eog_enabled
              }
              onChange={(event) =>
                onPreprocessingConfigChange({
                  ...preprocessingConfig,
                  artifact_handling: {
                    ...preprocessingConfig.artifact_handling,
                    eog_channels: event.target.value,
                  },
                })
              }
              placeholder={channelNames.slice(0, 2).join(", ")}
              type="text"
              value={preprocessingConfig.artifact_handling.eog_channels}
            />
          </label>
          <label>
            <span>ECG report</span>
            <input
              checked={preprocessingConfig.artifact_handling.ecg_enabled}
              disabled={!canContinue}
              onChange={(event) =>
                onPreprocessingConfigChange({
                  ...preprocessingConfig,
                  artifact_handling: {
                    ...preprocessingConfig.artifact_handling,
                    ecg_enabled: event.target.checked,
                  },
                })
              }
              type="checkbox"
            />
          </label>
          <label>
            <span>ECG channels</span>
            <input
              disabled={
                !canContinue || !preprocessingConfig.artifact_handling.ecg_enabled
              }
              onChange={(event) =>
                onPreprocessingConfigChange({
                  ...preprocessingConfig,
                  artifact_handling: {
                    ...preprocessingConfig.artifact_handling,
                    ecg_channels: event.target.value,
                  },
                })
              }
              placeholder={channelNames.slice(0, 2).join(", ")}
              type="text"
              value={preprocessingConfig.artifact_handling.ecg_channels}
            />
          </label>
          <label>
            <span>ICA</span>
            <input
              checked={preprocessingConfig.ica.enabled}
              disabled={!canContinue}
              onChange={(event) =>
                onPreprocessingConfigChange({
                  ...preprocessingConfig,
                  ica: {
                    ...preprocessingConfig.ica,
                    enabled: event.target.checked,
                  },
                })
              }
              type="checkbox"
            />
          </label>
          <label>
            <span>ICA method</span>
            <select
              disabled={!canContinue || !preprocessingConfig.ica.enabled}
              onChange={(event) =>
                onPreprocessingConfigChange({
                  ...preprocessingConfig,
                  ica: {
                    ...preprocessingConfig.ica,
                    method: event.target.value,
                  },
                })
              }
              value={preprocessingConfig.ica.method}
            >
              <option value="fastica">fastica</option>
              <option value="infomax">infomax</option>
              <option value="picard">picard</option>
            </select>
          </label>
          <label>
            <span>ICA components</span>
            <input
              disabled={!canContinue || !preprocessingConfig.ica.enabled}
              onChange={(event) =>
                onPreprocessingConfigChange({
                  ...preprocessingConfig,
                  ica: {
                    ...preprocessingConfig.ica,
                    n_components: event.target.value,
                  },
                })
              }
              placeholder="Optional"
              step="0.05"
              type="number"
              value={preprocessingConfig.ica.n_components}
            />
          </label>
          <label>
            <span>Exclude ICA</span>
            <input
              disabled={!canContinue || !preprocessingConfig.ica.enabled}
              onChange={(event) =>
                onPreprocessingConfigChange({
                  ...preprocessingConfig,
                  ica: {
                    ...preprocessingConfig.ica,
                    exclude_components: event.target.value,
                  },
                })
              }
              placeholder="0, 1"
              type="text"
              value={preprocessingConfig.ica.exclude_components}
            />
          </label>
        </div>
        <button
          className="primary-button"
          data-testid="start-preprocessing-button"
          disabled={!canContinue || Boolean(configError) || busyAction === "preprocessing"}
          onClick={onBeginPreprocessing}
          type="button"
        >
          Start Preprocessing
        </button>
        <PreprocessingRunList
          busyAction={busyAction}
          onCancel={onCancelPreprocessingRun}
          onSaveTemplate={onSaveTemplateFromRun}
          runs={preprocessingRuns}
        />
      </section>
    </div>
  );
}

function PreprocessingRunList({
  busyAction,
  onCancel,
  onSaveTemplate,
  runs,
}: {
  busyAction: string | null;
  onCancel: (runId: string) => void;
  onSaveTemplate: (run: PreprocessingRun) => void;
  runs: LoadState<PreprocessingRun[]>;
}) {
  if (runs.status === "loading" || runs.status === "idle") {
    return <p className="muted">Loading preprocessing runs...</p>;
  }

  if (runs.status === "error") {
    return <p className="error-text">{runs.error}</p>;
  }

  const runData = runs.data ?? [];
  if (runData.length === 0) {
    return <p className="muted">No preprocessing runs yet.</p>;
  }

  return (
    <div className="run-list" data-testid="preprocessing-runs">
      {runData.map((run) => (
        <div className="run-row" key={run.run_id}>
          <div>
            <strong>{run.run_id}</strong>
            <small>{run.output_path ?? "No output file"}</small>
          </div>
          <div className="run-actions">
            <div className="run-meta">
              <span>{run.status}</span>
              <span>{formatRunMetadata(run.output_metadata)}</span>
            </div>
            {run.status === "completed" ? (
              <button
                className="secondary-button compact-button"
                data-testid={`save-template-preprocessing-${run.run_id}`}
                disabled={busyAction === `template-save-${run.run_id}`}
                onClick={() => onSaveTemplate(run)}
                type="button"
              >
                {busyAction === `template-save-${run.run_id}`
                  ? "Saving..."
                  : "Save Template"}
              </button>
            ) : null}
            {["pending", "running"].includes(run.status) ? (
              <button
                className="secondary-button compact-button"
                onClick={() => onCancel(run.run_id)}
                type="button"
              >
                Cancel
              </button>
            ) : null}
          </div>
          <RunWarnings diagnostics={run.diagnostics} warnings={run.warnings} />
          {run.errors.length > 0 ? (
            <p className="error-text">{run.errors.join(" ")}</p>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function RunWarnings({
  diagnostics,
  warnings,
}: {
  diagnostics?: RunDiagnostics | Record<string, never> | null;
  warnings?: string[];
}) {
  const structuredWarnings =
    diagnostics &&
    "warnings" in diagnostics &&
    Array.isArray(diagnostics.warnings)
      ? diagnostics.warnings
      : [];
  const unstructuredWarnings = Array.isArray(warnings) ? warnings : [];

  if (structuredWarnings.length > 0) {
    return (
      <div className="run-warning-list" aria-label="Run warnings">
        {structuredWarnings.map((warning, index) => (
          <div className="run-warning" key={`${warning.code}-${index}`}>
            <strong>{warning.code}</strong>
            <span>
              {warning.source} / {warning.severity}
            </span>
            {warning.impact ? <p>{warning.impact}</p> : null}
            {warning.suggested_action ? (
              <small>{warning.suggested_action}</small>
            ) : null}
          </div>
        ))}
      </div>
    );
  }

  if (unstructuredWarnings.length === 0) {
    return null;
  }
  return <p className="muted">{unstructuredWarnings.join(" ")}</p>;
}

function EpochSection({
  activeDataset,
  busyAction,
  completedPreprocessingRuns,
  epochConfig,
  epochRuns,
  onEpochConfigChange,
  onSaveTemplateFromRun,
  onStartEpochRun,
}: {
  activeDataset: Dataset | null;
  busyAction: string | null;
  completedPreprocessingRuns: PreprocessingRun[];
  epochConfig: typeof DEFAULT_EPOCH_CONFIG;
  epochRuns: LoadState<EpochRun[]>;
  onEpochConfigChange: (config: typeof DEFAULT_EPOCH_CONFIG) => void;
  onSaveTemplateFromRun: (run: EpochRun) => void;
  onStartEpochRun: () => void;
}) {
  const disabled = !activeDataset || completedPreprocessingRuns.length === 0;
  const configError = getEpochConfigError(epochConfig);

  return (
    <div className="intake-stack">
      <section className="tool-section" aria-labelledby="epoch-config-title">
        <div className="tool-section-header">
          <span>05</span>
          <h3 id="epoch-config-title">Epoch Run</h3>
          <small>{disabled ? "blocked" : "ready"}</small>
        </div>
        {completedPreprocessingRuns.length === 0 ? (
          <p className="muted">No completed preprocessing runs yet.</p>
        ) : null}
        {configError ? <p className="error-text">{configError}</p> : null}
        <div className="epoch-grid">
          <label className="wide-field">
            <span>Preprocessing Run</span>
            <select
              data-testid="epoch-preprocessing-run-select"
              disabled={disabled}
              onChange={(event) =>
                onEpochConfigChange({
                  ...epochConfig,
                  preprocessing_run_id: event.target.value,
                })
              }
              value={epochConfig.preprocessing_run_id}
            >
              <option value="">Select completed run</option>
              {completedPreprocessingRuns.map((run) => (
                <option key={run.run_id} value={run.run_id}>
                  {run.run_id}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Condition Field</span>
            <select
              data-testid="epoch-condition-field-select"
              disabled={disabled}
              onChange={(event) =>
                onEpochConfigChange({
                  ...epochConfig,
                  condition_field: event.target.value,
                })
              }
              value={epochConfig.condition_field}
            >
              {CONDITION_FIELDS.map((field) => (
                <option key={field} value={field}>
                  {field}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>tmin s</span>
            <input
              data-testid="epoch-tmin-input"
              disabled={disabled}
              onChange={(event) =>
                onEpochConfigChange({
                  ...epochConfig,
                  tmin_seconds: event.target.value,
                })
              }
              step="0.01"
              type="number"
              value={epochConfig.tmin_seconds}
            />
          </label>
          <label>
            <span>tmax s</span>
            <input
              data-testid="epoch-tmax-input"
              disabled={disabled}
              onChange={(event) =>
                onEpochConfigChange({
                  ...epochConfig,
                  tmax_seconds: event.target.value,
                })
              }
              step="0.01"
              type="number"
              value={epochConfig.tmax_seconds}
            />
          </label>
          <label>
            <span>Baseline Start</span>
            <input
              disabled={disabled || !epochConfig.baseline_enabled}
              onChange={(event) =>
                onEpochConfigChange({
                  ...epochConfig,
                  baseline_start_seconds: event.target.value,
                })
              }
              step="0.01"
              type="number"
              value={epochConfig.baseline_start_seconds}
            />
          </label>
          <label>
            <span>Baseline End</span>
            <input
              disabled={disabled || !epochConfig.baseline_enabled}
              onChange={(event) =>
                onEpochConfigChange({
                  ...epochConfig,
                  baseline_end_seconds: event.target.value,
                })
              }
              step="0.01"
              type="number"
              value={epochConfig.baseline_end_seconds}
            />
          </label>
          <label>
            <span>Reject EEG uV</span>
            <input
              data-testid="epoch-reject-input"
              disabled={disabled}
              min="0.1"
              onChange={(event) =>
                onEpochConfigChange({
                  ...epochConfig,
                  reject_eeg_uv: event.target.value,
                })
              }
              placeholder="Optional"
              step="0.1"
              type="number"
              value={epochConfig.reject_eeg_uv}
            />
          </label>
          <label className="checkbox-field">
            <input
              checked={epochConfig.baseline_enabled}
              disabled={disabled}
              onChange={(event) =>
                onEpochConfigChange({
                  ...epochConfig,
                  baseline_enabled: event.target.checked,
                })
              }
              type="checkbox"
            />
            <span>Baseline</span>
          </label>
        </div>
        <button
          className="primary-button"
          data-testid="start-epoch-button"
          disabled={disabled || Boolean(configError) || busyAction === "epoch"}
          onClick={onStartEpochRun}
          type="button"
        >
          Start Epoching
        </button>
      </section>
      <EpochRunList
        busyAction={busyAction}
        onSaveTemplate={onSaveTemplateFromRun}
        runs={epochRuns}
      />
    </div>
  );
}

function EpochRunList({
  busyAction,
  onSaveTemplate,
  runs,
}: {
  busyAction: string | null;
  onSaveTemplate: (run: EpochRun) => void;
  runs: LoadState<EpochRun[]>;
}) {
  if (runs.status === "loading" || runs.status === "idle") {
    return <p className="muted">Loading epoch runs...</p>;
  }

  if (runs.status === "error") {
    return <p className="error-text">{runs.error}</p>;
  }

  const runData = runs.data ?? [];
  if (runData.length === 0) {
    return <p className="muted">No epoch runs yet.</p>;
  }

  return (
    <div className="run-list" data-testid="epoch-runs">
      {runData.map((run) => (
        <div className="run-row" key={run.run_id}>
          <div>
            <strong>{run.run_id}</strong>
            <small>{run.output_path ?? "No output file"}</small>
          </div>
          <div className="run-actions">
            <div className="run-meta">
              <span>{run.status}</span>
              <span>{formatEpochMetadata(run.output_metadata)}</span>
              <span>{run.config.condition_field}</span>
            </div>
            {run.status === "completed" ? (
              <button
                className="secondary-button compact-button"
                data-testid={`save-template-epoch-${run.run_id}`}
                disabled={busyAction === `template-save-${run.run_id}`}
                onClick={() => onSaveTemplate(run)}
                type="button"
              >
                {busyAction === `template-save-${run.run_id}`
                  ? "Saving..."
                  : "Save Template"}
              </button>
            ) : null}
          </div>
          <ConditionCountSummary metadata={run.output_metadata} />
          <RunWarnings diagnostics={run.diagnostics} warnings={run.warnings} />
          {run.errors.length > 0 ? (
            <p className="error-text">{run.errors.join(" ")}</p>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function ConditionCountSummary({
  metadata,
}: {
  metadata: Record<string, MetadataValue>;
}) {
  const conditionCount = metadata.condition_count;
  const epochCount = metadata.epoch_count;
  const droppedCount = metadata.dropped_epoch_count;
  const usedEventCount = metadata.event_count_used;

  if (
    typeof conditionCount !== "number" &&
    typeof epochCount !== "number" &&
    typeof droppedCount !== "number" &&
    typeof usedEventCount !== "number"
  ) {
    return null;
  }

  return (
    <dl className="run-summary-grid">
      <div>
        <dt>Conditions</dt>
        <dd>{typeof conditionCount === "number" ? conditionCount : "-"}</dd>
      </div>
      <div>
        <dt>Used Events</dt>
        <dd>{typeof usedEventCount === "number" ? usedEventCount : "-"}</dd>
      </div>
      <div>
        <dt>Epochs</dt>
        <dd>{typeof epochCount === "number" ? epochCount : "-"}</dd>
      </div>
      <div>
        <dt>Dropped</dt>
        <dd>{typeof droppedCount === "number" ? droppedCount : "-"}</dd>
      </div>
    </dl>
  );
}

function ErpSection({
  activeDataset,
  artifactIntegrity,
  busyAction,
  comparisonConfig,
  completedEpochRuns,
  completedErpRuns,
  erpConfig,
  erpRuns,
  onComparisonConfigChange,
  onDownloadErpExportBundle,
  onErpConfigChange,
  onGenerateErpAnalysisReport,
  onCheckArtifactIntegrity,
  onOpenErpAnalysisReport,
  onSaveTemplateFromRun,
  onStartComparisonSummary,
  onStartErpRun,
}: {
  activeDataset: Dataset | null;
  artifactIntegrity: Record<string, LoadState<ArtifactIntegrityPayload>>;
  busyAction: string | null;
  comparisonConfig: typeof DEFAULT_COMPARISON_CONFIG;
  completedEpochRuns: EpochRun[];
  completedErpRuns: ErpRun[];
  erpConfig: typeof DEFAULT_ERP_CONFIG;
  erpRuns: LoadState<ErpRun[]>;
  onComparisonConfigChange: (config: typeof DEFAULT_COMPARISON_CONFIG) => void;
  onDownloadErpExportBundle: (run: ErpRun) => void;
  onErpConfigChange: (config: typeof DEFAULT_ERP_CONFIG) => void;
  onGenerateErpAnalysisReport: (run: ErpRun) => void;
  onCheckArtifactIntegrity: (run: ErpRun) => void;
  onOpenErpAnalysisReport: (run: ErpRun) => void;
  onSaveTemplateFromRun: (run: ErpRun) => void;
  onStartComparisonSummary: () => void;
  onStartErpRun: () => void;
}) {
  const disabled = !activeDataset || completedEpochRuns.length === 0;
  const configError = getErpConfigError(erpConfig);

  return (
    <div className="intake-stack">
      <section className="tool-section" aria-labelledby="erp-config-title">
        <div className="tool-section-header">
          <span>06</span>
          <h3 id="erp-config-title">ERP Run</h3>
          <small>{disabled ? "blocked" : "ready"}</small>
        </div>
        {completedEpochRuns.length === 0 ? (
          <p className="muted">No completed epoch runs yet.</p>
        ) : null}
        {configError ? <p className="error-text">{configError}</p> : null}
        <div className="epoch-grid">
          <label className="wide-field">
            <span>Epoch Run</span>
            <select
              data-testid="erp-epoch-run-select"
              disabled={disabled}
              onChange={(event) =>
                onErpConfigChange({
                  ...erpConfig,
                  epoch_run_id: event.target.value,
                })
              }
              value={erpConfig.epoch_run_id}
            >
              <option value="">Select completed run</option>
              {completedEpochRuns.map((run) => (
                <option key={run.run_id} value={run.run_id}>
                  {run.run_id}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Conditions</span>
            <input
              data-testid="erp-conditions-input"
              disabled={disabled}
              onChange={(event) =>
                onErpConfigChange({
                  ...erpConfig,
                  conditions: event.target.value,
                })
              }
              placeholder="All"
              type="text"
              value={erpConfig.conditions}
            />
          </label>
          <label>
            <span>Picks</span>
            <input
              disabled={disabled}
              onChange={(event) =>
                onErpConfigChange({
                  ...erpConfig,
                  picks: event.target.value,
                })
              }
              placeholder="All channels"
              type="text"
              value={erpConfig.picks}
            />
          </label>
          <label>
            <span>Plot Mode</span>
            <select
              data-testid="erp-plot-mode-select"
              disabled={disabled}
              onChange={(event) =>
                onErpConfigChange({
                  ...erpConfig,
                  plot_mode: event.target.value,
                })
              }
              value={erpConfig.plot_mode}
            >
              <option value="gfp">GFP</option>
              <option value="channel">Channel</option>
            </select>
          </label>
          <label>
            <span>Plot Channel</span>
            <input
              data-testid="erp-plot-channel-input"
              disabled={disabled || erpConfig.plot_mode !== "channel"}
              onChange={(event) =>
                onErpConfigChange({
                  ...erpConfig,
                  plot_channel: event.target.value,
                })
              }
              placeholder="Fp1"
              type="text"
              value={erpConfig.plot_channel}
            />
          </label>
        </div>
        <button
          className="primary-button"
          data-testid="start-erp-button"
          disabled={disabled || Boolean(configError) || busyAction === "erp"}
          onClick={onStartErpRun}
          type="button"
        >
          Generate ERP
        </button>
      </section>
      <ErpRunList
        artifactIntegrity={artifactIntegrity}
        busyAction={busyAction}
        onCheckArtifactIntegrity={onCheckArtifactIntegrity}
        onDownloadExportBundle={onDownloadErpExportBundle}
        onGenerateAnalysisReport={onGenerateErpAnalysisReport}
        onOpenAnalysisReport={onOpenErpAnalysisReport}
        onSaveTemplate={onSaveTemplateFromRun}
        runs={erpRuns}
      />
      <ComparisonSection
        busyAction={busyAction}
        comparisonConfig={comparisonConfig}
        completedErpRuns={completedErpRuns}
        onComparisonConfigChange={onComparisonConfigChange}
        onStartComparisonSummary={onStartComparisonSummary}
      />
    </div>
  );
}

function ErpRunList({
  artifactIntegrity,
  busyAction,
  onCheckArtifactIntegrity,
  onDownloadExportBundle,
  onGenerateAnalysisReport,
  onOpenAnalysisReport,
  onSaveTemplate,
  runs,
}: {
  artifactIntegrity: Record<string, LoadState<ArtifactIntegrityPayload>>;
  busyAction: string | null;
  onCheckArtifactIntegrity: (run: ErpRun) => void;
  onDownloadExportBundle: (run: ErpRun) => void;
  onGenerateAnalysisReport: (run: ErpRun) => void;
  onOpenAnalysisReport: (run: ErpRun) => void;
  onSaveTemplate: (run: ErpRun) => void;
  runs: LoadState<ErpRun[]>;
}) {
  if (runs.status === "loading" || runs.status === "idle") {
    return <p className="muted">Loading ERP runs...</p>;
  }

  if (runs.status === "error") {
    return <p className="error-text">{runs.error}</p>;
  }

  const runData = runs.data ?? [];
  if (runData.length === 0) {
    return <p className="muted">No ERP runs yet.</p>;
  }

  return (
    <div className="run-list" data-testid="erp-runs">
      {runData.map((run) => {
        const exportReady = isErpExportReady(run);
        const exportBusy = busyAction === `export-${run.run_id}`;
        const reportBusy = busyAction === `report-${run.run_id}`;
        const reportReady =
          typeof run.output_metadata.analysis_report_url === "string" &&
          run.output_metadata.analysis_report_url.length > 0;
        const exportStatus = getErpExportStatus(run);
        const integrity = artifactIntegrity[run.run_id] ?? {
          status: "idle",
          data: null,
          error: null,
        };
        return (
          <div className="run-row" key={run.run_id}>
            <div>
              <strong>{run.run_id}</strong>
              <small>{run.output_path ?? "No output file"}</small>
            </div>
            <div className="run-actions">
              <div className="run-meta">
                <span>{run.status}</span>
                <span>{formatErpMetadata(run.output_metadata)}</span>
                <span>{run.config.plot_mode}</span>
              </div>
              {run.status === "completed" ? (
                <button
                  className="secondary-button compact-button"
                  data-testid={`save-template-erp-${run.run_id}`}
                  disabled={busyAction === `template-save-${run.run_id}`}
                  onClick={() => onSaveTemplate(run)}
                  type="button"
                >
                  {busyAction === `template-save-${run.run_id}`
                    ? "Saving..."
                    : "Save Template"}
                </button>
              ) : null}
              <p className="run-action-status" data-ready={exportReady}>
                {exportStatus}
              </p>
              <ArtifactIntegritySummary integrity={integrity} />
              <button
                className="secondary-button compact-button"
                data-testid={`integrity-erp-run-${run.run_id}`}
                disabled={!exportReady || integrity.status === "loading"}
                onClick={() => onCheckArtifactIntegrity(run)}
                title={
                  exportReady
                    ? "Check artifact existence and checksums"
                    : "Integrity check requires a completed artifact manifest"
                }
                type="button"
              >
                {integrity.status === "loading" ? "Checking..." : "Check Artifacts"}
              </button>
              <button
                className="secondary-button compact-button"
                data-testid={`report-erp-run-${run.run_id}`}
                disabled={!exportReady || reportBusy}
                onClick={() => onGenerateAnalysisReport(run)}
                title={
                  exportReady
                    ? "Generate or refresh analysis_report.json"
                    : exportStatus
                }
                type="button"
              >
                {reportBusy ? "Preparing..." : "Generate Report"}
              </button>
              <button
                className="secondary-button compact-button"
                data-testid={`open-report-erp-run-${run.run_id}`}
                disabled={!reportReady}
                onClick={() => onOpenAnalysisReport(run)}
                title={
                  reportReady
                    ? "Open analysis report"
                    : "Generate the report before opening it"
                }
                type="button"
              >
                Open Report
              </button>
              <button
                className="secondary-button compact-button"
                data-testid={`export-erp-run-${run.run_id}`}
                disabled={!exportReady || exportBusy}
                onClick={() => onDownloadExportBundle(run)}
                title={
                  exportReady
                    ? reportReady
                      ? "Download ZIP with report, manifest, provenance, diagnostics, plots, and artifacts"
                      : "Download ZIP; report will be generated first"
                    : exportStatus
                }
                type="button"
              >
                {exportBusy ? "Preparing..." : "Export ZIP"}
              </button>
            </div>
            <ErpPreview run={run} />
            <RunWarnings diagnostics={run.diagnostics} warnings={run.warnings} />
            {run.errors.length > 0 ? (
              <p className="error-text">{run.errors.join(" ")}</p>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function ArtifactIntegritySummary({
  integrity,
}: {
  integrity: LoadState<ArtifactIntegrityPayload>;
}) {
  if (integrity.status === "idle") {
    return (
      <p className="integrity-status" data-status="idle">
        Integrity not checked.
      </p>
    );
  }

  if (integrity.status === "loading") {
    return (
      <p className="integrity-status" data-status="loading">
        Checking artifact integrity...
      </p>
    );
  }

  if (integrity.status === "error") {
    return (
      <p className="integrity-status" data-status="mismatch">
        Integrity check failed: {integrity.error}
      </p>
    );
  }

  const payload = integrity.data;
  if (!payload) {
    return (
      <p className="integrity-status" data-status="mismatch">
        Integrity check returned no data.
      </p>
    );
  }

  return (
    <div
      className="integrity-status"
      data-status={payload.status}
      data-testid="artifact-integrity-summary"
    >
      <strong>{payload.status.toUpperCase()}</strong>
      <span>
        OK {payload.status_counts.ok} / missing {payload.status_counts.missing} /
        mismatch {payload.status_counts.mismatch}
      </span>
    </div>
  );
}

function ErpPreview({ run }: { run: ErpRun }) {
  const filename = run.output_metadata.preview_plot_filename;
  const condition = run.output_metadata.preview_plot_condition;
  const plotStatus = run.output_metadata.plot_status;

  if (typeof filename !== "string" || !filename) {
    if (run.status === "completed" && plotStatus !== "completed") {
      return <p className="muted">Plot preview unavailable: {String(plotStatus)}</p>;
    }
    return null;
  }

  return (
    <figure className="erp-preview" data-testid="erp-preview">
      <img
        alt={`ERP plot ${typeof condition === "string" ? condition : run.run_id}`}
        src={artifactUrl(run.run_id, filename)}
      />
      <figcaption>
        {typeof condition === "string" ? condition : "ERP"} /{" "}
        {String(run.output_metadata.preview_plot_mode ?? "plot")}
      </figcaption>
    </figure>
  );
}

function QcDashboard({
  onPreprocessingConfigChange,
  preprocessingConfig,
  qcSummary,
}: {
  onPreprocessingConfigChange: (
    config: typeof DEFAULT_PREPROCESSING_CONFIG,
  ) => void;
  preprocessingConfig: typeof DEFAULT_PREPROCESSING_CONFIG;
  qcSummary: LoadState<QcSummaryResponse | null>;
}) {
  if (qcSummary.status === "loading" || qcSummary.status === "idle") {
    return <p className="muted">Loading QC summary...</p>;
  }
  if (qcSummary.status === "error") {
    return <p className="error-text">{qcSummary.error}</p>;
  }
  if (!qcSummary.data) {
    return <p className="muted">No completed QC run yet.</p>;
  }

  const missingArtifacts =
    qcSummary.data.summary.artifact_manifest?.missing_artifacts ?? [];

  return (
    <div className="qc-dashboard" data-testid="qc-dashboard">
      <div className="qc-header">
        <strong>{qcSummary.data.run_kind}</strong>
        <span>{qcSummary.data.run_id}</span>
        <span>
          {qcSummary.data.summary.artifact_manifest?.artifact_count ?? 0} artifacts
        </span>
      </div>
      {missingArtifacts.length > 0 ? (
        <div className="qc-alert">
          <strong>Missing artifacts</strong>
          <span>{missingArtifacts.map((artifact) => artifact.logical_name).join(", ")}</span>
        </div>
      ) : null}
      <PhaseDQc summary={asRecord(qcSummary.data.summary.phase_d)} />
      {qcSummary.data.summary.run_kind === "preprocessing" ? (
        <PreprocessingQc
          onPreprocessingConfigChange={onPreprocessingConfigChange}
          preprocessingConfig={preprocessingConfig}
          summary={qcSummary.data.summary.preprocessing ?? {}}
        />
      ) : null}
      {qcSummary.data.summary.run_kind === "epoch" ? (
        <EpochQc summary={qcSummary.data.summary.epoch ?? {}} />
      ) : null}
      {qcSummary.data.summary.run_kind === "erp" ? (
        <ErpQc summary={qcSummary.data.summary.erp ?? {}} />
      ) : null}
    </div>
  );
}

function PhaseDQc({ summary }: { summary: Record<string, unknown> }) {
  if (Object.keys(summary).length === 0) {
    return null;
  }
  const recording = asRecord(summary.recording);
  const eventLog = asRecord(summary.event_log);
  const diagnostics = asRecord(summary.diagnostics);
  const warnings = Array.isArray(diagnostics.warnings)
    ? diagnostics.warnings.filter(isRecord)
    : [];
  const sourceFiles = Array.isArray(recording.source_files)
    ? recording.source_files.filter(isRecord)
    : [];
  const sidecarDiscovery = asRecord(recording.sidecar_discovery);
  const candidates = Array.isArray(sidecarDiscovery.candidates)
    ? sidecarDiscovery.candidates.filter(isRecord)
    : [];
  const eventSourceColumns = asRecord(eventLog.source_columns);
  const sourceColumnNames = Array.isArray(eventSourceColumns.column_names)
    ? eventSourceColumns.column_names.map(String)
    : [];
  const batch = asRecord(summary.batch);

  return (
    <div className="qc-section">
      <h3>Phase D Context</h3>
      <dl className="run-summary-grid">
        <QcMetric label="Source Files" value={stringValue(sourceFiles.length)} />
        <QcMetric label="Sidecars" value={stringValue(candidates.length)} />
        <QcMetric label="Event Rows" value={stringValue(eventLog.row_count)} />
        <QcMetric label="Filtered Rows" value={stringValue(eventLog.filter_count)} />
        <QcMetric
          label="Condition Column"
          value={stringValue(eventLog.condition_column)}
        />
        <QcMetric label="Batch" value={stringValue(batch.batch_id)} />
      </dl>
      {sourceColumnNames.length > 0 ? (
        <p className="muted">Event source columns: {sourceColumnNames.join(", ")}</p>
      ) : null}
      {warnings.length > 0 ? (
        <div className="run-warning-list" aria-label="QC diagnostics">
          {warnings.map((warning, index) => (
            <div className="run-warning" key={`${warning.code}-${index}`}>
              <strong>{stringValue(warning.code)}</strong>
              <span>
                {stringValue(warning.source)} / {stringValue(warning.severity)}
              </span>
              {warning.impact ? <p>{stringValue(warning.impact)}</p> : null}
              {warning.suggested_action ? (
                <small>{stringValue(warning.suggested_action)}</small>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function PreprocessingQc({
  onPreprocessingConfigChange,
  preprocessingConfig,
  summary,
}: {
  onPreprocessingConfigChange: (
    config: typeof DEFAULT_PREPROCESSING_CONFIG,
  ) => void;
  preprocessingConfig: typeof DEFAULT_PREPROCESSING_CONFIG;
  summary: Record<string, unknown>;
}) {
  const filters = asRecord(summary.filters);
  const reference = asRecord(summary.reference);
  const resample = asRecord(summary.resample);
  const channelStatus = asRecord(summary.channel_status);
  const artifactRejection = asRecord(summary.artifact_rejection);
  const eogArtifacts = asRecord(artifactRejection.eog);
  const ecgArtifacts = asRecord(artifactRejection.ecg);
  const ica = asRecord(summary.ica);
  const beforeAfter = asRecord(summary.before_after);
  const delta = asRecord(beforeAfter.delta);

  return (
    <div className="qc-section">
      <h3>Preprocessing QC</h3>
      <dl className="run-summary-grid">
        <QcMetric label="High-pass" value={operationStatus(filters.high_pass)} />
        <QcMetric label="Low-pass" value={operationStatus(filters.low_pass)} />
        <QcMetric label="Notch" value={operationStatus(filters.notch)} />
        <QcMetric label="Reference" value={stringValue(reference.status)} />
        <QcMetric label="Resample" value={stringValue(resample.status)} />
        <QcMetric
          label="Input Bad Ch"
          value={stringValue(channelStatus.input_bad_channel_count)}
        />
        <QcMetric
          label="Output Bad Ch"
          value={stringValue(channelStatus.output_bad_channel_count)}
        />
        <QcMetric
          label="Artifact Reject"
          value={artifactRejection.enabled === true ? "enabled" : "off"}
        />
        <QcMetric
          label="Blink Candidates"
          value={stringValue(eogArtifacts.candidate_count)}
        />
        <QcMetric
          label="Heartbeat Candidates"
          value={stringValue(ecgArtifacts.candidate_count)}
        />
        <QcMetric label="ICA" value={stringValue(ica.status)} />
        <QcMetric
          label="ICA Components"
          value={stringValue(ica.component_count)}
        />
        <QcMetric
          label="Bad Ch Delta"
          value={formatSignedNumber(delta.bad_channel_count)}
        />
        <QcMetric
          label="Annotation Delta"
          value={formatSignedNumber(delta.annotation_count)}
        />
        <QcMetric
          label="Variance Ratio"
          value={formatRatio(delta.variance_mean_ratio)}
        />
        <QcMetric
          label="PSD Ratio"
          value={formatRatio(delta.psd_total_power_ratio)}
        />
      </dl>
      <IcaComponentReview
        ica={ica}
        onPreprocessingConfigChange={onPreprocessingConfigChange}
        preprocessingConfig={preprocessingConfig}
      />
    </div>
  );
}

function IcaComponentReview({
  ica,
  onPreprocessingConfigChange,
  preprocessingConfig,
}: {
  ica: Record<string, unknown>;
  onPreprocessingConfigChange: (
    config: typeof DEFAULT_PREPROCESSING_CONFIG,
  ) => void;
  preprocessingConfig: typeof DEFAULT_PREPROCESSING_CONFIG;
}) {
  const components = Array.isArray(ica.component_metadata)
    ? ica.component_metadata.filter(isRecord)
    : [];
  if (components.length === 0) {
    return null;
  }

  const selectedComponents = new Set(
    parseIntegerCsv(preprocessingConfig.ica.exclude_components),
  );
  const updateSelection = (component: number, checked: boolean) => {
    const next = new Set(selectedComponents);
    if (checked) {
      next.add(component);
    } else {
      next.delete(component);
    }
    onPreprocessingConfigChange({
      ...preprocessingConfig,
      ica: {
        ...preprocessingConfig.ica,
        enabled: true,
        exclude_components: Array.from(next)
          .sort((left, right) => left - right)
          .join(", "),
      },
    });
  };

  return (
    <div className="ica-review" data-testid="ica-review">
      <h4>ICA Components</h4>
      <div className="ica-review-table-wrap">
        <table className="ica-review-table">
          <thead>
            <tr>
              <th>Exclude</th>
              <th>Component</th>
              <th>EOG</th>
              <th>ECG</th>
              <th>Variance</th>
            </tr>
          </thead>
          <tbody>
            {components.map((component) => {
              const componentIndex = Number(component.component);
              const checked = selectedComponents.has(componentIndex);
              return (
                <tr key={String(component.component)}>
                  <td>
                    <input
                      checked={checked}
                      disabled={!Number.isInteger(componentIndex)}
                      onChange={(event) =>
                        updateSelection(componentIndex, event.target.checked)
                      }
                      type="checkbox"
                    />
                  </td>
                  <td>{stringValue(component.component)}</td>
                  <td>{formatMaybeNumber(component.eog_score)}</td>
                  <td>{formatMaybeNumber(component.ecg_score)}</td>
                  <td>{formatRatio(component.pca_explained_variance_ratio)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function EpochQc({ summary }: { summary: Record<string, unknown> }) {
  const conditionCounts = asRecord(summary.condition_counts);
  const totals = asRecord(conditionCounts.totals);
  const dropLog = asRecord(summary.drop_log);
  const dropSummary = asRecord(dropLog.summary);
  const outOfBounds = asRecord(summary.out_of_bounds);

  return (
    <div className="qc-section">
      <h3>Epoch QC</h3>
      <dl className="run-summary-grid">
        <QcMetric label="Candidates" value={stringValue(totals.candidate)} />
        <QcMetric label="Retained" value={stringValue(totals.retained)} />
        <QcMetric label="Dropped" value={stringValue(totals.dropped)} />
        <QcMetric label="Drop Entries" value={stringValue(dropLog.entry_count)} />
        <QcMetric
          label="Dropped Epochs"
          value={stringValue(dropSummary.dropped_epoch_count)}
        />
        <QcMetric
          label="Out Of Bounds"
          value={stringValue(outOfBounds.out_of_bounds)}
        />
      </dl>
      <ConditionQcList conditions={asRecord(conditionCounts.conditions)} />
    </div>
  );
}

function ErpQc({ summary }: { summary: Record<string, unknown> }) {
  const conditions = Array.isArray(summary.conditions) ? summary.conditions : [];
  return (
    <div className="qc-section">
      <h3>ERP QC</h3>
      <dl className="run-summary-grid">
        <QcMetric label="Conditions" value={stringValue(summary.condition_count)} />
        <QcMetric label="Plot Status" value={stringValue(summary.plot_status)} />
      </dl>
      <div className="qc-condition-list">
        {conditions
          .filter((condition): condition is Record<string, unknown> =>
            isRecord(condition),
          )
          .map((condition, index) => (
            <div className="qc-condition" key={`${condition.condition ?? index}`}>
              <strong>{stringValue(condition.condition)}</strong>
              <span>Nave {stringValue(condition.nave)}</span>
              <span>GFP {formatMaybeNumber(condition.gfp_peak)}</span>
              <span>Peak {formatMaybeNumber(condition.channel_peak)}</span>
              <span>{stringValue(condition.plot_status)}</span>
            </div>
          ))}
      </div>
    </div>
  );
}

function QcMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value || "-"}</dd>
    </div>
  );
}

function ConditionQcList({ conditions }: { conditions: Record<string, unknown> }) {
  const entries = Object.entries(conditions).filter(([, value]) => isRecord(value));
  if (entries.length === 0) {
    return null;
  }
  return (
    <div className="qc-condition-list">
      {entries.map(([condition, value]) => {
        const counts = asRecord(value);
        return (
          <div className="qc-condition" key={condition}>
            <strong>{condition}</strong>
            <span>Candidate {stringValue(counts.candidate)}</span>
            <span>Retained {stringValue(counts.retained)}</span>
            <span>Dropped {stringValue(counts.dropped)}</span>
          </div>
        );
      })}
    </div>
  );
}

function ComparisonSection({
  busyAction,
  comparisonConfig,
  completedErpRuns,
  onComparisonConfigChange,
  onStartComparisonSummary,
}: {
  busyAction: string | null;
  comparisonConfig: typeof DEFAULT_COMPARISON_CONFIG;
  completedErpRuns: ErpRun[];
  onComparisonConfigChange: (config: typeof DEFAULT_COMPARISON_CONFIG) => void;
  onStartComparisonSummary: () => void;
}) {
  const selectedRun =
    completedErpRuns.find((run) => run.run_id === comparisonConfig.erp_run_id) ??
    null;
  const conditionLabels = selectedRun ? getErpConditionLabels(selectedRun) : [];
  const disabled = !selectedRun || conditionLabels.length < 2;
  const configError = getComparisonConfigError(comparisonConfig);

  return (
    <section className="tool-section" aria-labelledby="comparison-config-title">
      <div className="tool-section-header">
        <span>07</span>
        <h3 id="comparison-config-title">Comparison Prep</h3>
        <small>{disabled ? "blocked" : "ready"}</small>
      </div>
      {completedErpRuns.length === 0 ? (
        <p className="muted">No completed ERP runs with two conditions yet.</p>
      ) : null}
      {configError ? <p className="error-text">{configError}</p> : null}
      <div className="epoch-grid">
        <label className="wide-field">
          <span>ERP Run</span>
          <select
            data-testid="comparison-erp-run-select"
            disabled={completedErpRuns.length === 0}
            onChange={(event) => {
              const nextRun = completedErpRuns.find(
                (run) => run.run_id === event.target.value,
              );
              const labels = nextRun ? getErpConditionLabels(nextRun) : [];
              onComparisonConfigChange({
                ...comparisonConfig,
                erp_run_id: event.target.value,
                condition_a: labels[0] ?? "",
                condition_b: labels[1] ?? "",
              });
            }}
            value={comparisonConfig.erp_run_id}
          >
            <option value="">Select completed ERP run</option>
            {completedErpRuns.map((run) => (
              <option key={run.run_id} value={run.run_id}>
                {run.run_id}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Condition A</span>
          <select
            data-testid="comparison-condition-a-select"
            disabled={disabled}
            onChange={(event) =>
              onComparisonConfigChange({
                ...comparisonConfig,
                condition_a: event.target.value,
              })
            }
            value={comparisonConfig.condition_a}
          >
            <option value="">Select</option>
            {conditionLabels.map((label) => (
              <option key={label} value={label}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Condition B</span>
          <select
            data-testid="comparison-condition-b-select"
            disabled={disabled}
            onChange={(event) =>
              onComparisonConfigChange({
                ...comparisonConfig,
                condition_b: event.target.value,
              })
            }
            value={comparisonConfig.condition_b}
          >
            <option value="">Select</option>
            {conditionLabels.map((label) => (
              <option key={label} value={label}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Window Start</span>
          <input
            data-testid="comparison-window-start-input"
            disabled={disabled}
            onChange={(event) =>
              onComparisonConfigChange({
                ...comparisonConfig,
                window_start_seconds: event.target.value,
              })
            }
            step="0.01"
            type="number"
            value={comparisonConfig.window_start_seconds}
          />
        </label>
        <label>
          <span>Window End</span>
          <input
            data-testid="comparison-window-end-input"
            disabled={disabled}
            onChange={(event) =>
              onComparisonConfigChange({
                ...comparisonConfig,
                window_end_seconds: event.target.value,
              })
            }
            step="0.01"
            type="number"
            value={comparisonConfig.window_end_seconds}
          />
        </label>
        <label className="checkbox-field">
          <input
            checked={comparisonConfig.use_gfp}
            disabled={disabled}
            onChange={(event) =>
              onComparisonConfigChange({
                ...comparisonConfig,
                use_gfp: event.target.checked,
                channel: event.target.checked ? "" : comparisonConfig.channel,
              })
            }
            type="checkbox"
          />
          <span>GFP</span>
        </label>
        <label>
          <span>Channel</span>
          <input
            data-testid="comparison-channel-input"
            disabled={disabled || comparisonConfig.use_gfp}
            onChange={(event) =>
              onComparisonConfigChange({
                ...comparisonConfig,
                channel: event.target.value,
              })
            }
            placeholder="Fp1"
            type="text"
            value={comparisonConfig.channel}
          />
        </label>
      </div>
      <button
        className="primary-button"
        data-testid="start-comparison-button"
        disabled={disabled || Boolean(configError) || busyAction === "comparison"}
        onClick={onStartComparisonSummary}
        type="button"
      >
        Generate Summary
      </button>
      {selectedRun ? <ComparisonSummary run={selectedRun} /> : null}
    </section>
  );
}

function ComparisonSummary({ run }: { run: ErpRun }) {
  const metadata = run.output_metadata;
  if (metadata.comparison_available !== true) {
    return null;
  }

  return (
    <dl className="run-summary-grid" data-testid="comparison-summary">
      <div>
        <dt>Condition A</dt>
        <dd>{String(metadata.comparison_condition_a ?? "-")}</dd>
      </div>
      <div>
        <dt>Condition B</dt>
        <dd>{String(metadata.comparison_condition_b ?? "-")}</dd>
      </div>
      <div>
        <dt>Mean A</dt>
        <dd>{formatUv(metadata.comparison_mean_a_uv)}</dd>
      </div>
      <div>
        <dt>Mean B</dt>
        <dd>{formatUv(metadata.comparison_mean_b_uv)}</dd>
      </div>
      <div>
        <dt>Difference</dt>
        <dd>{formatUv(metadata.comparison_difference_uv)}</dd>
      </div>
      <div>
        <dt>Target</dt>
        <dd>{String(metadata.comparison_target_type ?? "-")}</dd>
      </div>
      <div>
        <dt>Window</dt>
        <dd>
          {String(metadata.comparison_window_start_seconds ?? "-")} to{" "}
          {String(metadata.comparison_window_end_seconds ?? "-")}
        </dd>
      </div>
      <div>
        <dt>Statistics</dt>
        <dd>deferred</dd>
      </div>
    </dl>
  );
}

function EventPreviewTable({ preview }: { preview: EventPreview }) {
  const columns = preview.columns.slice(0, 6);

  return (
    <div className="preview-table-wrap">
      <div className="preview-summary">
        <strong>{preview.row_count}</strong>
        <span>rows / {preview.delimiter === "\t" ? "TSV" : "CSV"}</span>
      </div>
      <table className="preview-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {preview.preview_rows.slice(0, 5).map((row, index) => (
            <tr key={`${index}-${columns.join("-")}`}>
              {columns.map((column) => (
                <td key={column}>{row[column] ?? ""}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ValidationPanel({ report }: { report: ValidationReport }) {
  const hasErrors = report.errors.length > 0;
  const hasWarnings = report.warnings.length > 0;

  return (
    <div
      className={`validation-panel ${report.valid ? "valid" : "invalid"}`}
      data-testid="validation-panel"
    >
      <div className="validation-heading">
        <div>
          <strong>{report.valid ? "Valid" : "Invalid"}</strong>
          <p>
            {report.valid
              ? "Preprocessing is available once EEG recording and mapped events are present."
              : "Resolve blocking errors before preprocessing can start."}
          </p>
        </div>
        <span>
          {report.errors.length} errors / {report.warnings.length} warnings
        </span>
      </div>
      {report.valid ? (
        <p className="validation-ready" data-testid="validation-ready-message">
          Dataset is ready for preprocessing. Configure filters below and start a
          preprocessing run.
        </p>
      ) : null}
      <ValidationIssueSection
        emptyText="No blocking errors."
        issues={report.errors}
        severity="error"
        title="Errors"
      />
      <ValidationIssueSection
        emptyText="No warnings."
        issues={report.warnings}
        severity="warning"
        title="Warnings"
      />
      {!hasErrors && !hasWarnings ? (
        <p className="muted">All required validation checks passed.</p>
      ) : null}
    </div>
  );
}

function ValidationIssueSection({
  emptyText,
  issues,
  severity,
  title,
}: {
  emptyText: string;
  issues: ValidationIssue[];
  severity: ValidationIssue["severity"];
  title: string;
}) {
  return (
    <section
      className="validation-issue-section"
      data-testid={`validation-${severity}s`}
    >
      <div className="validation-section-heading">
        <h4>{title}</h4>
        <span>{issues.length}</span>
      </div>
      {issues.length === 0 ? (
        <p className="muted">{emptyText}</p>
      ) : (
        <ul className="issue-list">
          {issues.map((issue) => (
            <li
              data-severity={issue.severity}
              key={`${issue.severity}-${issue.code}-${issue.field ?? ""}`}
            >
              <div className="issue-meta">
                <span>{issue.severity}</span>
                <code>{issue.code}</code>
                <small>{issue.field ?? "dataset"}</small>
              </div>
              <strong>{issue.message}</strong>
              <p>{getValidationActionHint(issue)}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function StatusTile({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "idle" | "loading" | "error" | "ok" | "neutral";
}) {
  return (
    <div className={`status-tile status-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SampleList({
  samples,
  selectedSampleId,
  onSelect,
}: {
  samples: LoadState<SampleDataset[]>;
  selectedSampleId: string | null;
  onSelect: (sampleId: string) => void;
}) {
  if (samples.status === "loading" || samples.status === "idle") {
    return <p className="muted">Loading sample datasets...</p>;
  }

  if (samples.status === "error") {
    return <p className="error-text">{samples.error}</p>;
  }

  const sampleData = samples.data ?? [];

  if (sampleData.length === 0) {
    return <p className="muted">No sample EEG files were found.</p>;
  }

  return (
    <div className="sample-list">
      {sampleData.map((sample) => (
        <button
          className="sample-row"
          data-active={sample.id === selectedSampleId}
          key={sample.id}
          onClick={() => onSelect(sample.id)}
          type="button"
        >
          <span>
            <strong>{sample.id}</strong>
            <small>{sample.filename}</small>
          </span>
          <em>{sample.format.toUpperCase()}</em>
        </button>
      ))}
    </div>
  );
}

function MetadataView({
  metadata,
  selectedSample,
}: {
  metadata: LoadState<DatasetMetadata>;
  selectedSample: SampleDataset | null;
}) {
  if (!selectedSample) {
    return <p className="muted">Select a sample dataset to inspect metadata.</p>;
  }

  if (metadata.status === "loading" || metadata.status === "idle") {
    return <p className="muted">Loading metadata...</p>;
  }

  if (metadata.status === "error") {
    return <p className="error-text">{metadata.error}</p>;
  }

  const data = metadata.data;
  if (!data) {
    return <p className="muted">No metadata is available.</p>;
  }
  const channelDetails = data.channel_details ?? [];

  return (
    <div className="metadata-stack">
      <dl className="metadata-grid">
        <div>
          <dt>Dataset ID</dt>
          <dd>{data.id}</dd>
        </div>
        <div>
          <dt>Format</dt>
          <dd>{data.format.toUpperCase()}</dd>
        </div>
        <div>
          <dt>Channels</dt>
          <dd>{data.channels}</dd>
        </div>
        <div>
          <dt>Sampling Rate</dt>
          <dd>{data.sampling_rate} Hz</dd>
        </div>
        <div>
          <dt>Duration</dt>
          <dd>{data.duration_seconds.toFixed(1)} s</dd>
        </div>
        {data.line_frequency_hz !== null && data.line_frequency_hz !== undefined ? (
          <div>
            <dt>Line Frequency</dt>
            <dd>{data.line_frequency_hz} Hz</dd>
          </div>
        ) : null}
        {data.reference ? (
          <div>
            <dt>Reference</dt>
            <dd>{data.reference}</dd>
          </div>
        ) : null}
      </dl>
      {channelDetails.length > 0 ? (
        <div>
          <h3>Channel Details</h3>
          <div className="channel-detail-table-wrap">
            <table className="channel-detail-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Type</th>
                  <th>Units</th>
                  <th>Status</th>
                  <th>Status Detail</th>
                </tr>
              </thead>
              <tbody>
                {channelDetails.map((channel) => (
                  <tr key={channel.name}>
                    <td>{channel.name}</td>
                    <td>{channel.type ?? "-"}</td>
                    <td>{channel.units ?? "-"}</td>
                    <td>{channel.status ?? "-"}</td>
                    <td>{channel.status_description ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div>
          <h3>Channel Names</h3>
          <div className="channel-list">
            {data.channel_names.map((channelName) => (
              <span key={channelName}>{channelName}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function LoadMessage<T>({
  empty,
  state,
}: {
  empty: string;
  state: LoadState<T[]>;
}) {
  if (state.status === "loading" || state.status === "idle") {
    return <p className="muted">Loading...</p>;
  }
  if (state.status === "error") {
    return <p className="error-text">{state.error}</p>;
  }
  if ((state.data ?? []).length === 0) {
    return <p className="muted">{empty}</p>;
  }
  return null;
}

async function fetchJson<T>(path: string): Promise<T> {
  return requestJson<T>(path);
}

async function fetchOptionalJson<T>(path: string): Promise<T | null> {
  try {
    return await requestJson<T>(path);
  } catch (error: unknown) {
    if (error instanceof ApiRequestError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  return requestJson<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new ApiRequestError(
      response.status,
      detail || `${response.status} ${response.statusText}`,
    );
  }

  return response.json() as Promise<T>;
}

async function requestBlob(
  path: string,
): Promise<{ blob: Blob; filename: string | null }> {
  const response = await fetch(`${API_BASE_URL}${path}`);

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new ApiRequestError(
      response.status,
      detail || `${response.status} ${response.statusText}`,
    );
  }

  return {
    blob: await response.blob(),
    filename: parseContentDispositionFilename(
      response.headers.get("content-disposition"),
    ),
  };
}

function downloadBlob(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

function parseContentDispositionFilename(value: string | null): string | null {
  if (!value) {
    return null;
  }
  const utf8Match = value.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1].replace(/^"|"$/g, ""));
  }
  const filenameMatch = value.match(/filename="?([^";]+)"?/i);
  return filenameMatch?.[1] ?? null;
}

class ApiRequestError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
    if (Array.isArray(payload.detail)) {
      return payload.detail
        .map((item) =>
          typeof item === "object" && item !== null && "msg" in item
            ? String((item as { msg: unknown }).msg)
            : String(item),
        )
        .join(", ");
    }
  } catch {
    return "";
  }
  return "";
}

function getInitialMapping(
  columns: string[],
  defaultMapping: EventColumnMapping | null,
): Record<MappingKey, string> {
  const guessed = guessMapping(columns);
  if (!defaultMapping) {
    return guessed;
  }

  return MAPPING_FIELDS.reduce<Record<MappingKey, string>>((next, field) => {
    const defaultColumn = defaultMapping[field.key];
    next[field.key] =
      defaultColumn && columns.includes(defaultColumn)
        ? defaultColumn
        : guessed[field.key];
    return next;
  }, { ...EMPTY_MAPPING });
}

function mappingFromPreset(
  presetValue: EventMappingPreset,
  columns: string[],
): Record<MappingKey, string> {
  const preset = EVENT_MAPPING_PRESETS.find((item) => item.value === presetValue);
  if (!preset) {
    return { ...EMPTY_MAPPING };
  }

  return MAPPING_FIELDS.reduce<Record<MappingKey, string>>((next, field) => {
    const presetColumn = preset.mapping[field.key];
    next[field.key] =
      presetColumn && columns.includes(presetColumn) ? presetColumn : "";
    return next;
  }, { ...EMPTY_MAPPING });
}

function guessMapping(columns: string[]): Record<MappingKey, string> {
  return {
    onset_seconds: findColumn(columns, ["onset", "stim_onset", "time", "timestamp"]),
    duration_seconds: findColumn(columns, ["duration", "stim_duration"]),
    trial_type: findColumn(columns, ["trial_type", "condition", "trial"]),
    stimulus: findColumn(columns, ["stimulus", "stimulus_file", "stim"]),
    response: findColumn(columns, ["response", "key_resp.keys", "key"]),
    correct: findColumn(columns, ["correct", "key_resp.corr", "accuracy"]),
    reaction_time_seconds: findColumn(columns, ["rt", "key_resp.rt", "reaction_time"]),
  };
}

function findColumn(columns: string[], candidates: string[]): string {
  const normalized = new Map(
    columns.map((column) => [column.trim().toLowerCase(), column]),
  );
  for (const candidate of candidates) {
    const match = normalized.get(candidate.toLowerCase());
    if (match) {
      return match;
    }
  }
  return "";
}

function normalizeMappingPayload(mapping: Record<MappingKey, string>): EventColumnMapping {
  return MAPPING_FIELDS.reduce<EventColumnMapping>(
    (payload, field) => ({
      ...payload,
      [field.key]: mapping[field.key] || null,
    }),
    {
      onset_seconds: null,
      duration_seconds: null,
      trial_type: null,
      stimulus: null,
      response: null,
      correct: null,
      reaction_time_seconds: null,
    },
  );
}

function normalizeRowFilterPayload(
  filter: EventRowFilterForm,
): EventRowFilter | null {
  const include = parseRowFilterConditions(filter.include);
  const exclude = parseRowFilterConditions(filter.exclude);
  if (include.length === 0 && exclude.length === 0) {
    return null;
  }
  return { include, exclude };
}

function parseRowFilterConditions(value: string): EventRowFilterCondition[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => {
      const [column, ...rest] = item.split("=");
      return {
        column: column.trim(),
        equals: rest.length > 0 ? rest.join("=").trim() || null : null,
      };
    })
    .filter((condition) => condition.column);
}

function normalizePreprocessingConfig(
  config: typeof DEFAULT_PREPROCESSING_CONFIG,
): PreprocessingConfig {
  const detectionEnabled = config.bad_channel_detection.enabled;
  return {
    artifact_schema_version: 1,
    high_pass_hz: parseOptionalNumber(config.high_pass_hz),
    low_pass_hz: parseOptionalNumber(config.low_pass_hz),
    notch_hz: parseOptionalNumber(config.notch_hz),
    resample_hz: parseOptionalNumber(config.resample_hz),
    reference: config.reference || null,
    manual_bad_channels: config.manual_bad_channels,
    bad_channel_interpolation: {
      enabled:
        config.bad_channel_interpolation.enabled &&
        config.manual_bad_channels.length > 0,
      reset_bads: config.bad_channel_interpolation.reset_bads,
    },
    bad_channel_detection: {
      enabled: detectionEnabled,
      method: detectionEnabled
        ? (config.bad_channel_detection.method as BadChannelDetectionMethod)
        : "none",
      minimum_correlation: detectionEnabled
        ? parseOptionalNumber(config.bad_channel_detection.minimum_correlation)
        : null,
      zscore_threshold: detectionEnabled
        ? parseOptionalNumber(config.bad_channel_detection.zscore_threshold)
        : null,
    },
    artifact_handling: {
      eog_enabled: config.artifact_handling.eog_enabled,
      ecg_enabled: config.artifact_handling.ecg_enabled,
      eog_channels: parseOptionalCsv(config.artifact_handling.eog_channels) ?? [],
      ecg_channels: parseOptionalCsv(config.artifact_handling.ecg_channels) ?? [],
      create_annotations: false,
    },
    ica: {
      enabled: config.ica.enabled,
      method: config.ica.method as IcaMethod,
      n_components: config.ica.enabled
        ? parseOptionalNumber(config.ica.n_components)
        : null,
      random_state: parseOptionalNumber(config.ica.random_state) ?? 97,
      max_iter: parseMaxIter(config.ica.max_iter),
      exclude_components: config.ica.enabled
        ? parseIntegerCsv(config.ica.exclude_components)
        : [],
      eog_channels: parseOptionalCsv(config.ica.eog_channels) ?? [],
      ecg_channels: parseOptionalCsv(config.ica.ecg_channels) ?? [],
    },
  };
}

function normalizeEpochConfig(config: typeof DEFAULT_EPOCH_CONFIG): EpochConfig {
  return {
    preprocessing_run_id: config.preprocessing_run_id,
    condition_field: config.condition_field,
    tmin_seconds: Number(config.tmin_seconds),
    tmax_seconds: Number(config.tmax_seconds),
    baseline_start_seconds: config.baseline_enabled
      ? parseOptionalNumber(config.baseline_start_seconds)
      : null,
    baseline_end_seconds: config.baseline_enabled
      ? parseOptionalNumber(config.baseline_end_seconds)
      : null,
    reject_eeg_uv: parseOptionalNumber(config.reject_eeg_uv),
  };
}

function normalizeErpConfig(config: typeof DEFAULT_ERP_CONFIG): ErpConfig {
  return {
    epoch_run_id: config.epoch_run_id,
    conditions: parseOptionalCsv(config.conditions),
    picks: parseOptionalCsv(config.picks),
    method: config.method,
    plot_mode: config.plot_mode,
    plot_channel:
      config.plot_mode === "channel" && config.plot_channel.trim()
        ? config.plot_channel.trim()
        : null,
  };
}

function preprocessingTemplateToForm(
  config: PreprocessingConfig,
): typeof DEFAULT_PREPROCESSING_CONFIG {
  return {
    high_pass_hz: optionalNumberToForm(config.high_pass_hz),
    low_pass_hz: optionalNumberToForm(config.low_pass_hz),
    notch_hz: optionalNumberToForm(config.notch_hz),
    resample_hz: optionalNumberToForm(config.resample_hz),
    reference: config.reference ?? "",
    manual_bad_channels: config.manual_bad_channels,
    bad_channel_interpolation: {
      enabled: config.bad_channel_interpolation.enabled,
      reset_bads: config.bad_channel_interpolation.reset_bads,
    },
    artifact_handling: {
      eog_enabled: config.artifact_handling.eog_enabled,
      ecg_enabled: config.artifact_handling.ecg_enabled,
      eog_channels: csvToForm(config.artifact_handling.eog_channels),
      ecg_channels: csvToForm(config.artifact_handling.ecg_channels),
      create_annotations: config.artifact_handling.create_annotations,
    },
    bad_channel_detection: {
      enabled: config.bad_channel_detection.enabled,
      method:
        config.bad_channel_detection.method === "none"
          ? "deviation"
          : config.bad_channel_detection.method,
      zscore_threshold: optionalNumberToForm(
        config.bad_channel_detection.zscore_threshold,
      ),
      minimum_correlation: optionalNumberToForm(
        config.bad_channel_detection.minimum_correlation,
      ),
    },
    ica: {
      enabled: config.ica.enabled,
      method: config.ica.method,
      n_components: optionalNumberToForm(config.ica.n_components),
      random_state: String(config.ica.random_state),
      max_iter: String(config.ica.max_iter),
      exclude_components: config.ica.exclude_components.join(", "),
      eog_channels: csvToForm(config.ica.eog_channels),
      ecg_channels: csvToForm(config.ica.ecg_channels),
    },
  };
}

function epochTemplateToForm(
  config: WorkflowTemplateEpochConfig,
  preprocessingRunId: string,
): typeof DEFAULT_EPOCH_CONFIG {
  const baselineEnabled =
    config.baseline_start_seconds !== null || config.baseline_end_seconds !== null;
  return {
    preprocessing_run_id: preprocessingRunId,
    condition_field: config.condition_field,
    tmin_seconds: String(config.tmin_seconds),
    tmax_seconds: String(config.tmax_seconds),
    baseline_enabled: baselineEnabled,
    baseline_start_seconds: baselineEnabled
      ? optionalNumberToForm(config.baseline_start_seconds)
      : "",
    baseline_end_seconds: baselineEnabled
      ? optionalNumberToForm(config.baseline_end_seconds)
      : "",
    reject_eeg_uv: optionalNumberToForm(config.reject_eeg_uv),
  };
}

function erpTemplateToForm(
  config: WorkflowTemplateErpConfig,
  epochRunId: string,
): typeof DEFAULT_ERP_CONFIG {
  return {
    epoch_run_id: epochRunId,
    conditions: csvToForm(config.conditions ?? []),
    picks: csvToForm(config.picks ?? []),
    method: config.method,
    plot_mode: config.plot_mode,
    plot_channel: config.plot_channel ?? "",
  };
}

function normalizeComparisonConfig(
  config: typeof DEFAULT_COMPARISON_CONFIG,
): ComparisonConfig {
  return {
    condition_a: config.condition_a,
    condition_b: config.condition_b,
    channel:
      !config.use_gfp && config.channel.trim() ? config.channel.trim() : null,
    use_gfp: config.use_gfp,
    window_start_seconds: Number(config.window_start_seconds),
    window_end_seconds: Number(config.window_end_seconds),
    metric: config.metric,
  };
}

function getPreprocessingConfigError(
  config: typeof DEFAULT_PREPROCESSING_CONFIG,
): string | null {
  const highPass = parseOptionalNumber(config.high_pass_hz);
  const lowPass = parseOptionalNumber(config.low_pass_hz);
  const notch = parseOptionalNumber(config.notch_hz);
  const resample = parseOptionalNumber(config.resample_hz);
  const zscore = parseOptionalNumber(
    config.bad_channel_detection.zscore_threshold,
  );
  const minimumCorrelation = parseOptionalNumber(
    config.bad_channel_detection.minimum_correlation,
  );
  const icaComponents = parseOptionalNumber(config.ica.n_components);
  const icaRandomState = parseOptionalNumber(config.ica.random_state);
  const icaMaxIter = parseMaxIter(config.ica.max_iter);

  for (const [label, value] of [
    ["High-pass", highPass],
    ["Low-pass", lowPass],
    ["Notch", notch],
    ["Resample", resample],
  ] as const) {
    if (value !== null && (!Number.isFinite(value) || value < 0)) {
      return `${label} must be a non-negative number.`;
    }
  }

  if (lowPass !== null && lowPass <= 0) {
    return "Low-pass must be greater than 0 Hz.";
  }

  if (notch !== null && notch <= 0) {
    return "Notch must be greater than 0 Hz.";
  }

  if (resample !== null && resample <= 0) {
    return "Resample must be greater than 0 Hz.";
  }

  if (highPass !== null && lowPass !== null && highPass >= lowPass) {
    return "High-pass must be lower than low-pass.";
  }

  if (config.bad_channel_detection.enabled) {
    if (
      !["flat", "deviation", "ransac"].includes(
        config.bad_channel_detection.method,
      )
    ) {
      return "Select a supported bad-channel detection method.";
    }
    if (zscore !== null && (!Number.isFinite(zscore) || zscore <= 0)) {
      return "Bad-channel z-score threshold must be greater than 0.";
    }
    if (
      minimumCorrelation !== null &&
      (!Number.isFinite(minimumCorrelation) ||
        minimumCorrelation < 0 ||
        minimumCorrelation > 1)
    ) {
      return "Bad-channel minimum correlation must be between 0 and 1.";
    }
  }

  if (config.ica.enabled) {
    if (!["fastica", "infomax", "picard"].includes(config.ica.method)) {
      return "Select a supported ICA method.";
    }
    if (
      icaComponents !== null &&
      (!Number.isFinite(icaComponents) || icaComponents <= 0)
    ) {
      return "ICA components must be greater than 0.";
    }
    if (
      icaComponents !== null &&
      !Number.isInteger(icaComponents) &&
      icaComponents > 1
    ) {
      return "ICA fractional components must be at most 1.";
    }
    if (
      icaRandomState === null ||
      !Number.isInteger(icaRandomState)
    ) {
      return "ICA random state must be an integer.";
    }
    if (icaMaxIter !== "auto" && (!Number.isInteger(icaMaxIter) || icaMaxIter <= 0)) {
      return "ICA max iterations must be auto or a positive integer.";
    }
    const rawExclusions = config.ica.exclude_components
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    if (
      rawExclusions.some(
        (item) => !Number.isInteger(Number(item)) || Number(item) < 0,
      )
    ) {
      return "ICA excluded components must be non-negative integers.";
    }
  }

  return null;
}

function getEpochConfigError(config: typeof DEFAULT_EPOCH_CONFIG): string | null {
  if (!config.preprocessing_run_id) {
    return "Select a completed preprocessing run.";
  }
  if (
    !CONDITION_FIELDS.includes(
      config.condition_field as (typeof CONDITION_FIELDS)[number],
    )
  ) {
    return "Select a supported condition field.";
  }

  const tmin = parseOptionalNumber(config.tmin_seconds);
  const tmax = parseOptionalNumber(config.tmax_seconds);
  const baselineStart = config.baseline_enabled
    ? parseOptionalNumber(config.baseline_start_seconds)
    : null;
  const baselineEnd = config.baseline_enabled
    ? parseOptionalNumber(config.baseline_end_seconds)
    : null;
  const reject = parseOptionalNumber(config.reject_eeg_uv);

  if (tmin === null || !Number.isFinite(tmin)) {
    return "tmin must be a number.";
  }
  if (tmax === null || !Number.isFinite(tmax)) {
    return "tmax must be a number.";
  }
  if (tmin >= tmax) {
    return "tmin must be lower than tmax.";
  }
  if (tmax <= 0) {
    return "tmax must be greater than 0.";
  }

  if (config.baseline_enabled) {
    if (baselineStart === null || baselineEnd === null) {
      return "Baseline start and end are required when baseline is enabled.";
    }
    if (!Number.isFinite(baselineStart) || !Number.isFinite(baselineEnd)) {
      return "Baseline values must be numbers.";
    }
    if (baselineStart > baselineEnd) {
      return "Baseline start must be lower than or equal to baseline end.";
    }
    if (baselineStart < tmin || baselineEnd > tmax) {
      return "Baseline must be inside the epoch window.";
    }
  }

  if (reject !== null && (!Number.isFinite(reject) || reject <= 0)) {
    return "Reject EEG must be greater than 0 uV.";
  }

  return null;
}

function getErpConfigError(config: typeof DEFAULT_ERP_CONFIG): string | null {
  if (!config.epoch_run_id) {
    return "Select a completed epoch run.";
  }
  if (config.method !== "mean") {
    return "ERP method must be mean.";
  }
  if (!["gfp", "channel"].includes(config.plot_mode)) {
    return "Select GFP or channel plot mode.";
  }
  if (config.plot_mode === "channel" && !config.plot_channel.trim()) {
    return "Enter a channel for channel plot mode.";
  }
  if (parseOptionalCsv(config.conditions)?.length === 0) {
    return "Conditions must not be empty.";
  }
  if (parseOptionalCsv(config.picks)?.length === 0) {
    return "Picks must not be empty.";
  }
  return null;
}

function getComparisonConfigError(
  config: typeof DEFAULT_COMPARISON_CONFIG,
): string | null {
  if (!config.erp_run_id) {
    return "Select a completed ERP run.";
  }
  if (!config.condition_a || !config.condition_b) {
    return "Select two conditions.";
  }
  if (config.condition_a === config.condition_b) {
    return "Comparison conditions must be different.";
  }
  if (config.metric !== "mean_amplitude_uv") {
    return "Comparison metric must be mean amplitude.";
  }
  const windowStart = parseOptionalNumber(config.window_start_seconds);
  const windowEnd = parseOptionalNumber(config.window_end_seconds);
  if (windowStart === null || windowEnd === null) {
    return "Comparison window values are required.";
  }
  if (!Number.isFinite(windowStart) || !Number.isFinite(windowEnd)) {
    return "Comparison window values must be numbers.";
  }
  if (windowStart >= windowEnd) {
    return "Window start must be lower than window end.";
  }
  if (config.use_gfp && config.channel.trim()) {
    return "Use either GFP or a channel.";
  }
  if (!config.use_gfp && !config.channel.trim()) {
    return "Enter a channel or enable GFP.";
  }
  return null;
}

function parseOptionalNumber(value: string): number | null {
  if (!value.trim()) {
    return null;
  }
  return Number(value);
}

function parseOptionalCsv(value: string): string[] | null {
  if (!value.trim()) {
    return null;
  }
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function optionalNumberToForm(value: number | null): string {
  return value === null ? "" : String(value);
}

function csvToForm(values: string[]): string {
  return values.join(", ");
}

function parseIntegerCsv(value: string): number[] {
  if (!value.trim()) {
    return [];
  }
  return value
    .split(",")
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isFinite(item));
}

function parseMaxIter(value: string): number | "auto" {
  const trimmed = value.trim().toLowerCase();
  if (!trimmed || trimmed === "auto") {
    return "auto";
  }
  return Number(trimmed);
}

function formatRunMetadata(metadata: Record<string, MetadataValue>): string {
  const samplingRate =
    metadata.output_sampling_rate_hz ?? metadata.sampling_rate_hz;
  const duration =
    metadata.output_duration_seconds ?? metadata.duration_seconds;
  const channels =
    metadata.output_channel_count ?? metadata.channel_count;
  const parts = [
    typeof samplingRate === "number" ? `${samplingRate.toFixed(1)} Hz` : null,
    typeof channels === "number" ? `${channels} ch` : null,
    typeof duration === "number" ? `${duration.toFixed(1)} s` : null,
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(" / ") : "Metadata pending";
}

function formatEpochMetadata(metadata: Record<string, MetadataValue>): string {
  const conditionCount = metadata.condition_count;
  const epochCount = metadata.epoch_count;
  const droppedCount = metadata.dropped_epoch_count;
  const parts = [
    typeof conditionCount === "number" ? `${conditionCount} cond` : null,
    typeof epochCount === "number" ? `${epochCount} epochs` : null,
    typeof droppedCount === "number" ? `${droppedCount} dropped` : null,
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(" / ") : "Metadata pending";
}

function formatErpMetadata(metadata: Record<string, MetadataValue>): string {
  const conditionCount = metadata.condition_count;
  const evokedCount = metadata.evoked_count;
  const plotCount = metadata.plot_count;
  const plotStatus = metadata.plot_status;
  const parts = [
    typeof conditionCount === "number" ? `${conditionCount} cond` : null,
    typeof evokedCount === "number" ? `${evokedCount} evoked` : null,
    typeof plotCount === "number" ? `${plotCount} plots` : null,
    typeof plotStatus === "string" ? plotStatus : null,
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(" / ") : "Metadata pending";
}

function formatTemplateWorkflowSummary(workflow: WorkflowTemplateWorkflow): string {
  const parts = [
    workflow.preprocessing ? "preprocessing" : null,
    workflow.epoch ? "epoch" : null,
    workflow.erp ? "ERP" : null,
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(" + ") : "empty workflow";
}

function formatTemplatePolicySummary(policy: WorkflowTemplateFieldPolicy): string {
  const parts = [
    policy.excluded_fields.length > 0
      ? `${policy.excluded_fields.length} excluded`
      : null,
    policy.review_required_fields.length > 0
      ? `${policy.review_required_fields.length} review-needed`
      : null,
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(" / ") : "";
}

function isActiveBatchStatus(status: string): boolean {
  return ["pending", "running", "cancelling"].includes(status);
}

function batchItemMatchesFilter(
  item: BatchSubjectRunPlan,
  filter: BatchItemFilter,
): boolean {
  if (filter === "all") {
    return true;
  }
  if (filter === "pending") {
    return ["pending", "running", "cancelling"].includes(item.status);
  }
  if (filter === "failed") {
    return ["failed", "cancelled"].includes(item.status);
  }
  return item.status === filter;
}

function summarizeBatchItems(items: BatchSubjectRunPlan[]): string {
  const completed = items.filter((item) => item.status === "completed").length;
  const failed = items.filter((item) => item.status === "failed").length;
  const pending = items.filter((item) =>
    ["pending", "running", "cancelling"].includes(item.status),
  ).length;
  return `${completed} completed / ${failed} failed / ${pending} pending`;
}

function formatBatchCurrentStep(
  item: BatchSubjectRunPlan,
  preprocessingRun: PreprocessingRun | null,
): string {
  if (preprocessingRun && ["pending", "running", "cancelling"].includes(preprocessingRun.status)) {
    return `preprocessing / ${preprocessingRun.status}`;
  }
  if (item.status === "completed") {
    return "completed";
  }
  if (item.status === "failed") {
    return "failed";
  }
  if (item.status === "cancelled") {
    return "cancelled";
  }
  return item.planned_steps[0] ?? "pending";
}

function formatBatchMessages(
  itemMessages: string[],
  runMessages: string[] | undefined,
): string {
  const messages = [...itemMessages, ...(runMessages ?? [])].filter(Boolean);
  return messages.length > 0 ? messages.join(" ") : "-";
}

function operationStatus(value: unknown): string {
  return stringValue(asRecord(value).status);
}

function asRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  if (typeof value === "boolean") {
    return value ? "yes" : "no";
  }
  return String(value);
}

function formatMaybeNumber(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(2)
    : stringValue(value);
}

function formatSignedNumber(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "-";
  }
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(2)}`;
}

function formatRatio(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "-";
  }
  return `${value.toFixed(2)}x`;
}

function getErpConditionLabels(run: ErpRun): string[] {
  const labels = run.output_metadata.condition_labels;
  if (typeof labels !== "string") {
    return [];
  }
  return labels
    .split(",")
    .map((label) => label.trim())
    .filter(Boolean);
}

function formatUv(value: MetadataValue): string {
  if (typeof value !== "number") {
    return "-";
  }
  return `${value.toFixed(3)} uV`;
}

function artifactUrl(runId: string, filename: string): string {
  return `${API_BASE_URL}/artifacts/${encodeURIComponent(runId)}/${encodeURIComponent(
    filename,
  )}`;
}

function isErpExportReady(run: ErpRun): boolean {
  return (
    run.status === "completed" &&
    typeof run.output_metadata.artifact_manifest_path === "string" &&
    run.output_metadata.artifact_manifest_path.length > 0
  );
}

function getErpExportStatus(run: ErpRun): string {
  if (run.status !== "completed") {
    return `Export unavailable: run is ${run.status}.`;
  }

  if (
    typeof run.output_metadata.artifact_manifest_path !== "string" ||
    run.output_metadata.artifact_manifest_path.length === 0
  ) {
    return "Export unavailable: artifact manifest is not ready.";
  }

  if (
    typeof run.output_metadata.analysis_report_url === "string" &&
    run.output_metadata.analysis_report_url.length > 0
  ) {
    return "Export ready: report, manifest, plots, provenance, diagnostics, and artifacts.";
  }

  return "Export ready: report will be generated before ZIP download.";
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed";
}

function getHealthLabel(health: LoadState<HealthResponse>): string {
  if (health.status === "success") {
    return `${health.data.service}: ${health.data.status}`;
  }

  if (health.status === "error") {
    return "Unavailable";
  }

  return "Checking";
}

function getProjectCountLabel(projects: LoadState<Project[]>): string {
  if (projects.status === "success") {
    return `${projects.data.length} registered`;
  }

  if (projects.status === "error") {
    return "Unavailable";
  }

  return "Loading";
}

function getInitialTheme(): ThemeMode {
  const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
  if (storedTheme === "dark" || storedTheme === "light") {
    return storedTheme;
  }

  return window.matchMedia("(prefers-color-scheme: light)").matches
    ? "light"
    : "dark";
}

function getInitialActiveDatasetId(): string {
  return window.localStorage.getItem(ACTIVE_DATASET_STORAGE_KEY) ?? "";
}

function getInitialWorkspaceMode(): WorkspaceMode {
  const storedMode = window.localStorage.getItem(WORKSPACE_MODE_STORAGE_KEY);
  return storedMode === "analysis" ? "analysis" : "setup";
}

function hasSupportedExtension(file: File, extensions: string[]): boolean {
  const filename = file.name.toLowerCase();
  return extensions.some((extension) => filename.endsWith(extension));
}

function getUploadStatus({
  disabled,
  selectedFilename,
  uploadedFilename,
  uploadedId,
  emptyText,
  uploadedText,
}: {
  disabled: boolean;
  selectedFilename: string | null;
  uploadedFilename: string | null;
  uploadedId: string | null;
  emptyText: string;
  uploadedText: string;
}) {
  if (disabled) {
    return {
      state: "waiting",
      label: "Waiting",
      detail: "Create or select a dataset before uploading.",
    };
  }

  if (selectedFilename) {
    return {
      state: "ready",
      label: "Ready",
      detail: `Selected: ${selectedFilename}`,
    };
  }

  if (uploadedFilename) {
    return {
      state: "uploaded",
      label: "Uploaded",
      detail: `${uploadedText}: ${uploadedFilename}`,
    };
  }

  if (uploadedId) {
    return {
      state: "uploaded",
      label: "Uploaded",
      detail: uploadedText,
    };
  }

  return {
    state: "waiting",
    label: "Required",
    detail: emptyText,
  };
}

function getValidationActionHint(issue: ValidationIssue): string {
  const actionByCode: Record<string, string> = {
    recording_missing:
      "Upload a supported EEG recording, then run validation again.",
    event_log_missing:
      "Upload a CSV or TSV event log, save the event mapping, then revalidate.",
    participant_label_missing:
      "Add a participant label in Setup so exports can identify this dataset.",
    session_label_missing:
      "Add a session label in Setup if the study has repeated sessions.",
    sampling_rate_invalid:
      "Check that the EEG file is readable and contains valid sampling metadata.",
    duration_invalid:
      "Check the EEG recording duration before continuing with preprocessing.",
    channels_missing:
      "Use an EEG recording with channel names and at least one valid channel.",
    event_log_empty:
      "Review event mapping and row filters so at least one event is normalized.",
    event_onset_out_of_range:
      "Align event onset units/timing with the EEG recording duration.",
    event_duration_missing:
      "Continue if fixed epoch windows are intended, or map a duration column.",
    event_response_missing:
      "Continue if response analysis is not required, or map a response column.",
    event_correct_missing:
      "Continue if accuracy is not needed, or map a correct/accuracy column.",
    event_reaction_time_missing:
      "Continue if reaction-time analysis is not needed, or map an RT column.",
  };

  if (actionByCode[issue.code]) {
    return `Next action: ${actionByCode[issue.code]}`;
  }

  if (issue.severity === "error") {
    return "Next action: Fix this blocking issue and run validation again.";
  }

  return "Next action: Review whether this warning affects the analysis plan.";
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
