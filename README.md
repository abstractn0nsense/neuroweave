# NeuroWeave

NeuroWeave is being prepared as a neuroscience and EEG workflow project.

## Structure

```text
apps/
  api/                  Server/API entrypoint for EEG workflows
  web/                  Web UI for EEG workflow setup and review
packages/
  eeg-core/             EEG domain models and pipeline contracts
  eeg-processing/       Signal preprocessing and analysis steps
  eeg-io/               EEG file readers, writers, and dataset adapters
  workflow-engine/      Pipeline execution graph and job state
  chat-interface/       Future chat layer for controlling EEG workflows
  shared/               Shared config, types, and small utilities
docs/
  architecture.md       Folder boundaries and dependency rules
  eeg-workflow.md       Initial EEG workflow outline
  decisions/            Architecture decision notes
tests/
  fixtures/eeg/         Shared EEG test fixtures
```

## Dependency Direction

Keep dependencies flowing inward:

```text
apps -> packages/workflow-engine -> packages/eeg-processing -> packages/eeg-core
apps -> packages/eeg-io -> packages/eeg-core
apps -> packages/chat-interface -> packages/workflow-engine
apps -> packages/shared
```

`eeg-core` should not import app code, UI frameworks, database clients, or vendor SDKs. The chat layer is intentionally thin for now and should depend on the workflow layer instead of becoming the source of EEG domain rules.
