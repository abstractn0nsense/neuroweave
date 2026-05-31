# Reproducibility Graph Contract

Phase E defines a reproducibility graph before adding one-click rerun. The graph
is a review artifact that records how a completed result was produced from local
dataset files, run configs, parent run IDs, worker outputs, artifact manifests,
comparison summaries, statistics, and Phase D provenance.

This is the contract for `reproducibility_graph.json`. It does not execute a
rerun and it must not mutate completed run records.

## Goals

- Make the dataset -> preprocessing -> epoch -> ERP -> comparison lineage
  explicit.
- Preserve config snapshots and config digests for rerun planning.
- Link every run node to artifact manifests and important artifact logical names.
- Carry worker payload/result/stdout/stderr metadata when available.
- Carry Phase D source file, sidecar, event provenance, and diagnostics links
  when available.
- Represent missing optional provenance as structured warnings, not graph
  generation failures.
- Support batch-created runs without making batch state part of the run chain.

## Versioning

Reproducibility graphs use an independent schema version.

```json
{
  "schema_version": 1,
  "graph_kind": "reproducibility_graph"
}
```

Rules:

- `schema_version` is the envelope version for the graph document.
- Run record schema versions remain independent.
- Node IDs are graph-local stable references.
- Unknown future top-level keys must be additive.
- Breaking changes require a new `schema_version`.

## Graph Shape

Canonical stored shape:

```json
{
  "schema_version": 1,
  "graph_kind": "reproducibility_graph",
  "created_at_utc": "2026-05-30T00:00:00+00:00",
  "dataset_id": "dataset-001",
  "root_node_id": "dataset:dataset-001",
  "terminal_node_id": "comparison:erp-001:comparison_summary",
  "nodes": [],
  "edges": [],
  "diagnostics": {
    "warnings": []
  }
}
```

Required top-level fields:

- `schema_version`
- `graph_kind`
- `created_at_utc`
- `dataset_id`
- `root_node_id`
- `terminal_node_id`
- `nodes`
- `edges`
- `diagnostics`

## Node Kinds

Version 1 supports these node kinds:

- `dataset`
- `preprocessing_run`
- `epoch_run`
- `erp_run`
- `comparison`

### Dataset Node

The dataset node records local data identity and Phase D provenance pointers.

```json
{
  "node_id": "dataset:dataset-001",
  "kind": "dataset",
  "label": "dataset-001",
  "dataset_id": "dataset-001",
  "phase_d": {
    "recording_source_files": [],
    "sidecar_discovery": {},
    "event_provenance": {},
    "event_source_columns": {}
  },
  "diagnostics": {
    "warnings": []
  }
}
```

### Run Nodes

Run nodes record immutable execution identity and rerun-relevant metadata.

```json
{
  "node_id": "run:preprocessing:preprocess-001",
  "kind": "preprocessing_run",
  "label": "preprocess-001",
  "dataset_id": "dataset-001",
  "run_id": "preprocess-001",
  "run_kind": "preprocessing",
  "status": "completed",
  "config_snapshot": {},
  "config_digest_sha256": "sha256:...",
  "artifact_manifest": {
    "path": "data/processed/dataset-001/preprocess-001/artifact_manifest.json",
    "artifact_count": 4
  },
  "artifacts": [],
  "worker": {
    "schema_version": 1,
    "exit_code": 0,
    "payload_path": "data/runs/preprocess-001/worker_payload.json",
    "result_path": "data/runs/preprocess-001/worker_result.json",
    "stdout_path": "data/runs/preprocess-001/worker_stdout.log",
    "stderr_path": "data/runs/preprocess-001/worker_stderr.log"
  },
  "provenance": {
    "path": "data/processed/dataset-001/preprocess-001/provenance.json",
    "schema_version": 1
  },
  "batch": null,
  "diagnostics": {
    "warnings": []
  }
}
```

Run node rules:

