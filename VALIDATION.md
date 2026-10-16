# Validation performed

- Loaded all 15 original Aegis documents and verified their manifest hashes.
- Ran `PYTHONPATH=src python3 -m unittest discover -s tests -v`: **20 tests passed**.
- Parsed all 38 Python files with Python's AST parser successfully.
- Executed CLI `--help` successfully.
- Checked the final ZIP for corrupt members and verified source document bytes match the earlier Aegis pack.

Tests cover manifest path containment, source hashes, chunk identities and token-budget checks, normalized index storage and round-trip loading, stale-index rejection, parent-document deduplication, invalid citations, empty claims, input rejection/failure, output rejection/failure, generation call order, no-hit abstention, tool-required responses, and malformed input-check output.

The offline tests use deterministic fake embedding/model adapters. No embedding model download, live Groq call, real semantic retrieval benchmark, guardrail recall study, or voice latency measurement was performed. The authoring environment did not have sentence-transformers installed and no user Groq key was supplied. No live benchmark result is claimed. Install the declared dependencies and use the included retrieval/answer evaluation commands to validate the selected models on your machine.

The threshold is an uncalibrated starting value. The original evaluation seeds are development data and contain a few imperative safety probes that may legitimately be blocked rather than answered. Review labels for the combined safety policy before interpreting response-status agreement. The input/output gates are probabilistic and require red-team testing; citation validation alone is not factuality verification.
