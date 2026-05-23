# Shared

Shared utilities that are not specific to the chat domain.

Suggested internal layout:

```text
src/
  config/  Shared configuration helpers
  types/   Generic shared types
  utils/   Small pure utilities
```

If a utility starts encoding chat behavior, move it to `packages/chat-core`.
