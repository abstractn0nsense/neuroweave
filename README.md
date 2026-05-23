# NeuroWeave

NeuroWeave is being prepared as a chat-based project.

## Structure

```text
apps/
  api/                  Server/API entrypoint for chat features
  web/                  Web chat UI entrypoint
packages/
  chat-core/            Framework-independent chat domain and use cases
  chat-adapters/        LLM, storage, realtime, and external integrations
  shared/               Shared config, types, and small utilities
docs/
  architecture.md       Folder boundaries and dependency rules
  decisions/            Architecture decision notes
tests/
  fixtures/             Shared test fixtures
```

## Dependency Direction

Keep dependencies flowing inward:

```text
apps -> packages/chat-adapters -> packages/chat-core
apps -> packages/shared
packages/chat-adapters -> packages/shared
packages/chat-core -> packages/shared only when the dependency is truly generic
```

`chat-core` should not import app code, framework code, database clients, or LLM SDKs.
