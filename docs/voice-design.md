# Voice channel

One Settings, Runtime and SupportService serve text and voice. The coordinator is a channel adapter, not another router. The browser uses one authenticated session for both input modes.

## Components

FastAPI serves the frontend at / and a WebSocket at /sessions/{id}/channel. Authentication is the first message, never a URL parameter. Identity is server-resolved; browser Origin must match the server. Configure trusted proxies correctly when terminating TLS. Audio/control messages, active connections, utterances and pending jobs are bounded.

The browser AudioWorklet captures continuously, requests echo cancellation, resamples the actual device rate to 16kHz, and produces 512 int16 samples per frame. Binary frames contain an 8-byte little-endian browser capture callback timestamp plus 1024 PCM bytes. There is no Python sounddevice dependency in this browser path. Remote microphone access requires HTTPS; localhost is suitable for development.

Backend Silero VAD shares an ONNX session while maintaining recurrent state separately for each call. Groq Whisper transcribes completed WAV utterances. Piper runs in a killable subprocess, emitting PCM chunks. The browser acknowledges each chunk after playback, with at most eight outstanding. Native speech dependencies load lazily; text works without speech models. Setup downloads models explicitly and verifies SHA-256 hashes; customer turns never trigger downloads.

## States and enforcement

States are listening, capturing, transcribing, processing, speaking, recovering and closed. Capture is independent of playback and stays active while the assistant speaks.

1. Only a completed, usable transcript becomes a Turn(channel=voice), with an application-generated unique ID.
2. Every turn calls SupportService.handle, preserving ownership, regex/semantic checks, signed dispatch, routing, tool authorization and output enforcement. Voice cannot call an agent directly.
3. TTS receives the exact finalized answer, after output checks. No unchecked model-token streaming. Tool evidence IDs are displayed as Order system in the UI; KB citations remain visible.
4. One connection worker serializes business turns. Existing Redis leases also serialize a session across connections/workers. Retrying transcription never creates an extra support turn.
5. Confirmed speech increments a generation, stops browser playback and cancels synthesis. Late audio is discarded. In-flight business work may complete and commit; interruption does not imply rollback. Its stale response is visible as interrupted and is not spoken. The next business turn waits.
6. The pending queue holds two jobs. All accepted voice and text jobs process FIFO, with stale assistant audio suppressed. A full queue explicitly rejects the new turn with a retry message. Graceful disconnect drains accepted jobs; a process crash still requires durable queue infrastructure.
7. Existing refund/eligibility reconciliation and exact messages remain authoritative. Successful escalation enters waiting-for-human. Shared history delivers human replies through the same playback path. Admin resolution resumes AI; customer termination closes both sides. Interruption cannot reopen a terminated session.

## Endpointing and barge-in

Defaults: five consecutive 32ms frames above .65 confirm speech (160ms), .35 sustains speech, 768ms of trailing nonspeech finalizes, and 320ms of pre-roll preserves initial phonemes. A 30-second utterance limit discards overlong audio and requests a shorter message rather than sending truncated order details.

Silence creates no turn. A short noise burst/false start below the speech confirmation duration leaves playback running. Confirmed speech invalidates current playback, clears browser audio sources and queues, retains pre-roll, then submits one completed interruption to STT. The browser acknowledges the stop. Empty or failed transcriptions never reach the router.

VAD detects speech, not speaker identity. Nearby speakers or TV speech can interrupt. Use a headset for this demo. Requested browser echo cancellation is not proof of robust speakerphone echo rejection; production speakerphone/telephony requires validated acoustic echo cancellation with the outgoing reference. Diarization is not implemented.

The shared order agent handles 'wait, wrong order' without reusing the previous reference: it asks which order. Explicit prefixes such as 'A E G 1003' normalize to AEG-1003 after input checks. It never invents digits from spoken number words; ambiguous references require clarification.

## Provider recovery

