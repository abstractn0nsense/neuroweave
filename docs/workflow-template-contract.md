# Workflow Template Contract

Phase C introduces reusable workflow templates for applying a known EEG analysis
configuration to new datasets. This document defines the domain contract for C1:
template schema/versioning, included preprocessing/epoch/ERP config, and the
policy for separating subject-specific or channel-specific fields.

This is a contract document, not the API implementation. C2 and later phases
should keep storage, validation, API responses, UI copy, and batch snapshots
compatible with this shape.

## Goals

- Capture reusable workflow parameters from completed runs.
- Keep completed run records immutable.
- Avoid carrying subject-specific review decisions into new datasets by default.
- Preserve enough provenance to explain where a template came from.
- Make template application deterministic by producing a validated config preview
  before a run or batch item is queued.

## Versioning

Workflow templates use an independent template schema version.

```json
{
  "schema_version": 1,
  "template_kind": "workflow_template"
}
```

Rules:

- `schema_version` is the envelope version for the template document.
- Run record `schema_version` remains independent and must not be changed by
  template work.
- Config subobjects retain their existing domain schema markers, such as
  `preprocessing.artifact_schema_version`.
- Unknown future top-level keys must be treated as additive metadata by readers.
- Unknown future config keys must not be silently applied to a run unless the
  target config validator recognizes them.
- Breaking changes require a new `schema_version` and a migration note.

## Template Document

Canonical stored shape:

```json
{
  "schema_version": 1,
  "template_kind": "workflow_template",
  "template_id": "template_20260528_001",
  "name": "Oddball ERP preprocessing and preview",
  "description": "Reusable preprocessing, epoch, and ERP preview settings.",
  "created_at_utc": "2026-05-28T00:00:00Z",
  "updated_at_utc": "2026-05-28T00:00:00Z",
  "created_from": {
    "dataset_id": "dataset-001",
    "preprocessing_run_id": "preprocess-001",
    "epoch_run_id": "epoch-001",
    "erp_run_id": "erp-001"
  },
  "compatibility": {
    "minimum_app_phase": "C",
    "requires_event_log": true,
    "requires_completed_preprocessing": false,
    "requires_completed_epoch": false
  },
  "workflow": {
    "preprocessing": {},
    "epoch": {},
    "erp": {}
  },
  "field_policy": {
    "excluded_fields": [],
    "review_required_fields": [],
    "channel_specific_fields": []
  },
  "notes": []
}
```

Required fields:

- `schema_version`
- `template_kind`
- `template_id`
- `name`
- `created_at_utc`
- `updated_at_utc`
- `workflow`
- `field_policy`

Optional fields:

- `description`
- `created_from`
- `compatibility`
- `notes`

Identity rules:

- `template_id` is stable once created.
- `name` is user-editable and not an identifier.
- `created_from` records provenance only. It must not bind future template
  application to the source dataset or source run ids.

## Workflow Config

The `workflow` object stores reusable config fragments. Missing fragments mean
that the template does not configure that step.

```json
{
  "workflow": {
    "preprocessing": {
      "artifact_schema_version": 1,
      "high_pass_hz": 1.0,
      "low_pass_hz": 40.0,
      "notch_hz": null,
      "resample_hz": null,
      "reference": "average",
      "bad_channel_detection": {
        "enabled": false,
        "method": "none",
        "minimum_correlation": null,
        "zscore_threshold": null
      },
      "bad_channel_interpolation": {
        "enabled": false,
        "reset_bads": true
      },
      "ica": {
        "enabled": false,
        "method": "fastica",
        "n_components": null,
        "random_state": 97,
        "max_iter": "auto",
        "eog_channels": [],
        "ecg_channels": []
      },
      "artifact_handling": {
        "eog_enabled": false,
        "ecg_enabled": false,
        "eog_channels": [],
        "ecg_channels": [],
        "create_annotations": true
      },
      "qc": {
        "enabled": true,
        "include_before_after": true,
        "metrics": ["channel_status", "amplitude", "annotations"]
      }
    },
    "epoch": {
      "condition_field": "trial_type",
      "tmin_seconds": -0.2,
      "tmax_seconds": 0.8,
      "baseline_start_seconds": -0.2,
      "baseline_end_seconds": 0.0,
      "reject_eeg_uv": null
    },
    "erp": {
      "conditions": null,
      "picks": null,
      "method": "mean",
      "plot_mode": "gfp",
      "plot_channel": null
    }
  }
}
```

Do not store source run binding fields in reusable workflow config:

- `epoch.preprocessing_run_id`
- `erp.epoch_run_id`

