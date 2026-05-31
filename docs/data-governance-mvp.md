# Data Governance MVP

Phase E adds a minimal local-data deletion path for the preview build. The goal
is explicit operator control over local dataset data without adding project-wide
delete/export semantics yet.

## Scope

Implemented:

- Dataset-scoped local data deletion.
- Required confirmation through `confirm_dataset_id`.
- Dry-run preview through `dry_run=true`.
- Active-run guard for `pending`, `running`, and `cancelling` runs.
- Deletion of dataset upload registry files, run metadata, and dataset-scoped
  processing output directories.

Deferred:

- Project export/delete.
- Cross-project archive policy.
- Secure erase.
- User/account retention policy.
- Cloud or shared-storage governance.

## API

```http
DELETE /datasets/{dataset_id}/local-data?confirm_dataset_id={dataset_id}
```

Optional dry run:

```http
DELETE /datasets/{dataset_id}/local-data?confirm_dataset_id={dataset_id}&dry_run=true
```

The confirmation value must exactly match the path `dataset_id`. A mismatch
returns `400` and does not delete anything.

If the dataset has active `pending`, `running`, or `cancelling` preprocessing,
epoch, or ERP runs, the endpoint returns `409` with `active_run_ids` and does
not delete anything.

## Deletion Boundary

The endpoint deletes only paths resolved under known local roots:

- `data/raw/uploads/datasets/{dataset_id}/`
- `data/runs/{run_id}/` for runs belonging to the dataset
- `data/processed/{dataset_id}/`
- `data/epochs/{dataset_id}/`
- `data/erp/{dataset_id}/`
- run output or artifact-manifest parent directories only when they resolve
  under `data/processed/`, `data/epochs/`, or `data/erp/`

Project, experiment, and participant records are retained. This keeps study
setup metadata available while removing dataset-local files and run records.

The endpoint refuses to delete paths outside those roots and reports skipped
unsafe paths in `warnings`.

## Response

```json
{
  "dataset_id": "dataset-001",
  "dry_run": false,
  "deleted": true,
  "deleted_paths": [
    "data/raw/uploads/datasets/dataset-001",
    "data/runs/preprocess-001",
    "data/processed/dataset-001"
  ],
  "run_ids": {
    "preprocessing": ["preprocess-001"],
    "epoch": [],
    "erp": []
  },
  "warnings": []
}
```

`dry_run=true` returns the same planned path and run-id shape with
`deleted=false`.