STT has one total deadline (default 12s), at most two attempts and bounded backoff. Retry transport/5xx errors and short rate limits with the same WAV. Do not retry invalid credentials or permanent request errors. Failure plays a bundled retry/type prompt and creates no business turn.

Piper has native-process termination/reaping and a bounded deadline. It can restart once if it fails before producing audio. A failure after audio starts stops playback and plays a bundled recovery recording; the validated answer stays on screen. It does not replay partial speech automatically. Bundled WAVs work without an operational TTS model. The synthesis deadline also bounds long spoken answers; configure it for expected answer length.

Missing playback acknowledgments time out. Disconnect stops microphone tracks/audio and closes the transport; already-started business work gets its existing bounded deadline to reach a known outcome before cleanup. Raw customer audio remains transient and is not logged by normal service operation. Explicit demo fixtures/transcripts are separate evidence.

## Latency definitions

- speech_frame_arrival_to_first_audio_sent_ms: server monotonic time from arrival of the last VAD-positive speech frame to the first substantive PCM packet sent. Includes trailing silence, STT, guards/router/handler, output checking and synthesis startup. Excludes inbound transit before that frame and delivery after send.
- capture_to_scheduled_audio_ms: client-reported estimate from that frame's browser capture callback timestamp to the first scheduled Web Audio sample, using one browser monotonic clock. Includes network and playback queueing. It is not a physical speaker measurement; callback scheduling and 32ms VAD resolution affect accuracy.
- playback_stop_roundtrip_ms: stop request to client acknowledgment; software control latency rather than physical acoustic decay.

Recovery prompts are marked separately and excluded from substantive response latency. scripts/summarize_voice_latency.py reports sample counts and p50/p95 by metric. Small scripted samples are not live-provider or production latency claims. Use annotated input and physical loopback for precise acoustic end-of-speech-to-speaker measurements.

## Accents, languages and deployment choices

A universal silence threshold does not fit hesitation, slow speech, accents or code-switching. Tune onset/hangover against representative recordings and report false interruptions, missed interruptions and premature endpoints per language/speaker. Adaptive hangover and semantic endpointing can be added with stable partial transcripts. Punctuation alone is insufficient. This baseline uses configurable acoustic endpointing, not a learned multilingual end-of-turn predictor.

Whisper supports multilingual recognition; the demo defaults to language=en and one English Piper voice. An empty AEGIS_STT_LANGUAGE lets Whisper detect language. Multilingual output needs matching voices and a language policy; it is not automatic.

On-device VAD reduces interruption latency/uploaded silence and survives network loss, but adds client models and device variability. Backend VAD centralizes tuning and fits this basic frontend, at the cost of continuous audio transport and network delay. The channel interfaces permit moving VAD client-side later without changing SupportService.

ASR is utterance-based through Groq's transcription endpoint, not the asynchronous Groq Batch API. Stable transcripts simplify one-turn dispatch. Streaming ASR helps long speech, captions and partial understanding, but revisable partials must not trigger business tools. TTS streams PCM after validated text; it does not stream unchecked LLM tokens.

## Capacity and sources

Worker-local limits bound channels, provider concurrency, audio frame rate, buffers and playback/jobs. Redis is still the shared session authority. 10,000 simultaneous calls need measured audio gateway capacity, provider quotas, admission control and separate VAD/TTS pools. Per-response Piper process isolation adds startup cost; a prewarmed bounded pool is a future optimization. Neither PSTN integration nor measured 10,000-call capacity is claimed.

- Groq STT: https://console.groq.com/docs/speech-to-text
- Piper API: https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md
- Silero: https://github.com/snakers4/silero-vad/blob/master/src/silero_vad/utils_vad.py
- Voice card: https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/lessac/medium/MODEL_CARD

Piper's engine is GPL-3.0; review engine/voice terms for distribution. Bundled recovery WAVs and test fixtures were synthesized with the selected Piper voice. Large models are setup downloads and are not in the changes-only package.