Those ids are application-time bindings and belong in a run plan or batch item,
not in the template.

## Field Policy

`field_policy` records what was excluded or marked for review when a template was
created. This lets the UI explain why a completed run and a derived template do
not contain exactly the same fields.

```json
{
  "field_policy": {
    "excluded_fields": [
      {
        "path": "workflow.preprocessing.manual_bad_channels",
        "reason": "subject_specific",
        "source_value_summary": "1 channel omitted by default"
      },
      {
        "path": "workflow.preprocessing.ica.exclude_components",
        "reason": "subject_specific_review_decision",
        "source_value_summary": "2 ICA components omitted by default"
      }
    ],
    "review_required_fields": [
      {
        "path": "workflow.preprocessing.ica.eog_channels",
        "reason": "channel_specific",
        "source_value": ["VEOG"],
        "default_action": "validate_against_target_channels"
      }
    ],
    "channel_specific_fields": [
      "workflow.preprocessing.ica.eog_channels",
      "workflow.preprocessing.ica.ecg_channels",
      "workflow.preprocessing.artifact_handling.eog_channels",
      "workflow.preprocessing.artifact_handling.ecg_channels",
      "workflow.erp.picks",
      "workflow.erp.plot_channel"
    ]
  }
}
```

Policy entry fields:

- `path`: dotted template path.
- `reason`: one of `subject_specific`, `subject_specific_review_decision`,
  `channel_specific`, `source_run_binding`, or `unsupported`.
- `source_value`: optional original value when it is safe and useful to show.
- `source_value_summary`: optional human-readable summary when the full source
  value should not be stored.
- `default_action`: optional application action, such as
  `omit`, `requires_review`, or `validate_against_target_channels`.

## Field Classification

### Reusable By Default

These fields can be stored in a template and applied after target-dataset
validation:

- `workflow.preprocessing.artifact_schema_version`
- `workflow.preprocessing.high_pass_hz`
- `workflow.preprocessing.low_pass_hz`
- `workflow.preprocessing.notch_hz`
- `workflow.preprocessing.resample_hz`
- `workflow.preprocessing.reference`
- `workflow.preprocessing.bad_channel_detection`
- `workflow.preprocessing.bad_channel_interpolation`
- `workflow.preprocessing.ica.enabled`
- `workflow.preprocessing.ica.method`
- `workflow.preprocessing.ica.n_components`
- `workflow.preprocessing.ica.random_state`
- `workflow.preprocessing.ica.max_iter`
- `workflow.preprocessing.artifact_handling.eog_enabled`
- `workflow.preprocessing.artifact_handling.ecg_enabled`
- `workflow.preprocessing.artifact_handling.create_annotations`
- `workflow.preprocessing.qc`
- `workflow.epoch.condition_field`
- `workflow.epoch.tmin_seconds`
- `workflow.epoch.tmax_seconds`
- `workflow.epoch.baseline_start_seconds`
- `workflow.epoch.baseline_end_seconds`
- `workflow.epoch.reject_eeg_uv`
- `workflow.erp.conditions`
- `workflow.erp.method`
- `workflow.erp.plot_mode`

### Excluded By Default

These fields are not stored in reusable workflow config by default:

- `workflow.preprocessing.manual_bad_channels`
- `workflow.preprocessing.ica.exclude_components`
- `workflow.epoch.preprocessing_run_id`
- `workflow.erp.epoch_run_id`

Reasons:

- `manual_bad_channels` is a subject-specific data quality decision.
- `ica.exclude_components` is a subject-specific visual or diagnostic review
  decision.
- `preprocessing_run_id` and `epoch_run_id` are source-run bindings, not reusable
  workflow parameters.

### Review Required

These fields may be stored only as review-required or must be validated against
the target dataset before application:

- `workflow.preprocessing.ica.eog_channels`
- `workflow.preprocessing.ica.ecg_channels`
- `workflow.preprocessing.artifact_handling.eog_channels`
- `workflow.preprocessing.artifact_handling.ecg_channels`
- `workflow.erp.picks`
- `workflow.erp.plot_channel`

Reasons:

- Channel names and channel types can vary across datasets.
- Reusing a missing EOG/ECG channel would make preprocessing fail late.
- Reusing an ERP pick or plot channel that is absent from the target epoch output
  would make ERP generation or plotting fail late.

## Template Creation From Completed Runs

When creating a template from completed runs:

1. Read config snapshots from completed run records.
2. Copy reusable fields into `workflow`.
3. Omit excluded-by-default fields from `workflow`.
4. Add omitted fields to `field_policy.excluded_fields`.
5. Add channel-specific fields to `field_policy.review_required_fields` when the
   source value is non-empty.
