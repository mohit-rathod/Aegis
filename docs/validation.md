# Validation

## Current source

- 70 unittest cases passed with real ephemeral Redis 6.2.14.
- Coverage includes shared configuration, the unified runtime serving both product and order requests, the full input/router/generation/output call sequence, API identity, authorization, cache/coalescing, signed dispatch, refund wording, escalation persistence, termination and retry behavior.
- The previous synchronous component checks were migrated to the single async guard/generation interfaces; no second conversation service remains for tests.
- CLI help and the renamed evaluation runner execute successfully.
- Knowledge-base files, source hashes and embedding settings are unchanged; no index rebuild is required by this refactor alone.
- The original decision record is preserved unchanged. Earlier capacity run outputs were absent from this source upload and are not recreated.
- New scripted-provider scenario traces and outputs are under evidence/runs/support-validation/.

## Scope

The provider and embedding substitutes in tests are explicit. Real Redis is exercised, and the Groq HTTP request contract is tested with injected HTTP responses. No live Groq key was supplied, so model accuracy, recall and provider latency were not measured. No new capacity measurement was performed in this update. The documented architecture and benchmark script do not establish 10,000 concurrent live-provider requests.

## Migration

The changes-only updater checks original file hashes before modifying or retiring modules. It preserves the existing .env, Git history, virtualenv and unrelated files. Superseded scripts omitted from the upload are retired only if they match the previously delivered versions; locally modified scripts produce a conflict rather than being silently overwritten. New script names are capability-based.

## Voice/frontend extension

See voice-validation.md for the current combined regression suite, real native speech components, six paced scenarios and Chromium results. The original consolidated text regression cases are included in that suite.
