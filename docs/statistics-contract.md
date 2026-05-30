# ERP Statistics Contract

Phase E introduces a statistics contract for ERP comparison outputs before
adding inferential calculation code. The contract is intentionally narrow so the
first implementation can be reviewed and tested without implying support for
every EEG statistics design.

This document defines the version 1 statistics object that may be embedded under
`comparison_summary.json` as `statistics`. It does not implement the statistics
engine. E2 and later work must keep existing descriptive comparison fields
readable while adding this object.

## MVP Decision

Phase E MVP statistics are limited to:

- paired t-test;
- subject-level paired observations;
- input metric `mean_amplitude_uv`;
- two-condition ERP comparisons;
- uncorrected p-value;
- Cohen's dz effect size.

The MVP explicitly does not include:

- unpaired tests;
- permutation tests;
- confidence interval calculation;
- multiple-comparison correction;
- cluster-based time-by-channel inference;
- single-subject inference from only two evoked averages.

Rationale: the current descriptive ERP comparison stores condition means and
`nave`, but `nave` is not a subject-level sample table. Phase E must not infer
p-values from two averaged evoked files alone. Inferential statistics require an
observation table with one paired metric per subject or another explicitly
declared observation unit.

## Versioning

Statistics payloads use an independent statistics schema version.

```json
{
  "schema_version": 1,
  "status": "implemented"
}
```

Rules:

- `schema_version` is the envelope version for the statistics object.
- `comparison_summary.json` keeps its existing descriptive fields.
- Existing Phase 3 summaries with `statistics: {"implemented": false,
  "phase": "Phase 4"}` remain readable as legacy summaries.
- New readers should accept both the legacy deferred marker and the Phase E
  versioned statistics object.
- Future statistics methods must add fields or use a new schema version instead
  of changing the meaning of v1 fields.

## Embedded Shape

When statistics are available, `comparison_summary.json` should keep the
descriptive comparison payload and add a versioned `statistics` object:

```json
{
  "schema_version": 1,
  "metric": "mean_amplitude_uv",
  "conditions": {
    "a": {"label": "left_fist", "mean_amplitude_uv": 1.42},
    "b": {"label": "right_fist", "mean_amplitude_uv": 0.81}
  },
  "difference": {
    "label": "left_fist - right_fist",
    "mean_amplitude_uv": 0.61
  },
  "statistics": {
    "schema_version": 1,
    "status": "implemented",
    "implemented": true,
    "phase": "Phase E",
    "method": "paired_t_test",
    "design": "within_subject",
    "input_metric": "mean_amplitude_uv",
    "observation_level": "subject",
    "condition_pair": {
      "a": "left_fist",
      "b": "right_fist"
    },
    "sample": {
      "unit": "subject",
      "paired": true,
      "n": 12,
      "missing_pairs": 0
    },
    "result": {
      "statistic_name": "t",
      "statistic": 2.431,
      "degrees_of_freedom": 11,
      "p_value": 0.0334,
      "p_value_kind": "uncorrected",
      "effect_size": {
        "name": "cohens_dz",
        "value": 0.702,
        "interpretation": null
      },
      "confidence_interval": {
        "implemented": false,
        "level": null,
        "lower": null,
        "upper": null,
        "unit": "microvolt"
      },
      "multiple_comparison": {
        "applied": false,
        "method": null,
        "family": null,
        "adjusted_p_value": null
      }
    },
    "assumptions": [
      {
        "name": "paired_observations",
        "status": "met",
        "detail": "Each row has both condition metrics for the same subject."
      }
    ],
    "diagnostics": {
      "warnings": []
    }
  }
}
```

When statistics are not available, the same object should report a structured
status instead of inventing inferential values:

```json
{
  "statistics": {
    "schema_version": 1,
    "status": "unavailable",
    "implemented": false,
    "phase": "Phase E",
    "method": "paired_t_test",
    "design": "within_subject",
    "input_metric": "mean_amplitude_uv",
    "observation_level": "subject",
    "condition_pair": {
      "a": "left_fist",
      "b": "right_fist"
    },
    "sample": {
      "unit": "subject",
      "paired": true,
      "n": 1,
      "missing_pairs": 0
    },
    "result": null,
    "assumptions": [],
    "diagnostics": {
      "warnings": [
        {
          "code": "insufficient_observations",
          "severity": "warning",
          "source": "artifact",
          "impact": "Paired t-test requires at least two paired observations.",
          "suggested_action": "Run the comparison from a multi-subject observation table."
        }
      ]
    }
  }
}
```

## Required Field Semantics

- `status`: `implemented`, `unavailable`, `not_requested`, or `planned`.
- `implemented`: boolean compatibility flag for UI/report/export code.
- `phase`: phase that owns the current statistics behavior.
- `method`: v1 supports `paired_t_test`; future values must remain additive.
- `design`: v1 supports `within_subject`.
- `input_metric`: v1 supports `mean_amplitude_uv`.
- `observation_level`: v1 supports `subject`.
- `condition_pair`: copied labels for the selected comparison pair.
- `sample.n`: number of complete paired observations used by the test.
- `result`: object when `status` is `implemented`; otherwise `null`.
- `diagnostics.warnings`: structured warnings using the Phase D diagnostic
  taxonomy.

## Schema And Fixtures

The draft JSON Schema is stored at:

```text
docs/schemas/erp-comparison-statistics.schema.json
```

Contract fixtures are stored at:

```text
tests/fixtures/statistics/erp_comparison_statistics_paired_t_test_v1.json
tests/fixtures/statistics/erp_comparison_statistics_unavailable_v1.json
```

These files are contract fixtures. They are not generated by E1 and do not imply
that the statistics engine exists yet.

## Report And Export Rules

E3 should follow these rules:

- `analysis_report.json` should copy the statistics object into the comparison
  section when present.
- Export bundles should include `comparison_summary.json` without changing the
  existing ZIP structure.
- Missing or unavailable statistics should be represented as structured
  diagnostics, not as a failed export.
- UI and report code should display `status` and `method` before any p-value.

## Deferred Methods

The v1 schema has placeholders for confidence intervals and multiple-comparison
metadata, but those calculations are deferred. Future work may add:

- unpaired t-test for between-subject designs;
- permutation test options;
- bootstrap or analytic confidence intervals;
- false-discovery-rate or family-wise correction;
- cluster-based inference over time or channel dimensions.
