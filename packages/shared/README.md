# Shared

Shared utilities that are not specific to the EEG domain, workflow execution, or chat interface.

Suggested internal layout:

```text
src/
  config/  Shared configuration helpers
  types/   Generic shared types
  utils/   Small pure utilities
```

If a utility starts encoding EEG behavior, move it to `packages/eeg-core`. If it starts encoding workflow behavior, move it to `packages/workflow-engine`.
