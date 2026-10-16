# Aegis Support Assistant

## Demo video

https://github.com/user-attachments/assets/ab557447-2d90-4946-895c-746ea4dac8d0

One customer-support application with text and voice input, a three-intent Groq router, embedding-based product answers, authorized order tools, classifier caching and live human-support handoff. FastAPI serves the basic frontend; no separate frontend build is needed.

Read [ARCHITECTURE.md](ARCHITECTURE.md) for the request flow and file responsibilities.

## 1. Prerequisites

- Python **3.11+**; the regression suite was run with Python 3.12.
- Docker with the Compose plugin, or an existing Redis instance.
- A Groq API key with access to a chat/function-calling model and Whisper transcription.
- Internet access for the first embedding/speech model downloads.
- A microphone and a recent browser for voice. Use a headset. On WSL, open the app in your Windows browser; Python does not need access to the Windows microphone.

The commands below use Bash on Linux/WSL and must run from the project root, which contains `pyproject.toml` and `compose.yaml`.

## 2. Create the environment and install

After cloning or extracting the project, open a terminal in its root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[voice]'
```

For CLI text only, install with `python -m pip install -e .` instead. The browser's duplex channel needs the WebSocket dependency included in the voice extra. Node is needed only for the optional frontend contract test.

## 3. Configure credentials

For a **new checkout without `.env`**, copy the template:

```bash
cp -n configs/environment.example .env
```

If `.env` already exists, keep it and merge only missing settings. Edit these values:

| Setting | Value/purpose |
| --- | --- |
| `GROQ_API_KEY` | Your Groq key. |
| `GROQ_MODEL` | A chat/tool-capable model enabled in your account; the template contains an example. Never use Whisper here. |
| `GROQ_STT_MODEL` | `whisper-large-v3-turbo` for audio transcription. |
| `HF_TOKEN` | Optional authentication for public embedding-model downloads; set your Hugging Face token if needed. |
| `AEGIS_DEMO_CUSTOMER_A_TOKEN` | A random nonempty browser/API token for `customer-a`. |
| `AEGIS_DEMO_CUSTOMER_B_TOKEN` | Optional second customer's token; it must differ from customer A's token. |
| `AEGIS_ADMIN_TOKEN` | Separate admin token, required for human chat; it must differ from every customer token. |
| `AEGIS_REDIS_URL` | Defaults to `redis://127.0.0.1:6379/0`. |
| `AEGIS_DEMO_AS_OF` | Keep `2026-10-16` to reproduce the dated order-fixture examples. Empty uses the current date in Asia/Kolkata. |

Generate a fresh token for each role you enable:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

The rest of the configuration is documented in `configs/environment.example`. `.env` is loaded from the **current working directory**. Exported shell variables take precedence; changing `.env` will not replace an already exported value. Restart the application after configuration changes. Keep real secrets out of source control and logs.

## 4. Start Redis and build the retrieval index

```bash
docker compose up -d
docker compose exec redis redis-cli ping
aegis-support build-index
aegis-support retrieve "Which filter fits Pure Plus?"
```

The Redis command should return `PONG`. Index creation downloads the local embedding model on first use and writes `var/indexes/aegis/`. Retrieval should list KB documents, including filter compatibility.

**Build the index before starting the API or conversation CLI on a fresh checkout.** Runtime startup validates the index against the KB and embedding configuration. Rebuild when KB contents, embedding model/revision or chunk settings change. Existing compatible indexes can be reused.

Compose starts Redis only. Python runs the application; there is no application Docker image in this repository.

## 5. Start the browser support line

Download the VAD/Piper models once, then start the application:

```bash
python scripts/setup_voice.py
aegis-support serve
```

Open **http://localhost:8000**:

1. Enter the value of `AEGIS_DEMO_CUSTOMER_A_TOKEN` and click **Connect**.
2. Use **Send text** to ask a product/order question.
3. Click **Start voice**, allow microphone access and speak. You can interrupt while the assistant speaks.
4. Click **Stop voice** to release the microphone while keeping text available. **Disconnect** ends the connection.

The browser token is cleared from the input after connection and is not stored in the URL or local storage. Text and voice use the same session and guarded support service. Voice runs browser capture → backend VAD/endpointing → Groq Whisper → shared support service → Piper → browser playback.

Try:

- `Which filter fits Pure Plus?`
- `Where is AEG-1001?`
- `Can I return AEG-1003?`
- `Has the refund for AEG-1008 been approved?`
- During playback: `Wait, wrong order.`
- `I want to speak to a human.`

A successful escalation pauses AI replies. Open **http://localhost:8000/admin**, sign in with `AEGIS_ADMIN_TOKEN`, select the handoff and click **Join chat**. The admin sees its summary and requested help before replying. Customer and admin messages are shared; human replies are spoken when customer voice is enabled. **End human chat and return to AI** sends an extractive resolution and resumes the same AI session. Customer **End conversation** closes both sides. **Disconnect** preserves the session for reconnection. Customer A cannot access customer B's `AEG-1007` order.

Speech models are checksum-verified setup downloads, not bundled weights. Missing speech assets do not prevent text support. Remote microphone access requires HTTPS; localhost works for development. This is a web support-line demo, not a PSTN integration.

## CLI and HTTP alternatives

```bash
aegis-support chat --customer customer-a
aegis-support ask "Can I wash the HEPA cartridge?"
aegis-support metrics
```

`chat` keeps session context; `ask` starts a fresh session each time. `retrieve` inspects embeddings for development and does not answer customer messages. `aegis-rag` is an alias of the same CLI. `aegis-support voice` starts the same frontend as `serve`.

