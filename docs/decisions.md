# Design decisions

Recorded 2026-10-16T11:25:19.684060+00:00 during consolidation.

- Consolidated two configuration classes into Settings without changing existing environment-variable names.
- Replaced the older synchronous RAG-only orchestration with the active async SupportService; migrated component tests to the same async contracts.
- Consolidated provider and product-handler implementations so there is one GroqClient and one ProductQuestionAgent.
- Unified interactive chat, one-shot questions, metrics and retrieval administration under one CLI. Both installed command names resolve to that exact entry point for compatibility.
- Preserved Redis keys and knowledge-base bytes to avoid data or index migrations.
- Retained the previous decision record unchanged. The latest upload omitted earlier capacity run outputs; current regression evidence is recorded separately.
- Kept voice as a future channel adapter over the existing runtime and service, not a second application.

Earlier decision records are preserved under evidence/archive/baseline-validation/decisions.md.
