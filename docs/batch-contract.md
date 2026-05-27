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
- `completed` requires every item to be completed.
- `partial` requires at least one completed item and at least one failed item.
