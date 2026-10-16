# Decisions recorded during this implementation

Recorded at 2026-10-16T10:28:35.507737+00:00. These entries document actual choices in this patch; they do not fabricate earlier timestamps or Git history.

- Retained the original embedding RAG and introduced a separate async Part A assembly so legacy RAG tests remain usable while public interfaces share the new guarded pipeline.
- Selected native Groq function calls and a bounded two-round loop; discarded final model prose on transactional paths in favor of exact trusted-field rendering.
- Added process-local signed approval tied to immutable turn/context, plus independent tool ownership validation and a request-scoped evidence vault.
- Used shared Redis for assignment sessions/cache/intake. Production separation and HA remain documented operational work.
- Replaced an initial stream-based intake approach before delivery: a later stream write could fail after other business values were saved. The final version records session, response and intake together using one atomic MSET under a checked lease. Intake enumeration uses admin-protected SCAN rather than a second index.
- Kept cancelled embedding work counted until its actual thread finishes, so request cancellation cannot create an unbounded executor backlog.
- Moved HTTP test doubles to injected transports after the authoring environment's SOCKS proxy caused unrelated client-initialization failures. Production clients retain normal environment proxy behavior.
- Used a real ephemeral Redis 6.2.14 for authoring tests. Deployment compose targets Redis 7. No real Groq key was present, so no live quality or latency claims are made.
- Kept two explicitly observed conservative false positives; details and reproduction are in red-team-findings.md.
