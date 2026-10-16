# Part A limitations

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
- The refund timeline and escalation policy changed to user-specified demo rules. The index must be rebuilt before starting Part A.
- The old sync RAG service remains for legacy tests and internal compatibility; public ask/chat/API paths use the new shared Part A service.
