# Voice and human-handoff validation

Validated 2026-10-16 with Python 3.12, a real isolated Redis 6.2 instance, ONNX Silero VAD and native Piper. Provider doubles are explicit below. No real Groq credentials or physical microphone were available; this evidence does not claim live model accuracy, human-speech quality, production SLO attainment or 10k active-call capacity.

| Check | Result and boundary |
| --- | --- |
| Python regression suite | 127 tests passed, including real Redis/native Piper; no skips in this run. |
| Accepted-turn lifecycle | Three accepted turns retain FIFO order despite newer input; pending duplicates do not dispatch twice; graceful disconnect drains accepted jobs; overflow is explicitly rejected. Hard process-crash durability remains a deployment gap. |
| Human handoff | Summary/help/verified context; customer/admin isolation; claim required; bidirectional messages; idempotent admin reply; extractive resolution; AI resume; re-escalation; customer closure; late admin rejection. |
| Native running-turn recovery | Actual Piper produces audio, the one-shot midstream fault stops it and uses recovery; the following turn completes. Cancellation reaps workers and drains pipes. |
| Chromium two-page check | Fake microphone with real VAD/Piper/Redis and scripted STT/LLM. Customer text/voice, displayed latency, admin handoff, real Piper human reply, mid-call failure controls, AI resume and customer closure passed. No page errors or mobile horizontal overflow. |
| Paced voice scenarios | All six passed: silence, short noise, interruption, false start then interruption, STT failure, TTS failure. Real VAD/Piper; scripted STT/LLM and virtual playback. |
| STT adapter | HTTP mock verifies one-request invalid credential isolation, transient timeout followed by retry, multipart WAV contract, auth no-retry and bounded deadlines. These are not actual Groq results. |
| Frontend contract | Node check passed microphone framing/resampling, auth, playback stop acknowledgment and stale audio rejection. |
| Static checks | Ruff lint/format and Prettier checks passed. |

Current text/JSON logs are under `evidence/runs/handoff-validation/`. Screenshots were used only for internal visual QA. Historical evidence elsewhere remains historical. Tests use fake credentials and fixture orders, never real customer accounts.

For real provider results, follow README's live evaluation command. For physical microphone recordings and actual Groq Whisper/Groq latency, follow `docs/voice-demo.md`. Each run must retain its provider mode; do not relabel scripted scores as live measurements.
