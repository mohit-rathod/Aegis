from support_assistant.domain.evidence import InputDecision
from support_assistant.rag.grounding import read_prompt


class SemanticInputGuard:
    def __init__(self, llm):
        self.llm = llm

    async def check(self, question, context=None):
        result = await self.llm.complete_json(
            read_prompt("input_guard.md"),
            {"untrusted_customer_message": question, "context": context or {}},
        )
        return InputDecision.model_validate(result)
