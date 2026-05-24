import React, { useEffect, useMemo, useState } from "react";
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
};

type EventLogResponse = {
  event_log_id: string;
  dataset_id: string;
  file_id: string;
  mapping: EventColumnMapping;
  row_count: number;
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
  high_pass_hz: number | null;
  low_pass_hz: number | null;
  notch_hz: number | null;
  resample_hz: number | null;
  reference: string | null;
};

type PreprocessingRun = {
  run_id: string;
  dataset_id: string;
  config: PreprocessingConfig;
  status: string;
  started_at_utc: string | null;
  finished_at_utc: string | null;
  cancel_requested_at_utc: string | null;
  output_path: string | null;
  output_metadata: Record<string, MetadataValue>;
  warnings: string[];
  errors: string[];
};

type PreprocessingRunsResponse = {
  runs: PreprocessingRun[];
};

type MetadataValue = string | number | boolean | null;

type NoticeState = {
  tone: "ok" | "error" | "neutral";
  message: string;
} | null;

type MappingKey = keyof EventColumnMapping;

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

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

const DEFAULT_PREPROCESSING_CONFIG = {
  high_pass_hz: "1",
  low_pass_hz: "40",
  notch_hz: "",
  resample_hz: "",
  reference: "average",
};

function App() {
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
  const [activeDatasetId, setActiveDatasetId] = useState("");
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
  const [eventPreview, setEventPreview] = useState<EventPreview | null>(null);
  const [mapping, setMapping] = useState<Record<MappingKey, string>>(EMPTY_MAPPING);
  const [eventLog, setEventLog] = useState<EventLogResponse | null>(null);
  const [validation, setValidation] = useState<ValidationReport | null>(null);
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
  const [notice, setNotice] = useState<NoticeState>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);

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

  useEffect(() => {
    void refreshWorkspace();
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
      setPreprocessingRuns({ status: "idle", data: null, error: null });
      return;
    }

    void refreshPreprocessingRuns(activeDatasetId);
  }, [activeDatasetId]);

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

  async function refreshWorkspace() {
    setNotice(null);
    setHealth({ status: "loading", data: null, error: null });
    setSamples({ status: "loading", data: null, error: null });
    setProjects({ status: "loading", data: null, error: null });
    setDatasets({ status: "loading", data: null, error: null });

    const [healthResult, samplesResult, projectsResult, datasetsResult] =
      await Promise.allSettled([
        fetchJson<HealthResponse>("/health"),
        fetchJson<SampleDatasetsResponse>("/datasets/samples"),
        fetchJson<ProjectsResponse>("/projects"),
        fetchJson<DatasetsResponse>("/datasets"),
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
      setValidation(null);
      setPreprocessingRuns({ status: "success", data: [], error: null });
      await refreshDatasets();
      setNotice({ tone: "ok", message: "Dataset created." });
    });
  }

  async function uploadEegFile() {
    if (!activeDatasetId || !eegFile) {
      setNotice({ tone: "error", message: "Select a dataset and EEG file." });
      return;
    }

    await runAction("eeg-upload", async () => {
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
      updateDatasetInState(response.dataset);
      setValidation(null);
      setNotice({ tone: "ok", message: "EEG file uploaded." });
    });
  }

  async function uploadEventFile() {
    if (!activeDatasetId || !eventFile) {
      setNotice({ tone: "error", message: "Select a dataset and event file." });
      return;
    }

    await runAction("event-upload", async () => {
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
      setEventPreview(response.preview);
      setEventLog(null);
      setValidation(null);
      setMapping(
        getInitialMapping(
          response.preview.columns,
          selectedExperiment?.default_event_mapping ?? null,
        ),
      );
      updateDatasetInState(response.dataset);
      setNotice({ tone: "ok", message: "Event log uploaded." });
    });
  }

  async function submitEventMapping() {
    if (!activeDatasetId) {
      setNotice({ tone: "error", message: "Select a dataset first." });
      return;
    }
    if (!mapping.onset_seconds) {
      setNotice({ tone: "error", message: "Map an onset column first." });
      return;
    }

    await runAction("event-mapping", async () => {
      const eventLogResponse = await postJson<EventLogResponse>(
        `/datasets/${encodeURIComponent(activeDatasetId)}/events/mapping`,
        {
          mapping: normalizeMappingPayload(mapping),
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
    } catch (error: unknown) {
      setPreprocessingRuns({
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

  const activeDatasetCount = datasets.data?.length ?? 0;

  return (
    <main className="shell">
      <section className="workspace" aria-labelledby="workspace-title">
        <header className="workspace-header">
          <div>
            <p className="eyebrow">NeuroWeave</p>
            <h1 id="workspace-title">EEG ingestion workspace</h1>
          </div>
          <button className="primary-button" type="button" onClick={refreshWorkspace}>
            Refresh
          </button>
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

        <div className="ingest-grid">
          <aside className="panel setup-panel" aria-labelledby="setup-title">
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
          </aside>

          <section className="workflow-stack">
            <section className="panel" aria-labelledby="datasets-title">
              <div className="panel-header">
                <div>
                  <h2 id="datasets-title">Datasets</h2>
                  {selectedProject ? (
                    <p className="subtle">
                      {selectedProject.name}
                      {selectedExperiment ? ` / ${selectedExperiment.name}` : ""}
                    </p>
                  ) : null}
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
                  setValidation(null);
                }}
                selectedExperimentId={selectedExperimentId}
                selectedProjectId={selectedProjectId}
              />
            </section>

            <section className="panel" aria-labelledby="intake-title">
              <div className="panel-header">
                <div>
                  <h2 id="intake-title">Dataset Intake</h2>
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
                ) : null}
              </div>
              <IntakeSection
                activeDataset={activeDataset}
                busyAction={busyAction}
                eegFile={eegFile}
                eventFile={eventFile}
                eventLog={eventLog}
                eventPreview={eventPreview}
                mapping={mapping}
                onBeginPreprocessing={beginPreprocessingHandoff}
                onEegFileChange={setEegFile}
                onEventFileChange={setEventFile}
                onMappingChange={setMapping}
                onPreprocessingConfigChange={setPreprocessingConfig}
                onCancelPreprocessingRun={cancelPreprocessingRun}
                onSubmitEventMapping={submitEventMapping}
                onUploadEeg={uploadEegFile}
                onUploadEvent={uploadEventFile}
                onValidate={validateDataset}
                preprocessingConfig={preprocessingConfig}
                preprocessingRuns={preprocessingRuns}
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
          </section>
        </div>
      </section>
    </main>
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
  eventPreview,
  mapping,
  onBeginPreprocessing,
  onEegFileChange,
  onEventFileChange,
  onMappingChange,
  onPreprocessingConfigChange,
  onCancelPreprocessingRun,
  onSubmitEventMapping,
  onUploadEeg,
  onUploadEvent,
  onValidate,
  preprocessingConfig,
  preprocessingRuns,
  validation,
}: {
  activeDataset: Dataset | null;
  busyAction: string | null;
  eegFile: File | null;
  eventFile: File | null;
  eventLog: EventLogResponse | null;
  eventPreview: EventPreview | null;
  mapping: Record<MappingKey, string>;
  onBeginPreprocessing: () => void;
  onEegFileChange: (file: File | null) => void;
  onEventFileChange: (file: File | null) => void;
  onMappingChange: (mapping: Record<MappingKey, string>) => void;
  onPreprocessingConfigChange: (
    config: typeof DEFAULT_PREPROCESSING_CONFIG,
  ) => void;
  onCancelPreprocessingRun: (runId: string) => void;
  onSubmitEventMapping: () => void;
  onUploadEeg: () => void;
  onUploadEvent: () => void;
  onValidate: () => void;
  preprocessingConfig: typeof DEFAULT_PREPROCESSING_CONFIG;
  preprocessingRuns: LoadState<PreprocessingRun[]>;
  validation: ValidationReport | null;
}) {
  const disabled = !activeDataset;
  const canContinue = validation?.valid === true || activeDataset?.status === "valid";
  const configError = getPreprocessingConfigError(preprocessingConfig);

  return (
    <div className="intake-stack">
      <div className="upload-grid">
        <div className="upload-group">
          <h3>EEG Recording</h3>
          <input
            data-testid="eeg-file-input"
            disabled={disabled}
            onChange={(event) => onEegFileChange(event.target.files?.[0] ?? null)}
            type="file"
          />
          <button
            className="secondary-button"
            data-testid="upload-eeg-button"
            disabled={disabled || !eegFile || busyAction === "eeg-upload"}
            onClick={onUploadEeg}
            type="button"
          >
            Upload EEG
          </button>
        </div>
        <div className="upload-group">
          <h3>Event Log</h3>
          <input
            accept=".csv,.tsv,text/csv,text/tab-separated-values"
            data-testid="event-file-input"
            disabled={disabled}
            onChange={(event) => onEventFileChange(event.target.files?.[0] ?? null)}
            type="file"
          />
          <button
            className="secondary-button"
            data-testid="upload-events-button"
            disabled={disabled || !eventFile || busyAction === "event-upload"}
            onClick={onUploadEvent}
            type="button"
          >
            Upload Events
          </button>
        </div>
      </div>

      {eventPreview ? (
        <div className="mapping-layout">
          <div>
            <h3>Column Mapping</h3>
            <div className="mapping-grid">
              {MAPPING_FIELDS.map((field) => (
                <label key={field.key}>
                  <span>
                    {field.label}
                    {field.required ? " *" : ""}
                  </span>
                  <select
                    data-testid={`mapping-${field.key}-select`}
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
            <button
              className="primary-button"
              data-testid="save-mapping-button"
              disabled={!mapping.onset_seconds || busyAction === "event-mapping"}
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
          <span className="muted">{eventLog.events.length} normalized events</span>
        ) : (
          <span className="muted">No mapped event log yet</span>
        )}
      </div>

      {validation ? <ValidationPanel report={validation} /> : null}

      <div className="preprocessing-panel">
        <div>
          <h3>Preprocessing Handoff</h3>
          <p className="muted">
            {canContinue
              ? "Configure filters and create a run for this valid dataset."
              : "A dataset must pass validation before preprocessing can start."}
          </p>
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
          onCancel={onCancelPreprocessingRun}
          runs={preprocessingRuns}
        />
      </div>
    </div>
  );
}

function PreprocessingRunList({
  onCancel,
  runs,
}: {
  onCancel: (runId: string) => void;
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
          <div className="run-meta">
            <span>{run.status}</span>
            <span>{formatRunMetadata(run.output_metadata)}</span>
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
          {run.warnings.length > 0 ? (
            <p className="muted">{run.warnings.join(" ")}</p>
          ) : null}
          {run.errors.length > 0 ? (
            <p className="error-text">{run.errors.join(" ")}</p>
          ) : null}
        </div>
      ))}
    </div>
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
  return (
    <div className={`validation-panel ${report.valid ? "valid" : "invalid"}`}>
      <div className="validation-heading">
        <strong>{report.valid ? "Valid" : "Invalid"}</strong>
        <span>
          {report.errors.length} errors / {report.warnings.length} warnings
        </span>
      </div>
      {report.issues.length === 0 ? (
        <p className="muted">Dataset is ready for preprocessing.</p>
      ) : (
        <ul className="issue-list">
          {report.issues.map((issue) => (
            <li key={`${issue.severity}-${issue.code}-${issue.field ?? ""}`}>
              <strong>{issue.code}</strong>
              <span>{issue.message}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
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
      </dl>
      <div>
        <h3>Channel Names</h3>
        <div className="channel-list">
          {data.channel_names.map((channelName) => (
            <span key={channelName}>{channelName}</span>
          ))}
        </div>
      </div>
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
    throw new Error(detail || `${response.status} ${response.statusText}`);
  }

  return response.json() as Promise<T>;
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

function normalizePreprocessingConfig(
  config: typeof DEFAULT_PREPROCESSING_CONFIG,
): PreprocessingConfig {
  return {
    high_pass_hz: parseOptionalNumber(config.high_pass_hz),
    low_pass_hz: parseOptionalNumber(config.low_pass_hz),
    notch_hz: parseOptionalNumber(config.notch_hz),
    resample_hz: parseOptionalNumber(config.resample_hz),
    reference: config.reference || null,
  };
}

function getPreprocessingConfigError(
  config: typeof DEFAULT_PREPROCESSING_CONFIG,
): string | null {
  const highPass = parseOptionalNumber(config.high_pass_hz);
  const lowPass = parseOptionalNumber(config.low_pass_hz);
  const notch = parseOptionalNumber(config.notch_hz);
  const resample = parseOptionalNumber(config.resample_hz);

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

  return null;
}

function parseOptionalNumber(value: string): number | null {
  if (!value.trim()) {
    return null;
  }
  return Number(value);
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

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
