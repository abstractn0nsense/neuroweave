# Phase C Batch Contract

This document fixes the C7 batch contract before repository, worker, and UI work.
Batch execution must be a separate persisted model and must not mutate source
datasets, templates, completed runs, or existing artifact manifests while a run
plan is being created.

## Status Enum

Batch status values are:

```text
pending
running
partial
completed
failed
cancelling
cancelled
```

Rules:

- `pending`: batch is created but no subject item is running.
- `running`: at least one subject item is actively being processed.
- `partial`: at least one item completed and at least one item failed.
- `completed`: all subject items completed.
- `failed`: batch could not complete and no completed item should be treated as a
  usable partial result.
- `cancelling`: cancellation has been requested and active items are being
  drained.
- `cancelled`: cancellation finished.

Per-subject item status uses the same lifecycle except `partial`, because a
single subject item is atomic for retry and reporting.

## Multi-Dataset Request

Initial request shape:

```json
{
  "template_id": "template-001",
  "dataset_selection": {
    "dataset_ids": ["dataset-001", "dataset-002"],
    "project_id": "project-001",
    "experiment_id": "experiment-001"
  },
  "requested_by": null,
  "continue_on_error": true,
  "dry_run": false,
  "metadata": {}
}
```

Rules:

- `template_id` is required.
- `dataset_selection.dataset_ids` is required, non-empty, ordered, and unique.
- `project_id` and `experiment_id` are optional filters/context copied from the
  UI selection; they do not replace explicit dataset ids.
- `continue_on_error` defaults to `true` so one failed subject can produce a
  `partial` batch instead of aborting completed work.
- `dry_run` may build and validate the plan without creating runnable items.

## Template Snapshot

Batch creation snapshots the template document once:

```json
{
  "template_id": "template-001",
  "template_name": "Oddball ERP",
  "template_updated_at_utc": "2026-05-28T00:10:00Z",
  "captured_at_utc": "2026-05-28T00:15:00Z",
  "template_digest_sha256": "sha256...",
  "template": {
    "schema_version": 1,
    "template_kind": "workflow_template",
    "template_id": "template-001"
  }
}
```

Rules:

- The embedded `template` is the full WorkflowTemplate document.
- `template_digest_sha256` is computed from the canonical JSON snapshot.
- Later registry edits must not affect the batch or retry behavior.
- Retries reuse this snapshot, not the current registry template.

## Per-Subject Run Plan

Each selected dataset gets one item:

```json
{
  "item_id": "batch-001-item-001",
  "dataset_id": "dataset-001",
  "status": "pending",
  "attempt": 1,
  "retry_of_item_id": null,
  "configs": {
    "preprocessing": {},
    "epoch": null,
    "erp": null
  },
  "bindings": {
    "preprocessing_run_id": null,
    "epoch_run_id": null,
    "erp_run_id": null
  },
  "planned_steps": ["preprocessing"],
  "run_ids": {},
  "previous_run_ids": {},
  "previous_error": null,
  "excluded_fields": [],
  "review_required_fields": [],
  "warnings": [],
  "errors": []
}
```

Rules:

- `configs` is the apply-preview output for that dataset after template defaults
  and target-dataset validation.
- `bindings` records completed target runs used by epoch/ERP config previews.
- `planned_steps` is ordered and uses existing run kinds: `preprocessing`,
  `epoch`, `erp`.
- `run_ids` is populated as worker orchestration creates concrete runs.
- `attempt` starts at `1`; retry paths increment it and carry the prior concrete
  run ids in `previous_run_ids`.
- `retry_of_item_id` is reserved for future retry records that need to point at
  another item; in-place retries can leave it `null`.
- `previous_error` captures the failure reason that motivated a retry.
- `excluded_fields` and `review_required_fields` are copied from apply preview
  so the UI can explain subject-specific omissions and blocked review decisions.
- Failed item retry must preserve the same batch-level template snapshot and
  carry forward the previous item error in the retry record.

## Batch Run Plan

Persisted plan shape:

```json
{
  "schema_version": 1,
  "batch_id": "batch-001",
  "status": "pending",
  "created_at_utc": "2026-05-28T00:16:00Z",
  "updated_at_utc": "2026-05-28T00:16:00Z",
  "request": {},
  "template_snapshot": {},
  "items": [],
  "warnings": [],
  "errors": []
}
```

Validation rules:

- `schema_version` must be supported.
- `batch_id`, `created_at_utc`, and `updated_at_utc` are required.
- `template_snapshot.template_id` must match `request.template_id`.
- `template_snapshot.template_digest_sha256` must match the embedded template.
- `items[*].dataset_id` must match `dataset_selection.dataset_ids` in the same
  order.
- `item_id` values must be unique.
- `items[*].attempt` must be at least `1`.
- `retry_of_item_id`, when present, must reference another item and use attempt
  `2` or greater.
- `completed` requires every item to be completed.
- `partial` requires at least one completed item and at least one failed item.

## C8 Repository And API

