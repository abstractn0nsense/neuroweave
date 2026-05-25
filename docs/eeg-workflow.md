# EEG Workflow

The first product direction is an EEG workflow for neuroscience work.

## Initial Flow

```text
setup project, experiment, and dataset
  -> choose active dataset
  -> continue to analysis
  -> upload EEG recording and event log
  -> validate metadata
  -> inspect channels and events
  -> preprocess signal
  -> detect or correct artifacts
  -> segment or epoch data
  -> run analysis
  -> review outputs
  -> export results
```

## Early Concepts

- Dataset: a source EEG recording plus metadata.
- Recording: signal data, sampling rate, channels, events, and annotations.
- Pipeline: ordered workflow definition.
- Step: one processing or analysis operation.
- Run: one execution of a pipeline against a dataset.
- Result: derived data, metrics, plots, logs, or exported files.
- Event Log: stimulus timing, trial condition, response, accuracy, and reaction-time data from tools such as PsychoPy.

## Current App Flow

The current web app intentionally separates setup from analysis:

```text
Setup
  -> create/select project
  -> create/select experiment
  -> create/select dataset
  -> review active dataset readiness
  -> Continue Analysis

Analysis
  -> upload EEG recording
  -> upload event log
  -> save event mapping
  -> validate dataset
  -> run preprocessing
  -> run epoching
  -> generate ERP preview
  -> prepare descriptive comparison
  -> review QC/export artifacts
```

Dataset Queue selection should only change the active dataset. It should not move
the user into Analysis by itself. This keeps study organization separate from
processing actions and reduces accidental workflow execution.

## Phase Direction

```text
Phase 0: local foundation, sample EEG, API/UI connection
Phase 1: external experiment dataset upload, event log ingestion, validation
Phase 2: preprocessing presets and QC report
Phase 3: workflow/job engine, run state, result storage
Phase 4: analysis modules, feature extraction, metrics
Phase 5: plots, tables, PDF/CSV/ZIP export
Phase 6: end-to-end UI polish
Phase 7: chat or assistant layer over the workflow
```

Near-term hardening should preserve reproducibility by keeping run configs
immutable, storing artifact manifests, validating event timing before processing,
and making every failed run queryable with warnings and errors.

## Future Chat Role

Chat should help users operate the workflow, not replace the workflow model.

Examples:

- "Load this EDF file and show basic metadata."
- "Run the default preprocessing pipeline."
- "Explain why this channel was marked noisy."
- "Compare alpha power before and after artifact correction."
