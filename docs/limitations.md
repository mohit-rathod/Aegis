# support system limitations

- Demo identities are selected by trusted local CLI use or server-configured demo bearer tokens; there is no real customer identity provider.
- Orders are read-only fixtures. No payment, shipping or refund-execution integration exists. Human chat is implemented in the local admin console.
- The admin console uses a shared demo admin token, bounded history and polling. Per-agent identity, assignment, audit retention, staffing guarantees and notification integrations are deployment work. Human replies are trusted operator content, not AI-verified claims.
- Multi-worker infrastructure is provided, but measured capacity is 10k session records with scripted providers in a single process, not 10k active Groq requests or open connections.
- Semantic gates are probabilistic; live quality and recall have not been measured here.
- Redis is standalone/primary based; scripts do not support Redis Cluster cross-slot routing.
- Redis has finite configured memory. A full instance fails closed; separate cache and authoritative persistence and add retention/acknowledgement for production.
- Session retry responses expire with their TTL; support-intake records persist until an operator-managed retention process is added. Session expiration returns unavailable/not found, never silently reactivates the old ID.
- Slow embedding tasks cannot be forcibly killed in a Python thread. Slots remain occupied until those tasks finish; request deadlines prevent their results from being delivered late.
- Per-worker provider limits need a deployment-wide quota budget. The package does not dynamically discover or enforce an account's global token quota.
- Only one handler runs per turn. Unrelated mixed issues clarify; an unrestricted cross-agent loop is deliberately absent.
- The human-support KB document changed; rebuild the index. Eligibility still does not initiate a refund.
- Text, browser voice and HTTP channels use the same async SupportService. Voice is a browser support-line demo; no PSTN integration or production speakerphone echo guarantee is provided.

- Accepted voice/text jobs survive interruption and graceful disconnect, but the in-memory queue cannot survive a process crash; production requires durable jobs.
- The included voice evidence uses synthetic input, real VAD/Piper/Redis, and scripted STT/LLM responses. No physical microphone, live Groq quality, accent coverage or production voice concurrency was measured in this environment.
- The English demo uses configurable acoustic endpointing and one English voice. Sustained background speech can interrupt; multilingual output, adaptive semantic endpointing and validated speakerphone AEC remain future work.
- Piper workers start per response for cancellation isolation. This adds startup latency; synthesis and playback deadlines can truncate long speech and use the recorded fallback while the full validated answer remains visible.
