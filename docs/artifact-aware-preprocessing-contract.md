# Artifact-Aware Preprocessing Contract

Phase B starts by stabilizing the preprocessing contract before adding artifact
execution. This document defines the JSON shape accepted by the API, stored in
run records, passed to worker payloads, and summarized in preprocessing
diagnostics.

## Config

`PreprocessingConfig` remains backward-compatible with Phase A fields. Missing
Phase B fields are filled with defaults when legacy run JSON is loaded.

```json
{
  "artifact_schema_version": 1,
  "high_pass_hz": 1.0,
  "low_pass_hz": 40.0,
  "notch_hz": null,
  "resample_hz": null,
  "reference": "average",
  "manual_bad_channels": ["Fp1"],
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
    "exclude_components": [],
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
}
```

Allowed methods:

- `bad_channel_detection.method`: `none`, `flat`, `deviation`, `ransac`
- `ica.method`: `fastica`, `infomax`, `picard`
- `qc.metrics`: `channel_status`, `amplitude`, `annotations`, `psd`, `ica`

Channel-list fields must reference uploaded recording channel names. The API
rejects unknown channels before queueing a run.

## Phase B1 Execution Status

B1 stores and transports the contract, but does not apply artifact operations.
When artifact-aware fields are requested, preprocessing keeps the run
reproducible and records an explicit warning that execution is deferred to the
later B subphase:

- B2: bad channel detection
- B3: manual bad channel marking
- B4: interpolation
- B6: EOG/ECG artifact handling
- B7: ICA

## Diagnostics

`artifact_summary.json` includes the Phase B sections even when execution is not
enabled. This gives the UI, export bundle, and future QC views a stable schema.

```json
{
  "schema_version": 1,
  "input": {
    "bad_channels": [],
    "bad_channel_count": 0,
    "annotation_count": 0,
    "annotation_descriptions": []
  },
  "output": {
    "bad_channels": [],
    "bad_channel_count": 0,
    "annotation_count": 0,
    "annotation_descriptions": []
  },
  "bad_channels": {
    "schema_version": 1,
    "manual": {
      "channels": [],
      "status": "not_requested"
    },
    "detection": {
      "config": {
        "enabled": false,
        "method": "none",
        "minimum_correlation": null,
        "zscore_threshold": null
      },
      "status": "not_requested"
    },
    "interpolation": {
      "config": {
        "enabled": false,
        "reset_bads": true
      },
      "status": "not_requested"
    }
  },
  "artifact_rejection": {
    "enabled": false,
    "schema_version": 1,
    "config": {
      "eog_enabled": false,
      "ecg_enabled": false,
      "eog_channels": [],
      "ecg_channels": [],
      "create_annotations": true
    },
    "reason": "Artifact detection and rejection are configured by contract but not executed in Phase B1."
  },
  "ica": {
    "schema_version": 1,
    "config": {
      "enabled": false,
      "method": "fastica",
      "n_components": null,
      "random_state": 97,
      "max_iter": "auto",
      "exclude_components": [],
      "eog_channels": [],
      "ecg_channels": []
    },
    "status": "not_requested"
  },
  "qc": {
    "schema_version": 1,
    "config": {
      "enabled": true,
      "include_before_after": true,
      "metrics": ["channel_status", "amplitude", "annotations"]
    },
    "status": "schema_only"
  }
}
```

## Compatibility Rules

- Legacy Phase A config JSON without Phase B fields loads with safe defaults.
- Worker payload schema remains `schema_version: 1`; artifact-aware config is
  added as nested optional fields.
- Run record `schema_version` remains `1` until the run envelope changes.
- Export/report consumers should treat unknown future keys as additive.
