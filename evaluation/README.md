# Evaluation tools

Run commands from the project root in the installed virtual environment. Build the retrieval index first when running retrieval or full support answers.

| Command | Purpose | Requirements |
| --- | --- | --- |
| `python scripts/evaluate_retrieval.py` | Hit@k, recall@k and reciprocal rank over `aegis_grounding_seed.jsonl`. | Embedding model + compatible index. |
| `python scripts/evaluate_retrieval.py --answers` | Also obtain full guarded answers for manual factuality review. | Above + Redis/Groq. |
| `python scripts/evaluate_support.py --suite all --live` | Routing/ambiguity, safety, tool authorization and cache checks. | Redis/Groq; live calls consume quota. |
| `python scripts/run_support_scenarios.py --scripted` | Deterministic business-path walkthrough. | Redis; explicit LLM doubles. |
| `python scripts/run_voice_scenarios.py --scripted` | Six paced interruption/recovery scenarios. | VAD/Piper models + Redis; scripted STT/LLM and virtual playback. |
| `python scripts/run_voice_scenarios.py --live` | Same voice fixtures using real ordinary Groq requests, plus injected failure cases. | Above + index/Groq. |
| `python scripts/summarize_voice_latency.py var/evaluation/voice/traces.jsonl` | Count, p50 and p95 grouped by timing definition. | Existing JSONL trace. |
| `python scripts/benchmark_support.py --sessions 10000 --turns 200 --concurrency 16` | Session storage/coordination measurement. | Redis; scripted providers, not production call capacity. |

`evaluation/runners/grounding.py` and `support.py` contain the actual evaluators. Datasets are development seeds; results are not independent held-out model-quality guarantees. See each command's `--help` for output paths, and `docs/voice-design.md` for latency definitions. Physical microphone testing is a separate browser demonstration. `scripts/run_evaluation.py` remains a compatibility alias for retrieval evaluation.

## Consolidated actual-provider evaluation

`python scripts/evaluate_live_system.py --live --retrieval --answers` writes `support.json`, optional `retrieval.json`, `summary.json` and `REPORT.md` under `var/evaluation/live-system/`. It requires the real Groq key, Redis and (for retrieval) a rebuilt index. Provider failures leave the report incomplete and exit nonzero; do not interpret them as measured semantic quality. Cache mechanics, fake providers and synthetic audio are labeled separately. See `docs/integration-and-operations.md` for held-out-set expansion, SLO proposals and rollout policy. Physical-microphone/end-to-audio evidence must be recorded on the actual browser/provider pipeline.