- `run_id`, `run_kind`, `status`, and `config_snapshot` are required.
- `config_digest_sha256` is computed from canonical JSON for `config_snapshot`.
- `artifact_manifest.path` is optional when missing, but the node must include a
  warning.
- `worker` is optional for legacy runs, but missing worker metadata must be a
  warning, not a graph failure.
- `batch` is optional and records only the batch context for a run created by a
  batch item.

### Comparison Node

The comparison node records the descriptive comparison and optional Phase E
statistics object.

```json
{
  "node_id": "comparison:erp-001:comparison_summary",
  "kind": "comparison",
  "label": "target - standard",
  "dataset_id": "dataset-001",
  "run_id": "erp-001",
  "comparison_summary_path": "data/erp/dataset-001/erp-001/comparison_summary.json",
  "metric": "mean_amplitude_uv",
  "condition_pair": {
    "a": "target",
    "b": "standard"
  },
  "statistics": {
    "status": "implemented",
    "method": "paired_t_test"
  },
  "diagnostics": {
    "warnings": []
  }
}
```

Comparison node rules:

- The comparison node is a child of the ERP run node.
- It must not replace the ERP run node.
- If `comparison_summary.json` is missing, the graph may still be generated with
  a comparison node only when the caller explicitly targets a comparison; the
  node must contain a structured warning.

## Edges

Version 1 supports these edge relations:

- `contains`
- `produced`
- `derived_from`
- `compares`

The main chain for an ERP comparison is:

```text
dataset -> preprocessing_run -> epoch_run -> erp_run -> comparison
```

Edges are directed and ordered by the `edges` array:

```json
{
  "edge_id": "edge:erp-001:comparison",
  "source": "run:erp:erp-001",
  "target": "comparison:erp-001:comparison_summary",
  "relation": "compares"
}
```

## Artifacts

Artifact entries are compact copies of artifact manifest rows:

```json
{
  "logical_name": "comparison_summary",
  "artifact_type": "comparison_json",
  "path": "data/erp/dataset-001/erp-001/comparison_summary.json",
  "checksum_sha256": "abc123",
  "size_bytes": 1024,
  "exists": true
}
```

Rules:

- `logical_name`, `artifact_type`, `path`, and `exists` are required.
- `checksum_sha256` and `size_bytes` are included when available.
- Missing artifacts remain in the node with `exists: false` and a graph warning.

## Batch Context

Batch-created runs can include a compact `batch` object on the run node:

```json
{
  "batch_id": "batch-001",
  "batch_item_id": "batch-001-item-001",
  "template_id": "template-001",
  "template_digest_sha256": "sha256:...",
  "attempt": 1
}
```

Rules:

- Batch context does not change the main run lineage.
- Retry history belongs in batch metadata and future graph extensions; it must
  not rewrite completed run IDs.

## Diagnostics

Graphs use the Phase D diagnostic warning shape:

```json
{
  "code": "provenance_missing",
  "severity": "warning",
  "source": "artifact",
  "impact": "No provenance artifact was found for run erp-001.",
  "suggested_action": "Regenerate the run or rebuild the artifact manifest."
}
```

Graph generation should continue for missing optional provenance, sidecar
metadata, worker metadata, or artifacts. It should fail only when the target
dataset or target completed run cannot be identified.

## Schema And Fixture

The draft JSON Schema is stored at:

```text
docs/schemas/reproducibility-graph.schema.json
```

The contract fixture is stored at:

```text
tests/fixtures/reproducibility/reproducibility_graph_erp_comparison_v1.json
```

This fixture covers dataset -> preprocessing -> epoch -> ERP -> comparison
lineage, a batch-created preprocessing node, worker metadata, artifact entries,
config digests, Phase D provenance links, and a statistics-bearing comparison
node.

## Future Work

E5 may add a read-only UI over this graph. E6 may add rerun planning that reads
this graph and reports blockers. Neither phase should require a graph schema
change unless the graph cannot represent a necessary rerun precondition.
