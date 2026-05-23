# Architecture

This repository starts with a chat-first folder layout that can grow into a web app, API service, worker, or multiple packages without forcing early framework choices.

## Folders

### `apps/`

Runnable applications live here.

- `apps/web`: browser UI for chat sessions, messages, settings, and user flows.
- `apps/api`: HTTP or RPC entrypoint for chat orchestration.

Applications can depend on packages, but packages should not depend on applications.

### `packages/chat-core/`

Framework-independent chat logic lives here.

Use this package for:

- conversation and message models
- chat session state rules
- use cases such as creating a conversation or appending a message
- ports/interfaces that describe what storage or LLM providers must do

Avoid importing SDKs, database clients, UI frameworks, or server frameworks from this package.

### `packages/chat-adapters/`

Infrastructure implementations live here.

Use this package for:

- LLM provider adapters
- persistence adapters
- realtime transport adapters
- file or vector store adapters

Adapters implement the ports defined by `chat-core`.

### `packages/shared/`

Small cross-cutting code lives here.

Use this package for generic config, shared types, constants, and tiny utilities. Keep domain-specific chat behavior in `chat-core`.

### `tests/`

Repository-level test fixtures and integration test support live here. Package-specific tests can live near the code once a test framework is chosen.

## Compatibility Rules

1. Keep domain logic in `chat-core`.
2. Put external service code in `chat-adapters`.
3. Let `apps` compose packages instead of putting business logic directly in app entrypoints.
4. Introduce framework-specific folders only inside the app or adapter that uses that framework.
5. Prefer stable interfaces between folders before adding implementation details.
