# Aegis Support Assistant

A single customer-support application with guarded three-intent routing, embedding-based knowledge retrieval, authorized order tools, persistent escalation and shared session state. Text interfaces are implemented. Voice will extend the same runtime and conversation service.

## Setup

From the existing project root, activate your virtual environment. The package distribution is now aegis-support. Replace the previous installed distribution once, then install the current project:

```bash
source .venv/bin/activate
python -m pip uninstall -y aegis-support-rag
python -m pip install -e .
docker compose up -d
```

Keep your existing .env. Its variable names are unchanged. configs/environment.example is a reference, not a file to copy over existing keys. Use a chat/tool-capable Groq model for GROQ_MODEL and Whisper only for GROQ_STT_MODEL. Demo HTTP tokens must be distinct and configured server-side.

## One CLI

```bash
aegis-support chat --customer customer-a
aegis-support ask "Which filter fits Pure Plus?"
aegis-support metrics
aegis-support build-index
aegis-support retrieve "Which filter fits Pure Plus?"
```

The older aegis-rag command is a compatibility alias to the same CLI, not another implementation. ask starts a fresh session; chat supports follow-ups and terminates after successful escalation. retrieve is developer inspection only; it does not answer customer messages or bypass the guarded support path.

The consolidation does not change knowledge-base bytes, embedding settings or Redis key names. Rebuild the index only if it is missing or your local KB/model settings differ.

## API

```bash
uvicorn support_assistant.entrypoints.api.app:app --host 127.0.0.1 --port 8000 --workers 2
```

POST /sessions uses a server-configured demo bearer token. POST /sessions/{session_id}/messages accepts turn_id, text and optional channel. Identity comes from the bearer token, never chat text. Identical turn retries replay the saved response; conflicting reuse is rejected. /health and /ready provide local health checks. /admin/classifier-metrics and /admin/support-requests require the configured admin token.

## Verification and tooling

```bash
AEGIS_TEST_REDIS_URL=redis://127.0.0.1:6379/0 python -m unittest discover -s tests -v
python scripts/run_support_scenarios.py --scripted
python scripts/benchmark_support.py --sessions 10000 --turns 200 --concurrency 16
python scripts/evaluate_support.py --suite all --live
python scripts/evaluate_retrieval.py
```

The scripts use neutral capability names. Live evaluation consumes real Groq quota. Scripted tests measure control flow, authorization and storage behavior, not model accuracy. Current validation lives in evidence/runs/support-validation/.

## Project organization

- config.py and bootstrap.py: shared configuration and runtime construction.
- application/: one guarded conversation service and response boundary.
- agents/: product, order and human-escalation handlers.
- rag/, tools/, safety/: support capabilities and enforcement.
- adapters/: Groq, embeddings, Redis, and future speech integrations.
- entrypoints/: CLI and HTTP channels.
- voice/: reserved for the future voice coordinator.

The exact approved refund and escalation messages, tool ownership checks, cache behavior and chat termination rules remain unchanged. Escalation persists demo support intake; no live human connection or payment execution is implemented. See docs/architecture.md, docs/support-design.md and docs/limitations.md for details.