C8 persists batch plans with `JsonBatchRepository` at
`data/batches/{batch_id}/batch.json` by default. The root can be overridden with
`NEUROWEAVE_BATCHES_DIR`. The repository validates plans before save, loads
legacy/missing retry fields with defaults, and recomputes a missing snapshot
digest from the embedded template for backward-compatible reads.

API endpoints:

```text
POST /batches
GET /batches
GET /batches/{batch_id}
POST /batches/{batch_id}/cancel
POST /batches/{batch_id}/items/{item_id}/retry
```

`POST /batches` creates the immutable template snapshot, runs apply-preview for
each selected dataset, writes per-subject config/status records, and returns the
persisted plan. Later edits to the workflow template registry do not change the
embedded batch snapshot. Pending batches can be cancelled immediately; running
batches enter `cancelling` so future workers can drain active items.

`POST /batches/{batch_id}/items/{item_id}/retry` retries one failed subject
item inside an idle batch. The endpoint preserves the batch-level template
snapshot, moves the failed attempt's current run ids into `previous_run_ids`,
stores the failure reason in `previous_error`, clears current `run_ids`,
increments `attempt`, and re-queues the same batch. The worker creates a new
concrete preprocessing run id for the retry; it does not reuse the failed run id
or re-read a later registry template revision.

## C9 Planning Service

C9 moves per-subject planning into `plan_batch_run`. The service accepts an
ordered `BatchRequest`, the selected template, dataset lookup, template
apply-preview resolver, and run binding resolver. It finalizes the
`BatchRunPlan` before any worker execution starts.

Responsibilities:

- Validate the batch request before any dataset preview work.
- Resolve each selected dataset independently.
- Run template apply preview for each found dataset.
- Copy preview configs, excluded fields, review-required fields, warnings, and
  errors into that dataset's `BatchSubjectRunPlan`.
- Mark invalid or missing datasets as failed items without blocking valid
  datasets from receiving pending plans.
- Add dry-run and review-required execution warnings at item level.
- Validate the completed batch plan, including snapshot digest and item order,
  before repository persistence.

The service also returns per-dataset planning results so callers can inspect
validation state without parsing the persisted plan shape directly.

## C10 Worker Orchestration MVP

C10 adds a local batch worker that queues persisted batch ids and executes
preprocessing subject items sequentially. It reuses the existing preprocessing
run repository and `_execute_preprocessing_run` path instead of running a second
preprocessing implementation.

Worker rules:

- `POST /batches` persists the plan, then enqueues the batch id.
- Startup recovery re-enqueues `pending`, `running`, and `cancelling` batches.
- The worker marks a batch `running` before item execution.
- Each pending subject item gets one concrete preprocessing run id in
  `run_ids.preprocessing`.
- Items execute in request order; the next subject does not start until the
  previous preprocessing run reaches a terminal state.
- A completed preprocessing run marks only that subject item `completed`.
- A failed preprocessing run marks only that subject item `failed` and copies
  run errors/warnings onto the item.
- A mix of completed and failed items finalizes the batch as `partial`.
- If all runnable items fail, the batch finalizes as `failed`.

Cancellation checkpoints:

- Cancelling a pending batch marks pending items `cancelled`.
- Cancelling a running batch moves the batch to `cancelling`, marks pending or
  running items `cancelling`, and requests cancellation for the active concrete
  preprocessing run.
- The worker checks cancellation before each item and after each concrete run,
  then finalizes remaining pending items as `cancelled`.

## C13 Batch Artifact Integration

C13 adds a batch-level `batch_summary.json` artifact under
`data/batches/{batch_id}/`. The summary is generated whenever a batch reaches a
terminal worker/cancel state and can also be regenerated through:

```text
GET /batches/{batch_id}/summary-artifact
```

The summary records the immutable template snapshot digest, batch status,
per-status item counts, retry lineage fields, concrete run ids, and per-subject
artifact-manifest links such as `/artifacts/{run_id}/artifact_manifest.json`.

Run-level QC summary, analysis report, and export bundle paths now surface batch
context when the selected run was created by a batch or descends from a batched
preprocessing run. They preserve the original per-run artifact manifest and add
batch context as an additive section:

- QC summary adds `summary.batch`.
- Analysis reports add top-level `batch`.
- Export bundles include `batch/batch_summary.json`.

## C15 Hardening

C15 closes Phase C with these release rules:

- Batch cancellation must persist terminal `cancelled` state and generate a
  `batch_summary.json` artifact with cancelled item counts.
- Partial completion remains valid when at least one item completed and at
  least one item failed; completed item artifact-manifest links stay available
  in the batch summary.
- Templates whose apply preview returns `requires_review` are not runnable in a
  batch. The affected subject item is planned as `failed` with
  `Template apply requires review before batch execution.` so stale or
  channel-specific review work cannot execute automatically.
- Batch-created subject runs continue to use the normal run artifact manifest,
  artifact integrity, QC summary, analysis report, and export bundle paths.
- The Phase C full regression gate is:

```text
pytest --basetemp=data\cache\pytest
npm.cmd run build
npm.cmd run e2e:all
```
