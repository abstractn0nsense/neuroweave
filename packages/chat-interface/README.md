# Chat Interface

Future conversational interface for EEG workflows.

Suggested internal layout:

```text
src/
  commands/    Chat intent and command mapping
  summaries/   Workflow and result summaries for chat responses
  adapters/    LLM or assistant runtime integrations
```

Keep this package thin. It should translate between chat interactions and workflow actions, while EEG rules stay in `packages/eeg-core` and execution rules stay in `packages/workflow-engine`.
