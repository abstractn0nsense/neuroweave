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

Phase 1 ingestion domain contract:

- `Project`: top-level research or product workspace.
- `Experiment`: protocol/task definition, including a default event column mapping.
- `Participant`: participant identity within a project.
- `Session`: one participant visit or recording session for an experiment.
- `Dataset`: analysis-ready unit linking project, experiment, participant, and session.
- `Recording`: uploaded EEG file plus extracted recording metadata.
- `EventLog`: uploaded behavior/event log plus normalized event rows.
- `UploadedFile`: original file identity and local storage metadata.
- `ValidationReport`: blocking errors and warnings before preprocessing.
