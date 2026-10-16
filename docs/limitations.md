# support system limitations

- Demo identities are selected by trusted local CLI use or server-configured demo bearer tokens; there is no real customer identity provider.
- Orders are read-only fixtures. No payment, shipping, refund-execution or real human-chat integration exists.
- The support intake is persistent Redis records. The requested human-joining message is part of the demo flow, not evidence that a staffed human chat service is connected.
- Multi-worker infrastructure is provided, but measured capacity is 10k session records with scripted providers in a single process, not 10k active Groq requests or open connections.
- Semantic gates are probabilistic; live quality and recall have not been measured here.
- Redis is standalone/primary based; scripts do not support Redis Cluster cross-slot routing.
- Redis has finite configured memory. A full instance fails closed; separate cache and authoritative persistence and add retention/acknowledgement for production.
- Session retry responses expire with their TTL; support-intake records persist until an operator-managed retention process is added. Session expiration returns unavailable/not found, never silently reactivates the old ID.
- Slow embedding tasks cannot be forcibly killed in a Python thread. Slots remain occupied until those tasks finish; request deadlines prevent their results from being delivered late.
- Per-worker provider limits need a deployment-wide quota budget. The package does not dynamically discover or enforce an account's global token quota.
- Only one handler runs per turn. Unrelated mixed issues clarify; an unrestricted cross-agent loop is deliberately absent.
- Refund and escalation policies remain the approved demo rules. This structural refactor does not change KB content or require a new index.
- Text, browser voice and HTTP channels use the same async SupportService. Voice is a browser support-line demo; no PSTN integration or production speakerphone echo guarantee is provided.

- The included voice evidence uses synthetic input, real VAD/Piper/Redis, and scripted STT/LLM responses. No physical microphone, live Groq quality, accent coverage or production voice concurrency was measured in this environment.
- The English demo uses configurable acoustic endpointing and one English voice. Sustained background speech can interrupt; multilingual output, adaptive semantic endpointing and validated speakerphone AEC remain future work.
- Piper workers start per response for cancellation isolation. This adds startup latency; synthesis and playback deadlines can truncate long speech and use the recorded fallback while the full validated answer remains visible.
