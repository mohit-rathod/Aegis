# Requirements mapping

| Requirement | Implementation | Evidence |
|---|---|---|
| Three-intent Groq router | routing/classifier.py, routing/registry.py | routing.jsonl and live runner |
| Embedding RAG | existing rag modules + agents/async_product_question.py | original KB/index checks and grounding seeds |
| Native tool calling | adapters/groq/async_client.py, agents/order_status.py | adapter contract and authorization tests |
| Regex and semantic input guards | safety/regex_guard.py, prompts/input_guard.md | blocked/failed-input tests |
| No unchecked dispatch | domain/safety.py, application/guarded_dispatcher.py | missing/mismatched approval tests |
| Output commitments grounded | application/response_service.py, tool evidence vault | forged evidence/refund/eligibility tests |
| Classifier cache/hit rate | adapters/cache/redis_cache.py | hit/miss/coalescing tests and capacity.json |
| Exact refund message | safe_responses.py + confirmed tool state | test_refund_exact_message |
| Escalate and terminate | redis_sessions.py + support_service.py | persistence/replay/termination tests |
| Terminal traces | observability/logging.py | saved scripted traces.jsonl |
| Scale design and scaffolding | async API + Redis + bounded workers | support-design.md and capacity runner |
| Actual 10k production capacity | not established | capacity report explicitly narrows its scope |
| Fourth-agent extension | versioned registry boundary | documented only; deferred |
| Honest failures | red-team-findings.md | two observed component false positives |
| Real commit history | user's existing Git repository | never generated or backdated by this patch |
