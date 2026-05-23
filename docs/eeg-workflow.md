# EEG Workflow

The first product direction is an EEG workflow for neuroscience work.

## Initial Flow

```text
import dataset
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

## Future Chat Role

Chat should help users operate the workflow, not replace the workflow model.

Examples:

- "Load this EDF file and show basic metadata."
- "Run the default preprocessing pipeline."
- "Explain why this channel was marked noisy."
- "Compare alpha power before and after artifact correction."
