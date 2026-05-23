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

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

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
  const [selectedSampleId, setSelectedSampleId] = useState<string | null>(null);
  const [metadata, setMetadata] = useState<LoadState<DatasetMetadata>>({
    status: "idle",
    data: null,
    error: null,
  });

  const selectedSample = useMemo(
    () => samples.data?.find((sample) => sample.id === selectedSampleId) ?? null,
    [samples.data, selectedSampleId],
  );

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    if (!selectedSampleId) {
      setMetadata({ status: "idle", data: null, error: null });
      return;
    }

    let isCurrent = true;
    setMetadata({ status: "loading", data: null, error: null });

    fetchJson<DatasetMetadata>(
      `${API_BASE_URL}/datasets/samples/${selectedSampleId}/metadata`,
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

  async function refresh() {
    setHealth({ status: "loading", data: null, error: null });
    setSamples({ status: "loading", data: null, error: null });
    setSelectedSampleId(null);

    const [healthResult, samplesResult] = await Promise.allSettled([
      fetchJson<HealthResponse>(`${API_BASE_URL}/health`),
      fetchJson<SampleDatasetsResponse>(`${API_BASE_URL}/datasets/samples`),
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
      setSelectedSampleId(samplesResult.value.samples[0]?.id ?? null);
    } else {
      setSamples({
        status: "error",
        data: null,
        error: getErrorMessage(samplesResult.reason),
      });
    }
  }

  return (
    <main className="shell">
      <section className="workspace" aria-labelledby="workspace-title">
        <header className="workspace-header">
          <div>
            <p className="eyebrow">NeuroWeave</p>
            <h1 id="workspace-title">EEG sample workspace</h1>
          </div>
          <button className="primary-button" type="button" onClick={refresh}>
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
            label="Samples"
            value={getSampleCountLabel(samples)}
            tone={samples.status === "success" ? "ok" : samples.status}
          />
          <StatusTile
            label="API URL"
            value={API_BASE_URL}
            tone="neutral"
          />
        </div>

        <div className="content-grid">
          <section className="panel" aria-labelledby="sample-list-title">
            <div className="panel-header">
              <h2 id="sample-list-title">Sample Datasets</h2>
            </div>
            <SampleList
              samples={samples}
              selectedSampleId={selectedSampleId}
              onSelect={setSelectedSampleId}
            />
          </section>

          <section className="panel" aria-labelledby="metadata-title">
            <div className="panel-header">
              <h2 id="metadata-title">Metadata</h2>
              {selectedSample ? (
                <span className="file-pill">{selectedSample.filename}</span>
              ) : null}
            </div>
            <MetadataView metadata={metadata} selectedSample={selectedSample} />
          </section>
        </div>
      </section>
    </main>
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

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }

  return response.json() as Promise<T>;
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

function getSampleCountLabel(samples: LoadState<SampleDataset[]>): string {
  if (samples.status === "success") {
    return `${samples.data.length} found`;
  }

  if (samples.status === "error") {
    return "Unavailable";
  }

  return "Loading";
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
