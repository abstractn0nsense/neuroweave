# Chat Core

Framework-independent chat domain package.

Suggested internal layout:

```text
src/
  domain/       Entities, value objects, and domain rules
  application/  Use cases and orchestration that stays provider-agnostic
  ports/        Interfaces for storage, LLMs, realtime, and other adapters
```

This package should remain easy to test without a browser, server framework, database, or LLM SDK.
