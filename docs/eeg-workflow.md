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

## Future Chat Role

Chat should help users operate the workflow, not replace the workflow model.

Examples:

- "Load this EDF file and show basic metadata."
- "Run the default preprocessing pipeline."
- "Explain why this channel was marked noisy."
- "Compare alpha power before and after artifact correction."