The API runs on the same server. Open `/docs` for its HTTP schema.

| Endpoint | Authentication/purpose |
| --- | --- |
| `GET /health`, `GET /ready` | Process/Redis health. Startup must already have succeeded. |
| `POST /sessions` | Customer bearer token; returns a new session ID. |
| `POST /sessions/{id}/messages` | Same customer's token; body contains `turn_id`, `text`, optional `channel`. |
| `WS /sessions/{id}/channel` | Browser text/voice; first message authenticates the token. |
| `GET /admin/classifier-metrics` | Admin token; hit/miss/coalescing counters. |
| `GET /admin/support-requests` | Admin token; waiting/active human handoffs. |

HTTP retries must reuse the same `turn_id` **and** message. Conflicting reuse is rejected. Identity comes from server configuration, never chat text.

## Tests and evaluations

Use a development Redis instance. With your virtual environment active:

```bash
AEGIS_TEST_REDIS_URL=redis://127.0.0.1:6379/0 \
AEGIS_TEST_PIPER_MODEL=var/models/en_US-lessac-medium.onnx \
python -m unittest discover -s tests -v
```

Redis/native synthesis tests skip when their respective variables are absent. Most regression tests inject provider doubles; they do not need a live Groq key or a downloaded embedding model. The native Piper tests require the speech model from setup.

```bash
python scripts/run_support_scenarios.py --scripted
python scripts/run_voice_scenarios.py --scripted
python scripts/summarize_voice_latency.py var/evaluation/voice/traces.jsonl
node tests/frontend/check_frontend.mjs
```

Scripted voice scenarios use real VAD/Piper/Redis with scripted STT/LLM and a paced virtual audio sink. For real-provider evaluation, the following commands consume Groq quota:

```bash
python scripts/run_voice_scenarios.py --live
python scripts/evaluate_support.py --suite all --live
python scripts/evaluate_retrieval.py
```

Retrieval evaluation uses the embedding model/index; `--answers` additionally exercises live support answers. `benchmark_support.py` measures scripted storage/coordination, not 10,000 live voice calls. See [voice demo](docs/voice-demo.md) for microphone recording and optional Playwright checks, and [evaluation guide](evaluation/README.md) for datasets/outputs.

For Python lint and formatting:

```bash
python -m pip install -e '.[dev]'
ruff check src scripts evaluation tests
ruff format --check src scripts evaluation tests
```

Optional frontend formatting (Node/npm required only for this check):

```bash
npx --yes prettier@3.6.2 --check 'src/support_assistant/entrypoints/web/*' tests/frontend/check_frontend.mjs
```

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Missing/stale index at startup | Run `aegis-support build-index` from the project root. |
| Redis connection refused | Start Compose, wait for `PONG`, check `AEGIS_REDIS_URL`/port 6379. |
| Browser/API authentication fails | Set a nonempty customer token, restart the server and enter that token—not the Groq key. |
| Groq HTTP 400 / unavailable answers | Check that `GROQ_MODEL` supports chat/tool calling; Whisper belongs only in `GROQ_STT_MODEL`. Inspect categorized terminal events. |
| Hugging Face unauthenticated warning | Check `.env` location and `HF_TOKEN`; restart, and check for stale exported environment values. |
| Microphone unavailable | Use localhost/HTTPS, allow browser permission, select the right device and try a headset. |
| Voice setup or playback fails | Install `.[voice]`, run `scripts/setup_voice.py`, verify configured model paths and inspect the recovery/category event. Text remains available. |
| Waiting after asking for a human | Open `/admin` with the separate admin token and join the handoff. AI replies resume when the admin ends it. |

## Scope and evidence

Orders are read-only fixtures. Eligibility does not execute a refund. The refund-initiation message requires confirmed fixture state; the included admin console connects an operator to the customer. Staffing, production identity and access control remain deployment responsibilities. English TTS, acoustic endpointing and headset use are the demonstrated baseline.

Saved evidence distinguishes scripted providers, synthetic/fake microphone input and live runs. Historical logs are preserved as history. The cleanup verification is in [docs/cleanup-validation.md](docs/cleanup-validation.md); [limitations](docs/limitations.md) describes deployment gaps. Dependency ranges are declared in `pyproject.toml`, not a complete lockfile; retain actual versions and model identifiers with measured runs.

Stop the Python server with Ctrl+C. `docker compose stop` stops Redis while keeping its persisted data.

## Running-call failures and live measurement

For an explicit local failure demonstration, add `AEGIS_ENABLE_DEMO_FAULTS=true` to `.env` and restart. In `/admin`, open **Local demo failure controls**, paste the customer's displayed session ID, choose a one-shot failure and arm it during the conversation. See [voice-demo.md](docs/voice-demo.md) for the exact scenarios and timing boundaries. Leave this setting false outside demonstrations.

The customer interface shows client end-to-first-audio latency plus endpointing, queue, Whisper, support/Groq and first Piper chunk timings. These are measured values for the selected response, not predicted provider speed. Text-only and failed turns are labeled separately.

```bash
python scripts/evaluate_live_system.py --live --retrieval --answers
```

This consumes actual Groq quota and writes a consolidated report under `var/evaluation/live-system/`. No live Groq scores or physical-microphone evidence are bundled with this update. Detailed state transfer, production evaluation/rollout and outage tradeoffs are in [integration and operations](docs/integration-and-operations.md).

**Updating an existing checkout:** rebuild the retrieval index after applying this update because the human-support KB document changed: `aegis-support build-index`. Keep your `.env`, models and Redis data; no reset is required. Existing terminated sessions stay terminated.
