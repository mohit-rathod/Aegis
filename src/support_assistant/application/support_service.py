import logging

from support_assistant.domain.errors import ProviderError
from support_assistant.domain.evidence import FinalResponse

logger = logging.getLogger(__name__)

SAFE_MESSAGES = {
    "abstain": "I do not have enough confirmed information in the Aegis knowledge base. I can help prepare a human-support handoff.",
    "tool_required": "That needs an authorized order-service check. This knowledge-base module cannot confirm live order or refund details.",
    "blocked": "I cannot bypass authorization, reveal internal instructions, or make an unconfirmed commitment. I can help with documented Aegis support questions.",
    "unavailable": "I could not complete the required checks. Please retry or use human support.",
}

def safe_response(status):
    return FinalResponse(status=status, answer=SAFE_MESSAGES[status], citations=[])

class GuardedRAGService:
    """Public RAG entry point. Voice/text should call this, never agent.run directly."""
    def __init__(self, input_guard, agent, output_guard):
        self.input_guard, self.agent, self.output_guard = input_guard, agent, output_guard

    def handle(self, question):
        if not isinstance(question, str) or not question.strip() or len(question) > 2000:
            raise ValueError("Provide a non-empty question of at most 2000 characters")
        
        stage = "input_guard"

        try:
            decision = self.input_guard.check(question)
            if not decision.allowed:
                return safe_response("blocked")

            stage = "retrieval_or_generation"

            draft, hits = self.agent.run(question)
            if draft is None:
                return safe_response("abstain")

            stage = "output_guard"

            if not self.output_guard.check(question, draft, hits):
                return safe_response("abstain")
            if draft.status != "answer":
                return safe_response(draft.status)
            answer = "\n".join(f"{c.text} [{', '.join(c.citations)}]" for c in draft.claims)
            citations = sorted({doc for c in draft.claims for doc in c.citations})
            return FinalResponse(status="answer", answer=answer, citations=citations)
        except Exception as exc:
            detail = (
                str(exc)
                if isinstance(exc, ProviderError)
                else "Check the stage's configuration or response schema"
            )

            logger.error(
                "RAG stage=%s failed (%s): %s",
                stage,
                type(exc).__name__,
                detail,
            )

            return safe_response("unavailable")
