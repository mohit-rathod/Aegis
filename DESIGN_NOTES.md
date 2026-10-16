# Aegis Support Assistant — Design Notes

## 1. Architecture and technology

One Python/FastAPI application serves browser text, voice, HTTP and CLI. All business turns enter the same `SupportService`. Redis holds shared sessions, turn replay, classifier cache and human handoffs. Groq supplies chat/function calling and Whisper STT; local Sentence Transformers, Silero VAD and Piper supply embeddings, speech detection and synthesis.

Voice flow: microphone → VAD/endpointing → Groq Whisper → guarded support service → Piper → browser speakers. Orders are fictional, read-only fixtures; this system does not execute payments or refunds.

## 2. Routing, retrieval and tools

The Groq classifier selects exactly one of three registered handlers: `product_question`, `order_status` or `escalate_to_human`. Ambiguous multi-issue requests ask for clarification.

The product handler searches 15 Aegis Markdown documents using normalized `all-MiniLM-L6-v2` embeddings and vector similarity. Chunks use 160 tokens with 24-token overlap; matched chunks expand to their source documents. Local embeddings fill Groq’s embedding gap; exact vector search avoids database overhead for this small corpus. Answers cite retrieved sources and abstain when support is insufficient. Corpus/model metadata detect stale indexes.

The order handler uses Groq native function calling with an allowlisted schema and bounded loop. Explicit schemas simplify argument validation compared with free-form ReAct parsing. The executor checks customer ownership and records authoritative tool evidence. Transactional wording comes from verified fields.

## 3. Safety guarantees and classifier cache

AI dispatch follows this enforced sequence: authenticated ownership → regex input checks → semantic input guard → signed approval → classifier → guarded dispatcher → handler → output validation → atomic commit. The dispatcher verifies approval against the exact turn/session before either RAG or tool execution. Invalid approval prevents dispatch, including on cache hits. Retrieved documents and human resolutions are untrusted context, not instructions or authorization.

Output checks reject unsupported refund and delivery commitments. Return eligibility, refund approval and actual initiation are distinct states. Only confirmed initiation permits: “The refund is initiated and will be refunded to the original payment source in the next 3-5 working days”. Approval alone cannot establish initiation.

Redis caches classifier results using message, relevant context and model/prompt identity, with bounded entries, TTL and concurrent-request coalescing. Hit rate is hits/(hits + misses); coalescing is reported separately.

## 4. Voice coordination and recovery

Silero processes 32 ms audio frames. Defaults require 160 ms speech onset, preserve 320 ms pre-roll and finalize after 768 ms nonspeech. Confirmed speech cancels playback/synthesis; short noise should not. Accepted user turns remain FIFO: playback generations suppress obsolete audio without discarding accepted input. Turn IDs, replay fingerprints, leases and acceptance/outcome events protect normal turn processing. Full queues reject new work explicitly; graceful disconnect drains accepted jobs.

Whisper processes completed utterances, simplifying one-turn dispatch. Streaming ASR suits captions/long speech; revised partials must never trigger tools. Piper streams PCM only after answer validation. STT uses bounded deadlines and at most one transient retry; authentication failures fail immediately. Midstream TTS failure stops playback and uses local recovery audio while retaining validated text. Expiring, admin-only controls demonstrate in-call failures; they are disabled by default.

Voice latency runs from the last captured frame identified as speech to the first scheduled browser audio sample. Server logs additionally separate endpointing, queue, STT, support and synthesis startup. Browser timing is an estimate, not a physical acoustic measurement. Interrupted/fallback responses must be reported separately.

## 5. Shared state and human support

Voice and text reuse the authenticated customer/session identity, bounded transcript, order context and turn contracts. Handoff changes `active → waiting_for_human → human_active`; AI dispatch pauses. An authenticated admin sees the summary and requested help, claims the chat and exchanges persisted messages with the customer. Human replies use Piper when voice is enabled. Ending the handoff sends an extractive resolution and resumes AI in the same session. Customer termination closes both sides; disconnect permits reconnection.

## 6. Scaling, extension and evaluation

For 10k concurrent sessions, scale async API workers behind a WebSocket-capable load balancer, retain shared session authority, separate bounded speech/embedding workers and enforce deployment-wide provider quotas/admission control. This is a deployment design, not a measured 10k-call result. Production also needs durable jobs, stronger identity, retention and agent assignment.

A fourth agent requires a registered handler, versioned routing schema/prompt/cache identity and new evaluation cases. Existing contracts/guards remain; implementation is deferred.

Evaluate held-out routing, ambiguity, grounding, ownership, refund claims, injections, speech/noise, adversarial interruptions and outages. Report routing macro-F1/confusion matrix, guardrail recall/false positives, grounding, tool authorization, cache hit rate, lost/duplicate turns and latency p50/p95/p99. A proposed healthy-call target is voice p95 <4 seconds, not an achieved SLO. Shadow routing changes, then use session-stable canaries with safety/latency rollback criteria.

Detect Groq degradation through latency, timeouts, 429/auth errors and queue age. Current recovery uses deadlines, bounded retries and local audio. Production circuit breakers and secondary-provider failover require additional work. Text bypasses STT failures, not chat-provider outages. Alternative models must pass the same safety/tool suites because routing, refusals and wording may change; failover must preserve authorization and turn IDs.

## 7. Evidence and limitations

Recorded regression evidence: 127 passing tests, six paced voice scenarios and a two-browser handoff/failure check. Automated voice checks use real VAD/Piper/Redis with explicitly scripted STT/LLM; they do not establish live Groq quality. Assess live reports/demo separately. See [validation](docs/handoff-validation.md), [demo instructions](docs/voice-demo.md) and [operations answers](docs/integration-and-operations.md).

Known weaknesses include overblocking harmless example credentials and conditional refund-template quotations. Semantic guards remain probabilistic. Fixed pause thresholds need testing across accents/languages; on-device VAD reduces transport/privacy costs but increases device variability, while server VAD centralizes tuning. Speakerphone echo, multilingual TTS and hard process-crash survival of queued audio are not solved. See [red-team findings](docs/red-team-findings.md). Final design is separate from the [decisions log](docs/decisions.md).
