# Requirements mapping

| Requirement | Implementation | Evidence |
|---|---|---|
| Three-intent Groq router | routing/classifier.py, routing/registry.py | routing.jsonl and live runner |
| Embedding RAG | existing rag modules + agents/product_question.py | original KB/index checks and grounding seeds |
| Native tool calling | adapters/groq/client.py, agents/order_status.py | adapter contract and authorization tests |
| Regex and semantic input guards | safety/regex_guard.py, prompts/input_guard.md | blocked/failed-input tests |
| No unchecked dispatch | domain/safety.py, application/guarded_dispatcher.py | missing/mismatched approval tests |
| Output commitments grounded | application/response_service.py, tool evidence vault | forged evidence/refund/eligibility tests |
| Classifier cache/hit rate | adapters/cache/redis_cache.py | hit/miss/coalescing tests and capacity.json |
| Exact refund message | safe_responses.py + confirmed tool state | test_refund_exact_message |
| Human handoff and AI resumption | application/human_support.py + shared history + admin UI | handoff API, browser, voice and termination tests |
| Terminal traces | observability/logging.py | saved scripted traces.jsonl |
| Scale design and scaffolding | async API + Redis + bounded workers | support-design.md and capacity runner |
| Actual 10k production capacity | not established | capacity report explicitly narrows its scope |
| Fourth-agent extension | versioned registry boundary | documented only; deferred |
| Honest failures | red-team-findings.md | two observed component false positives |
| Real commit history | user's existing Git repository | never generated or backdated by this patch |
| Browser text/voice controls | entrypoints/web + authenticated WebSocket | Chromium/Node checks |
| Groq Whisper transcription | adapters/groq/speech_to_text.py | multipart/retry/deadline tests; live-run command |
| Interruptible Piper output | adapters/tts/piper.py + voice/playback_controller.py | native synthesis/cancellation and failure fixtures |
| Speech/noise discrimination | Silero + voice/endpointing.py | six paced scenarios and VAD fixture replay |
| Latency reporting | coordinator + browser playback clock | separate server/client estimates, explicit test mode |
| Accepted-turn preservation | voice/coordinator.py | FIFO, duplicate, disconnect and overflow tests |
| In-call failure controls | voice/faults.py + admin API/UI | default-disabled authorization tests and native Piper browser recovery |
| Live evaluation and operations answers | scripts/evaluate_live_system.py + docs/integration-and-operations.md | reproducible runner; live results require credentials |
