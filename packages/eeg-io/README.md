# EEG I/O

File and dataset boundary package.

Suggested internal layout:

```text
src/
  readers/    EDF, BDF, FIF, CSV, and other importers
  writers/    Exporters for processed data, reports, or interoperable formats
  metadata/   Metadata normalization and validation helpers
```

I/O modules should convert external formats into `packages/eeg-core` models.
