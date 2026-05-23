# Workflow Engine

Pipeline orchestration package for EEG workflows.

Suggested internal layout:

```text
src/
  definitions/  Pipeline and step definitions
  execution/    Run orchestration, progress, cancellation, and retries
  state/        Job state, run history, and result references
```

The engine should compose EEG I/O and processing behavior through stable interfaces. It should not depend on UI components or chat-specific concepts.
