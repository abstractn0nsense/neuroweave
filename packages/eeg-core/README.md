# EEG Core

Framework-independent EEG domain package.

Suggested internal layout:

```text
src/
  domain/       Recording, channel, montage, event, annotation, dataset, and result models
  application/  Use cases that stay provider-agnostic
  ports/        Interfaces for I/O, processing, persistence, and workflow execution
```

This package should remain easy to test without a browser, server framework, database, plotting library, or EEG vendor SDK.

Phase 0 domain contract:

- `eeg_core.domain.RecordingMetadata`: minimal metadata returned by EEG readers before full dataset ingestion exists.
