# Reproducing Aegis Support

1. Apply the consolidation changes using the provided hash-checking updater. It backs up replaced/retired files and leaves the real .env, Git history and virtualenv untouched.
2. In the activated virtualenv, uninstall aegis-support-rag once and install the current project with pip install -e . so stale console entry points are replaced.
3. Start shared Redis using docker compose up -d. The existing project/volume names and Redis keys are preserved.
4. Keep current environment values; configs/environment.example documents them. GROQ_MODEL is a chat model. GROQ_STT_MODEL is reserved for transcription.
5. Start aegis-support chat or the HTTP API. All channels use the same SupportService and Settings.
6. Run tests with AEGIS_TEST_REDIS_URL set to an isolated development instance. Tests delete only their generated namespaces.
7. Use scripts/run_support_scenarios.py for live execution or add --scripted for deterministic provider doubles. Preserve which mode produced each result.
8. Use scripts/benchmark_support.py for storage/coordination measurements and scripts/evaluate_support.py --live for real model evaluation.
9. Preserve model identifiers, prompt hashes, dataset hashes, configuration and your actual Git commit with measured outputs. Never log real keys.

Knowledge-base content is unchanged in this refactor. Existing valid indexes need no rebuild. The previous decision record is retained unchanged under evidence/archive/baseline-validation/decisions.md. Earlier capacity run outputs were absent from the latest upload. Voice audio and barge-in testing will be added when the voice channel is implemented.
