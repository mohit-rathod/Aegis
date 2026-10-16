# Reproducing Part A

1. Apply only patch files after reviewing changes.json. Keep the real .env and Git history.
2. Install updated dependencies with `python -m pip install -e .`.
3. Start Redis with `docker compose -f compose.part-a.yaml up -d`.
4. Merge .env.part-a.example settings into .env. Retain HF_TOKEN and GROQ_API_KEY. Use a chat model, not Whisper, for GROQ_MODEL.
5. Rebuild the index with `aegis-rag build-index`; the old source fingerprint is stale after the two policy updates.
6. Run `aegis-support chat --customer customer-a`, or the ASGI API with two workers and configured distinct demo tokens.
7. Pin AEGIS_DEMO_AS_OF=2026-10-16 for the static order fixtures. The model cannot set the trusted clock through a tool argument.
8. Run tests with AEGIS_TEST_REDIS_URL set. They create/delete only their own generated namespaces and do not FLUSHDB.
9. Run scripts/run_part_a_scenarios.py with --scripted for repeatable structural traces, or without that flag for actual Groq and embeddings.
10. Run scripts/run_part_a_evaluation.py --suite all --live for real model evaluation; this consumes account quota. Preserve model, prompt hashes, dataset hashes, Git commit and configuration with results.
11. Run scripts/load_test_part_a.py for session-record and scripted-turn coordination. It is not a live-provider benchmark.

Use an isolated Redis database/prefix for evaluation. The test scripts remove their temporary namespaces, but normal CLI/API sessions and escalations persist. Never put real keys in evidence. Raw human audio is not supplied by Part A and must be recorded separately for Part B.
