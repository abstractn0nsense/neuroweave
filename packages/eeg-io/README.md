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

Phase 0 reader contract:

- `eeg_io.datasets.list_eeg_files(directory)`: discover supported EEG files.
- `eeg_io.datasets.find_eeg_file_by_id(directory, dataset_id)`: resolve one discovered file.
- `eeg_io.readers.read_eeg_metadata(path, dataset_id=None)`: read metadata with MNE and return `RecordingMetadata`.
