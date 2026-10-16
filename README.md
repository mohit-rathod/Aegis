# Aegis: document-aware semantic RAG

This is the RAG portion of the customer-support assignment. It includes the exact 15 fictional Aegis documents previously supplied, a local dense retrieval index, Groq answer generation, semantic input/output checks, a CLI, development evaluation runner, and deterministic offline tests. It is not the complete router, order-tool, voice, cache, or session application.

## Why this methodology

Use small embedding passages for matching and full parent documents for answer context. Policy exceptions stay with the policy. This is practical for 15 short documents and avoids a vector database, framework, reranker, or additional search provider. Retrieval uses embeddings, not keyword search.

Flow: verified manifest -> YAML metadata removal -> token-window child chunks with titles -> normalized local embeddings -> NumPy cosine search -> top three unique parent documents -> structured Groq claims with source IDs -> deterministic citation checks -> semantic output verification -> rendered answer. Input safety runs before retrieval or generation. Insufficient evidence returns an abstention; live order questions return tool_required rather than fabricated data.

## Run in a new folder (Bash / WSL)

Use Python 3.11 or newer. Run from this extracted package root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
cp .env.example .env
```

Edit `.env`: set your Groq key and an active account-accessible Groq chat model supporting JSON object mode. The adapter uses the Groq OpenAI-compatible endpoint with JSON object mode, then validates the response locally with strict Pydantic models. JSON syntax mode alone does not enforce the schema. No real key is included. The embedding model downloads on first use; retrieval needs internet for that initial download, then can use the local model cache.

```bash
aegis-rag build-index
aegis-rag retrieve "Can I connect Pure Mini to Wi-Fi?"
aegis-rag ask "Can I connect Pure Mini to Wi-Fi?"
aegis-rag ask "Does being eligible for a return mean my refund is approved?"
aegis-rag ask "What is the live delivery status of AEG-1001?"
```

`build-index` and `retrieve` do not require a Groq key. `ask` performs up to three Groq calls: input gate, grounded generation, output verification. Abstentions and blocked requests may use fewer. This deliberately prioritizes traceability over minimum voice latency. Each provider request has a configurable timeout; this module makes no automatic retries. The total turn can span several per-call timeouts. A voice integration should add an overall turn deadline and discard obsolete generation results.

`retrieve` is a development inspection command, not a public support endpoint: it does not call the input gate or generate an answer. Expose `GuardedRAGService.handle()` to the application, not this inspection command or the raw agent.

## Integrate into the existing project

This package follows the proposed `src/support_assistant/` structure. Merge the implemented files into the existing scaffold. Review existing changes before replacement, particularly `bootstrap.py`, `config.py`, and `application/support_service.py`. Merge dependencies into an existing pyproject rather than overwriting a working project definition. Preserve unrelated voice, tools, and router files.

The public integration is:

```python
from support_assistant.config import Settings
from support_assistant.bootstrap import build_service

service, provider = build_service(Settings.from_env())
try:
    result = service.handle("Which filter fits Pure Plus?")
    print(result.model_dump())
finally:
    provider.close()
```

Construct once per worker/process and reuse, not once per message. The code is synchronous. An async voice coordinator must run blocking inference/network work off its audio event loop, for example using `asyncio.to_thread`, and enforce its own generation IDs; cancelling that await does not cancel underlying blocking work. Do not send `AnswerDraft` to TTS. Only deliver the final guarded response.

When merging with the full multi-agent application, keep one input gate before router/dispatch and one final output gate before delivery. Refactor the standalone service's guard ownership deliberately to avoid double-checking or accidentally bypassing checks. Order ownership and tool authorization remain in the order-tool path; semantic RAG cannot establish identity. A tool_required response here does not actually execute a tool or create a handoff.

## Index correctness

Only manifest-listed Markdown files are embedded. Front matter, evaluation answers, README files, internal prompts, and source code are excluded. SHA-256 hashes must match the supplied manifest. Paths cannot escape the KB directory. Chunk text preserves its document identity; generated answers cite document IDs, not arbitrary filenames.

The model tokenizer creates token-bounded passages with overlap; encoding explicitly rejects overlength input rather than silently truncating. The title and special-token budget are checked. Long queries can also be rejected safely. Index storage uses NumPy with pickle disabled, finite normalized vectors, and atomic file replacement. Model/revision, chunk settings, source fingerprint, dimensions, build date, and embedding-library version are stored with the index.

Treat the KB as immutable during a running process. If you edit a document, update its manifest hash, rebuild the index, and restart workers. Startup rejects stale indexes. Pin `AEGIS_EMBEDDING_REVISION` to a model commit for reproducibility; `main` is only a convenient development default and can change. Lock dependencies in your final repository after installation, e.g. with your chosen package manager. This deliverable contains dependency ranges, not a generated lockfile.

## Tests and evaluation

```bash
python -m unittest discover -s tests -v
python scripts/run_evaluation.py
python scripts/run_evaluation.py --answers
```

The tests use deterministic fake embeddings and model responses. They verify structural behavior, not real semantic retrieval quality or attack recall. Evaluation uses the actual downloaded embedding model; `--answers` additionally requires Groq and makes live calls. Results go to `var/evaluation/aegis-results.json`; use `--output evidence/runs/YOUR-RUN-ID/evaluation-results.json` to preserve a run for submission.

Reported retrieval metrics: document hit@k, recall@k over listed relevant documents, and MRR@k. The response-status metric is only a development behavior check. It does not establish factual correctness; inspect the returned claims against their evidence. The original seed includes adversarial imperatives whose expected behavior may need to be relabeled as blocked when evaluating this input policy. Preserve original labels, report disagreements, and create a separately reviewed combined safety/answer oracle rather than tuning away failures.

The initial similarity cutoff 0.25 is NOT calibrated and is NOT a confidence probability. Tune it and top-k on development data, freeze settings, then evaluate fresh held-out questions. Questions whose answer is 'not documented' can still correctly retrieve a document that explicitly says that. Do not treat every abstention as a retrieval miss.

## Safety and production limitations

Citation membership is checked deterministically. Factual support and injection detection are probabilistic LLM judgments; using the same model for generation and verification can produce correlated mistakes. A valid citation is not proof of entailment. The module fails closed when required checks throw or emit invalid structures. It cannot guarantee that every malicious or unsupported claim is detected. Conduct genuine red-team testing before making safety claims.

No broad chat history is embedded or accepted as authority. Model names, product features, and policy exceptions must come from retrieved documents. Live order facts, authorization, refunds, guarantees, or ticket completion cannot come from this static corpus. Generic failed-check responses do not assert that escalation actually occurred.

For a production service, add a trusted identity/session layer, bounded worker admission, turn deadlines, provider resilience and observability around this module. Do not deploy the debug retrieval command publicly. Do not claim 10k-session capacity or measured real-provider accuracy based on the included offline tests.

## Validation in the authoring environment

See `VALIDATION.md` for actual checks performed. Real embedding-model downloads and live Groq calls were not available for validation in that environment; no retrieval or latency results are fabricated.
