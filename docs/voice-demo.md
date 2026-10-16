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

## Current running-call demonstration

Run the application with your real Groq key, built index and downloaded Silero/Piper models. The customer page must report `live_groq_whisper_chat_piper`; a scripted test explicitly reports a different mode. Enable voice, ask an order question and listen to the actual response. Record the browser plus categorized terminal logs. Browser fake-device tests are regression evidence, not this physical-microphone demonstration.

Record silence through full playback; a short tap/noise burst that should not interrupt; “wait, wrong order” that should stop speech and submit exactly one new turn; and a false start followed by real speech. Use a headset to reduce playback echo. Include turn IDs and acceptance/outcome events so cancellation of old audio can be distinguished from processing the new turn.

For provider resilience, set `AEGIS_ENABLE_DEMO_FAULTS=true`, restart, open `/admin` and sign in with the separate admin token. During an ongoing customer session, paste its displayed session ID into Local demo failure controls:

- `stt_transient`: arm, then speak. One injected transient timeout is followed by a bounded attempt to actual Groq Whisper. Logs show `stt_retry`, then transcription or explicit recovery.
- `stt_auth`: arm, then speak. Only this actual STT request uses an invalid credential. It fails without auth retries, plays local recovery and invites typed input. The next turn uses the original key. No permanent credential changes are made.
- `tts_midstream`: arm, then ask for sufficiently long order details with voice enabled. Actual Piper audio begins; after at least 0.6 seconds of generated PCM, synthesis fails, playback stops and the prerecorded recovery message plays. The validated answer remains on screen. The following turn still works.

One-shot controls expire after five minutes, require admin authorization and are disabled by default. Do not arm multiple different STT faults for the same demonstration. An actual provider outage can also be demonstrated by blocking its network, but avoid changing shared credentials or severing Redis. A failed retry must end with an explicit outcome, never an indefinitely spinning UI.

## Latency boundaries

For voice, end-to-end client latency starts at the browser capture timestamp of the last frame VAD identifies as speech and ends at the Web Audio scheduled start of the first response sample. It includes trailing-silence endpointing, transport, queueing, Whisper, support/Groq checks and response generation, Piper startup and browser audio scheduling. It is an operational estimate of audible onset, not a hardware measurement of the last acoustic phoneme or speaker output. Capture callbacks and output-device buffering can add uncertainty. For text, the origin is submission and the metric is labeled accordingly; text-only responses have no first-audio value.

The frontend shows current response timing and stage metrics. `voice_latency` logs report server endpoint, queue, STT, support and first-chunk times. Browser latency reports carry a server-known playback ID and turn ID; client measurements remain untrusted telemetry. Server first-chunk latency ends before network/playout and is a different metric. Do not add server and client totals or compare their monotonic clocks directly. Exclude interrupted playback from successful-response percentiles and report it separately, along with failures and fallback frequency. Repeated physical-microphone runs provide a distribution; a single recording is one sample.

For human support, open `/admin` before requesting escalation: the chat stays hidden until a real ticket exists. Join it, exchange messages, then end human chat to demonstrate the resolution and AI resumption. With customer voice enabled, human replies and the resolution are synthesized. Customer End conversation stops both sides; Disconnect preserves reconnection.