6. Record source run ids in `created_from`.
7. Do not modify source run JSON or artifact manifests.

If only a preprocessing run is available, the template may contain only
`workflow.preprocessing`. If epoch or ERP runs are available, the template can add
their reusable config fragments.

## Template Application Contract

Applying a template must produce an application preview before queueing work.

Application preview shape:

```json
{
  "template_id": "template_20260528_001",
  "target_dataset_id": "dataset-002",
  "status": "ready",
  "configs": {
    "preprocessing": {},
    "epoch": {},
    "erp": {}
  },
  "excluded_fields": [],
  "review_required_fields": [],
  "errors": [],
  "warnings": []
}
```

Application rules:

- Fill missing config fields with the same defaults used by existing run
  creation.
- Validate preprocessing config against the target recording.
- Validate epoch config against the target event log and target preprocessing
  output metadata.
- Validate ERP config against the target epoch output.
- Do not queue a run when review-required fields are unresolved.
- Do not apply `manual_bad_channels` or `ica.exclude_components` unless a future
  explicit user override flow supplies them for the target dataset.

## Batch Snapshot Contract

Batch execution must snapshot the template at batch creation time.

Rules:

- Store the full template document or a stable digest plus full embedded template
  copy in the batch record.
- Do not follow later edits to the registry template after a batch is created.
- Store the per-subject application preview or run plan so retries use the same
  template snapshot.
- Retry may create a new run id, but it must not silently switch to a newer
  template version.

## Compatibility Checklist

C2 and later implementations must verify:

- Legacy run JSON still loads.
- Missing Phase B preprocessing fields still default safely.
- Templates with unknown additive metadata still load.
- Templates do not require source datasets or source runs to exist for listing.
- Applying a template validates against the target dataset.
- `manual_bad_channels` is excluded by default.
- `ica.exclude_components` is excluded by default or marked review-only.
- Channel-specific fields are validated before use.
- Source `preprocessing_run_id` and `epoch_run_id` never become reusable config.
- Batch snapshots are immutable and retry-safe.

## C2 Serialization Rules

The JSON repository stores templates at
`data/templates/{template_id}/template.json` through the same atomic JSON write
and lock helpers used by run and dataset registries.

Reader compatibility rules:

- Missing `schema_version` defaults to `1`.
- Missing `template_kind` defaults to `workflow_template`.
- Legacy `id` is accepted as `template_id`.
- Missing `updated_at_utc` defaults to `created_at_utc`.
- Missing `field_policy`, `created_from`, `compatibility`, and `notes` use safe
  defaults.
- Legacy top-level `preprocessing`, `epoch`, and `erp` config fragments are
  accepted when `workflow` is absent.
- Source run binding fields in legacy config, such as `preprocessing_run_id` and
  `epoch_run_id`, are ignored when loading reusable template config.
- Unknown top-level keys are retained under template `extra` so future metadata
  is not discarded by a read/write cycle.

Stale validation rules:

- Unsupported `schema_version` is invalid and stale.
- `manual_bad_channels` in reusable preprocessing config is invalid and stale.
- `ica.exclude_components` in reusable preprocessing config is invalid and
  stale.
- Non-empty channel-specific fields without a review policy are valid to load but
  marked stale until target-dataset review is resolved.

## C3 Registry API

The initial template registry API exposes the template document without applying
it to datasets yet:

```text
POST /workflow-templates
GET /workflow-templates
GET /workflow-templates/{template_id}
DELETE /workflow-templates/{template_id}
```

API behavior:

- `POST /workflow-templates` saves a new or existing template.
- When `template_id` is omitted, the API generates one.
- Updating an existing template preserves `created_at_utc` and refreshes
  `updated_at_utc`.
- Invalid templates return `422` with validation errors.
- Valid but stale templates can be saved and include `validation.stale: true`
  plus `stale_reasons` in the response.
- `GET /workflow-templates` returns all templates sorted by id.
- `DELETE /workflow-templates/{template_id}` removes the registry entry and
  returns `204`; missing templates return `404`.

## Relationship To Phase B Artifacts

Workflow templates store intended config. They do not store Phase B diagnostic
artifact contents. Completed runs remain the source of truth for:

- `bad_channel_report.json`
- `artifact_rejection_report.json`
- `ica_report.json`
- `before_after_qc.json`
- `artifact_manifest.json`

Template-derived runs must continue to emit those artifacts through the existing
preprocessing execution path.
