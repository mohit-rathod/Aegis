# Voice and frontend validation

- 105 Python tests passed with no skips, including the original support regression suite, real ephemeral Redis 6.2.14, native Piper synthesis/cancellation, STT HTTP contract/retry/deadline checks, coordinator lifecycle, order correction and authenticated WebSocket checks.
- Six paced audio scenarios passed with real Silero VAD/Piper/Redis: silence, noise, interruption, false start followed by interruption, STT credential failure, and TTS failure after initial output.
- Silence/noise produced zero voice turns and zero speech interruptions. Each real-interruption case produced exactly one voice turn and requested the correct order reference.
- The Node frontend contract test passed: text/auth transport, capture framing/resampling without 48kHz drift, stop acknowledgment and stale output rejection.
- Chromium desktop/mobile checks passed with no page errors or horizontal overflow. It exercised actual browser AudioWorklet capture, WebSocket transport, PCM playback and shared business processing using a fake microphone device. The browser latency label is recorded in browser/browser.json.
- A wheel built successfully and contained frontend assets and bundled recovery WAVs. Large models are external setup assets with pinned hashes.

## Timing evidence and limits

The fixture replay used a paced virtual audio sink and scripted STT/LLM. Its server-estimated last-speech-frame-arrival-to-first-audio-send measurement had two substantive samples: p50 2277.14ms and p95 2296.20ms. These reflect native VAD/Piper startup plus scripted business processing, not live Groq latency. Virtual stop acknowledgments are not physical interruption-stop measurements. The browser report separately records a client capture-to-scheduled-playback estimate; one browser run is not a percentile study.

No physical microphone, live Groq recognition/generation quality, accent/language coverage, PSTN line or 10,000 concurrent calls was tested here. The production browser path calls Groq; only explicit test runners inject substitutes. Follow voice-demo.md to record a live run with your credentials and microphone.

Raw output and mode labels are in evidence/runs/voice-validation/: tests.txt, traces.jsonl, scenarios.json, browser-console.txt, browser/browser.json, frontend-contract.txt, latency-summary.txt, cli-help.txt, versions.json and summary.json. Current source hashes are recorded in summary.json. Screenshots were used only for local QA and are not shipped.
