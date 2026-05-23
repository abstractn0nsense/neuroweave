# Chat Adapters

Infrastructure package for concrete implementations used by chat features.

Suggested internal layout:

```text
src/
  llm/       LLM provider implementations
  storage/   Database, file, or vector store implementations
  realtime/  WebSocket, SSE, queue, or pub/sub implementations
```

Adapters should implement interfaces from `packages/chat-core/src/ports`.
