# API App

Server-side entrypoint for chat workflows.

Expected responsibilities:

- expose chat endpoints
- validate request and response shapes
- compose `chat-core` use cases with infrastructure from `chat-adapters`
- handle authentication and runtime configuration when those features are added

Do not put reusable chat domain rules here. Move them to `packages/chat-core`.
