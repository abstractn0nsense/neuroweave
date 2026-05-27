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

## Phase B6 Execution Status

B2 executes automatic bad-channel detection in report-only mode. It records
candidates and metrics in diagnostics, but does not mutate `raw.info["bads"]`,
interpolate channels, or remove data.

B3 applies `manual_bad_channels` to `raw.info["bads"]` before saving the
preprocessed FIF.

B4 interpolates the marked bad channels when
`bad_channel_interpolation.enabled` is true. Interpolation is applied to the raw
data before filters/reference/resampling, and the report records before/after
bad-channel state. With the default `reset_bads: true`, interpolated channels are
removed from the output bad list after interpolation.

B5 writes a before/after QC comparison for preprocessing. The comparison records
input raw state and final preprocessed output state for bad-channel counts,
annotation counts, variance summaries, and PSD band-power summaries.

B6 executes EOG/ECG artifact detection in report-only mode. EOG/ECG channels can
be user-specified, inferred from channel types, or inferred from channel names.
The worker records blink and heartbeat candidate events in diagnostics, but does
not add annotations, reject data, or mutate the raw signal.

Other artifact-aware fields remain schema-only until later B subphases:

- B7: ICA

Bad-channel detection methods:

- `flat`: marks channels with near-zero peak-to-peak amplitude.
- `deviation`: marks flat channels and channels whose log standard deviation is
  outside the robust z-score threshold. If `minimum_correlation` is set, it also
  marks channels with low correlation to the median of peer EEG channels.
- `ransac`: accepted by the contract, but currently reports `unsupported`
  without candidates because the optional dependency path is deferred.

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
      "channels": ["Fp1"],
      "applied_channels": ["Fp1"],
      "status": "applied"
    },
    "detection": {
      "config": {
        "enabled": true,
        "method": "deviation",
        "minimum_correlation": null,
        "zscore_threshold": 5.0
      },
      "method": "deviation",
      "status": "completed",
      "candidate_count": 1,
      "candidates": [
        {
          "channel": "Fp1",
          "reasons": ["variance_deviation"],
          "metrics": {
            "std_uv": 184.2,
            "peak_to_peak_uv": 1030.5,
            "log_std_robust_zscore": 6.4,
            "correlation": 0.12
          }
        }
      ],
      "metrics": {
        "channel_count": 64,
        "zscore_threshold": 5.0,
        "minimum_correlation": null,
        "flat_threshold_uv": 0.000001
      }
    },
    "interpolation": {
      "config": {
        "enabled": true,
        "reset_bads": true
      },
      "status": "applied",
      "before": {
        "bad_channels": ["Fp1"],
        "bad_channel_count": 1
      },
      "after": {
        "bad_channels": [],
        "bad_channel_count": 0
      },
      "interpolated_channels": ["Fp1"],
      "reset_bads": true,
      "montage_source": "existing"
    }
  },
  "artifact_rejection": {
    "enabled": true,
    "schema_version": 1,
    "config": {
      "eog_enabled": true,
      "ecg_enabled": true,
      "eog_channels": [],
      "ecg_channels": [],
      "create_annotations": true
    },
    "status": "completed",
    "mode": "report_only",
    "annotations_created": false,
    "create_annotations_requested": true,
    "eog": {
      "schema_version": 1,
      "enabled": true,
      "status": "completed",
      "channel_source": "channel_type",
      "channels": ["VEOG"],
      "candidate_count": 1,
      "candidates": [
        {
          "type": "blink",
          "channel": "VEOG",
          "onset_seconds": 2.34,
          "duration_seconds": 0.25,
          "peak_amplitude_uv": 142.1,
          "score": 9.6
        }
      ],
      "warnings": []
    },
    "ecg": {
      "schema_version": 1,
      "enabled": true,
      "status": "completed",
      "channel_source": "channel_type",
      "channels": ["ECG"],
      "candidate_count": 1,
      "candidates": [
        {
          "type": "heartbeat",
          "channel": "ECG",
          "onset_seconds": 1.02,
          "duration_seconds": 0.1,
          "peak_amplitude_uv": 88.5,
          "score": 7.8
        }
      ],
      "warnings": []
    },
    "warnings": [],
    "reason": "EOG/ECG artifact candidates are reported without modifying raw annotations."
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
    "status": "completed",
    "before_after": {
      "enabled": true,
      "before": {
        "channel_status": {
          "bad_channels": [],
          "bad_channel_count": 0
        },
        "annotations": {
          "count": 0,
          "descriptions": []
        },
        "variance": {
          "channel_count": 64,
          "mean_uv2": 12.4,
          "median_uv2": 11.8,
          "min_uv2": 4.2,
          "max_uv2": 31.5,
          "channels": []
        },
        "psd": {
          "channel_count": 64,
          "sampling_rate_hz": 256.0,
          "total_power_uv2": 1840.2,
          "bands": {
            "alpha": {
              "low_hz": 8.0,
              "high_hz": 13.0,
              "mean_power_uv2": 120.5,
              "median_power_uv2": 101.4
            }
          }
        }
      },
      "after": {
        "channel_status": {
          "bad_channels": [],
          "bad_channel_count": 0
        },
        "annotations": {
          "count": 0,
          "descriptions": []
        },
        "variance": {},
        "psd": {}
      },
      "delta": {
        "bad_channel_count": 0,
        "annotation_count": 0,
        "variance_mean_uv2": -3.1,
        "variance_mean_ratio": 0.75,
        "psd_total_power_uv2": -300.0,
        "psd_total_power_ratio": 0.84
      }
    }
  }
}
```

## Compatibility Rules

- Legacy Phase A config JSON without Phase B fields loads with safe defaults.
- Worker payload schema remains `schema_version: 1`; artifact-aware config is
  added as nested optional fields.
- Run record `schema_version` remains `1` until the run envelope changes.
- Export/report consumers should treat unknown future keys as additive.
