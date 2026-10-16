import asyncio
import time

from support_assistant.domain.orders import HandlerResult
from support_assistant.observability.logging import event
from support_assistant.rag.grounding import GroundedAnswerer


class ProductQuestionAgent:
    def __init__(self, retriever, llm, authority, pool, max_pending=4):
        self.retriever, self.llm, self.authority, self.pool = (
            retriever,
            llm,
            authority,
            pool,
        )
        self.answerer = GroundedAnswerer(llm)
        self.pending = 0
        self.max_pending = max_pending

    async def run(self, approved):
        self.authority.verify(approved)
        # Counter is owned by one asyncio loop. Remains occupied after cancellation
        # until the real thread finishes, preventing unbounded executor submission.
        if self.pending >= self.max_pending:
            return HandlerResult("busy")
        self.pending += 1
        start = time.monotonic()
        loop = asyncio.get_running_loop()
        try:
            future = loop.run_in_executor(
                self.pool, self.retriever.retrieve, approved.turn.text
            )
        except BaseException:
            self.pending -= 1
            raise

        def finished(done):
            self.pending -= 1
            if not done.cancelled():
                done.exception()

        future.add_done_callback(finished)
        hits = await asyncio.shield(future)
        event(
            "retrieval_completed",
            turn_id=approved.turn.turn_id,
            documents=[
                {"id": h.document.document_id, "score": round(h.score, 4)} for h in hits
            ],
            duration_ms=round((time.monotonic() - start) * 1000, 2),
        )
        if not hits:
            return HandlerResult("abstain")
        draft = await self.answerer.draft(approved.turn.text, hits)
        if draft.status != "answer":
            return HandlerResult(draft.status)
        return HandlerResult("product", hits=tuple(hits), draft=draft)
