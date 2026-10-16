# Demonstrating the support line

## Start

Preserve .env. Configure GROQ_API_KEY, a chat-capable GROQ_MODEL, GROQ_STT_MODEL=whisper-large-v3-turbo, and nonempty distinct demo customer tokens. In the activated virtual environment:

```bash
python -m pip install -e '.[voice]'
python scripts/setup_voice.py
docker compose up -d
aegis-support serve 2> var-voice-trace.jsonl
```

Open http://localhost:8000. Enter AEGIS_DEMO_CUSTOMER_A_TOKEN's value, click Connect, and send text. Click Start voice and grant microphone permission. Use a headset. In WSL, open the page in your Windows browser: the microphone belongs to that browser, not the Python process. Remote access needs HTTPS. This is a support-line-style web call, not a PSTN carrier integration.

## Live recording checklist

1. Ask 'Where is order AEG-1001?' and stay silent through playback. No extra transcript should appear.
2. Repeat and make a short tap/click during playback. Playback should continue.
3. Repeat and say 'Wait, wrong order.' Playback should stop, exactly one interruption should be transcribed, and the correct order reference should be requested.
4. Repeat with a brief false start, pause, then the real interruption. Confirm one finalized interruption and no stale audio.
5. Stop voice during playback. Microphone tracks and queued audio stop; text remains available.
6. Ask for a human. Confirm the exact escalation message and session closure.

Use the Call events panel and terminal JSONL trace. Record your actual microphone/Groq run instead of relabeling supplied scripted evidence. The response latency label is a capture-to-scheduled-playback estimate, not a physical speaker measurement.

## Repeatable scenario evidence

```bash
python scripts/run_voice_scenarios.py --scripted
python scripts/summarize_voice_latency.py var/evaluation/voice/traces.jsonl
python scripts/run_voice_scenarios.py --live
```

The six scenarios are silence, short noise, real interruption, false-start-then-interruption, STT 401 and TTS failure after its first chunk. Scripted mode uses real Silero/Piper/Redis with explicit STT/LLM doubles and a paced virtual audio sink. Live mode uses Groq for ordinary requests, retaining isolated injected failure cases. It needs your index and consumes quota. Both modes emit per-scenario assertions and transcripts. Synthetic fixtures are not accent evaluation data. Fault wrappers are runner-only, not remotely accessible controls.

## Tests

```bash
AEGIS_TEST_REDIS_URL=redis://127.0.0.1:6379/0 AEGIS_TEST_PIPER_MODEL=var/models/en_US-lessac-medium.onnx python -m unittest discover -s tests -v
node tests/frontend/check_frontend.mjs
```

Set both variables to include real Redis/native synthesis checks; otherwise those tests skip. Use a development Redis instance. Optional browser check:

```bash
python -m pip install playwright
python -m playwright install chromium
AEGIS_TEST_REDIS_URL=redis://127.0.0.1:6379/0 python tests/frontend/browser_smoke.py
```

This exercises desktop/mobile layout and real browser capture/worklet/WebSocket/playback with Chromium's fake microphone, real Silero/Piper/Redis and scripted STT/LLM. It does not test physical hardware or live Groq. browser.json records the test mode and page errors; screenshots are local QA output.
