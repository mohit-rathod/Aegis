# Aegis Support Assistant architecture

One Settings model is loaded from the existing environment. bootstrap.py is the only composition root. create_runtime assembles one async GroqClient, shared Redis stores, a bounded retrieval executor, the three handlers, one guarded dispatcher, and one SupportService.

The CLI and HTTP API submit channel-independent Turn objects to SupportService. The service validates session ownership, checks input, classifies intent, dispatches the approved turn, validates the result, persists the session transition and returns SupportResponse. Product retrieval is a handler capability, not a separate application.

## Ownership

- config.py: all environment-backed settings; existing environment names remain valid.
- bootstrap.py: resource construction and shutdown; developer retrieval tooling can reuse build_retriever without starting a second service.
- application/support_service.py: the sole conversation orchestration path.
- application/response_service.py: common evidence checks and response rendering.
- agents/: product_question, order_status and human_escalation handlers.
- adapters/groq/client.py: one async chat/tool provider implementation.
- entrypoints/cli.py: chat, ask, metrics, build-index and retrieve commands.
- entrypoints/api/app.py: HTTP transport and demo-authentication boundary.
- rag/: reusable indexing, retrieval, grounding and citation capabilities.
- voice/: reserved channel coordination modules; voice processing is not implemented yet.

## Adding voice

Future capture/VAD/STT coordination will create Turn(channel="voice") and call the same runtime.service.handle method. Only a validated SupportResponse may reach TTS. Voice must reuse session identity, turn IDs, state and termination rules. Add speech-provider adapters and coordinator state under existing voice/ and adapters/ folders; do not create another settings model, routing pipeline or application bootstrap.

## Stable behavior

The three intent IDs, Redis prefix/key layout, authorization rules, session TTLs, cache semantics, refund message and escalation termination behavior are unchanged by the consolidation. Knowledge-base document bytes and hashes remain unchanged, so this refactor alone does not require index rebuilding. API routes and body fields remain compatible.
