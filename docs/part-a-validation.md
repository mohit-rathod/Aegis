# Actual Part A validation

## Passed

- 67 unittest cases passed, including the original 20 RAG tests.
- New tests exercised real Redis 6.2.14 for sessions, Lua/MSET commits, classifier cache/coalescing, idempotent replay, ownership denial, support persistence and terminal state shared by two service instances.
- HTTP API authentication/ownership was exercised with an in-process ASGI transport. Groq HTTP request contracts were checked with injected HTTP responses, not a live key.
- Python syntax, project TOML and JSON manifests parsed successfully.
- The original 15-document corpus loads with the revised policy hashes. No updated embedding index is shipped; users must rebuild it.
- Saved scripted-provider end-to-end responses and structured traces cover regex rejection, product dispatch, a cache repeat, status, eligibility, confirmed refund, unauthorized order, escalation and post-termination rejection.

## Measured capacity scope

Real ephemeral Redis, Python 3.12.14, one application process, scripted provider, no embedding inference, AOF disabled:

- Session records created: 10000.
- Session creation elapsed: 0.733 seconds.
- Active turns processed: 200 at client concurrency 16.
- Turn results: {'abstain': 200} (the fake product handler intentionally abstains).
- Classifier hit rate: 92%; one scripted classifier call and 15 coalesced misses.

The raw numbers are in evidence/runs/part-a-validation/capacity.json. These measurements are only local coordination/storage evidence. They are not 10k open connections or real Groq/RAG/voice throughput. Deployment compose enables AOF with appendfsync always, so these ephemeral-storage timings should not be treated as deployed persistence performance.

## Not run

No real Groq key was supplied. No live routing accuracy, input attack recall, output factuality, provider latency, or model tool-call quality is claimed. The live evaluator and development datasets are supplied to run with the user's account. No real human agent joins the demo. Part B audio/voice implementation remains outside this update.

## Known weaknesses

See red-team-findings.md for two observed component-level false positives and their scope. Arbitrary Python execution is outside the signed-approval threat model. Deployment-wide quotas, Redis HA and real identity remain production requirements, not completed capacity claims.
