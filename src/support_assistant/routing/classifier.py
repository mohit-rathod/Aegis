import asyncio
import hashlib
import time

from support_assistant.domain.conversation import SupportError
from support_assistant.domain.routing import Route
from support_assistant.observability.logging import event
from support_assistant.rag.grounding import read_prompt
from support_assistant.routing.cache_key import cache_key
from support_assistant.routing.registry import INTENTS


class Classifier:
    def __init__(self, llm, cache, provider_timeout=20):
        self.llm, self.cache, self.provider_timeout = llm, cache, provider_timeout
        self.prompt = read_prompt("router.md")
        self.prompt_hash = hashlib.sha256(self.prompt.encode()).hexdigest()

    async def classify(self, approved):
        session, turn = approved.session, approved.turn
        key = cache_key(session, turn.text, self.llm.model, self.prompt_hash)
        cached = await self.cache.get(key)
        if cached:
            await self.cache.count("hits")
            event("classifier_cache", turn_id=turn.turn_id, hit=True)
            return cached
        await self.cache.count("misses")
        event("classifier_cache", turn_id=turn.turn_id, hit=False)
        end = time.monotonic() + self.provider_timeout + 2
        token = None
        while time.monotonic() < end:
            token = await self.cache.acquire_fill(key, int(self.provider_timeout) + 5)
            if token:
                break
            cached = await self.cache.get(key)
            if cached:
                await self.cache.count("coalesced")
                return cached
            await asyncio.sleep(0.05)
        if not token:
            raise SupportError("classifier_busy")
        try:
            cached = await self.cache.get(key)
            if cached:
                await self.cache.count("coalesced")
                return cached
            await self.cache.count("groq_calls")
            start = time.monotonic()
            raw = await self.llm.complete_json(
                self.prompt,
                {
                    "message": turn.text,
                    "context": {
                        "last_order_id": session.last_order_id,
                        "pending_intent": session.pending_intent,
                        "human_resolution_untrusted": session.human_resolution,
                    },
                    "registered_intents": INTENTS,
                },
            )
            route = Route.model_validate(raw)
            await self.cache.put(key, route)
            event(
                "route_resolved",
                turn_id=turn.turn_id,
                intent=route.intent,
                needs_clarification=route.needs_clarification,
                duration_ms=round((time.monotonic() - start) * 1000, 2),
            )
            return route
        except Exception:
            await self.cache.count("failures")
            raise
        finally:
            await self.cache.release_fill(key, token)
