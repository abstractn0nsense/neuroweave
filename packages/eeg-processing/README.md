# EEG Processing

Signal processing and analysis package.

Suggested internal layout:

```text
src/
  preprocessing/  Filtering, resampling, referencing, and normalization
  artifacts/      Artifact detection, marking, and correction
  analysis/       Epoching, features, statistics, and derived metrics
```

Processing modules should accept and return types from `packages/eeg-core` and avoid UI, API, or storage concerns.
