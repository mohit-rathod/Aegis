# RAG implementation decision

## Choice

Document-aware dense child-to-parent retrieval over 15 short fictional Aegis documents. Local sentence-transformer embeddings, normalized cosine similarity using NumPy, and Groq JSON answer generation with local schema validation. No keyword search, vector service, agent framework, or reranker is required for this corpus.

## Parameters

- Model: sentence-transformers/all-MiniLM-L6-v2, CPU.
- Child passage target: 160 tokenizer tokens with 24-token overlap.
- Document title included in each passage, with embedding input-length checks.
- Parent selection: rank documents by their highest-scoring child; return up to three unique documents passing the cutoff.
- Context: entire selected parent documents, preserving exceptions and related rules.
- Initial similarity cutoff: 0.25, development default only; not a confidence score or a measured optimum.

Using max child score avoids automatically rewarding a document for having more chunks. Whole documents provide enough context for this tiny corpus without a second reranking model. If future documents become long, introduce heading-bounded parent sections and a measured context budget rather than blindly expanding every match to a full manual.

## Why not alternatives today?

- Whole-document embedding alone risks tokenizer truncation and dilutes localized questions.
- Fixed character splitting ignores the embedding model's token limit and can detach policy exceptions.
- BM25 alone does not satisfy the assignment's embedding requirement. Dense+lexical hybrid search can help exact model codes later, but should be justified by observed retrieval misses.
- A vector database adds operational work without meaningful capacity benefit for a few dozen passages.
- Cross-encoder reranking and query rewriting add dependencies and latency. Add only if held-out evaluation demonstrates enough gain.
- Fine-tuning is disproportionate and does not replace source grounding.

## Safety boundary

The public standalone path performs the semantic input check, retrieval, structured answer generation, citation membership validation, semantic claim verification, and deterministic rendering. Failures release a safe response, never the draft. Claims are rendered only from a schema-valid and verified structure; answer text outside that structure cannot be returned.

Semantic checks are not perfect. The verifier shares the generation model and may share its mistakes. Retrieved text remains untrusted data. There is no tool execution in this RAG module; live facts return tool_required. The full application's trusted router, identity layer, and authorized executor must own actual order actions. Do not silently turn this module's tool_required status into an unguarded tool call.

## Evaluation plan

First inspect retrieval using the supplied 20-question development set: document hit@3, recall@3, MRR@3, and manual relevance inspection. Tune retrieval cutoff/top-k only on development data. Then create held-out paraphrases and separate injection, benign-sensitive, and unsupported-claim sets. Measure answer factuality, correct abstention, input attack recall, benign false-positive rate, and output overpromise rejection separately. Do not present development-label agreement as safety recall.

## Latency and scale

The standalone path uses up to three sequential Groq calls and synchronous local embedding inference. It favors auditable checks over low latency and is not a voice-latency claim. The voice application must maintain one coordinator, move blocking work off the audio loop, enforce a turn deadline, and invalidate late results. Load the embedding model/index once per bounded worker. Do not duplicate model loading per session. Scale admission and provider quota against active requests, not just connected sessions. This package does not establish 10k-session throughput.

## Reproducibility

Source hashes, model/revision configuration, embedding dimensions, chunk settings, library version, and build time are recorded in the index. Pin the embedding revision to a commit and lock dependencies for the submission. Treat source documents as immutable within a running worker, rebuild after edits, and restart workers. Preserve actual evaluation output with its configuration and Git commit rather than reporting estimates.
