from support_assistant.domain.evidence import SupportDecision
from support_assistant.rag.citations import validate_citations
from support_assistant.rag.grounding import read_prompt, evidence_payload

class GroundingOutputGuard:
    def __init__(self, llm): self.llm = llm

    def check(self, question, draft, hits):
        validate_citations(draft, hits)
        if draft.status != "answer":
            return True
        result = SupportDecision.model_validate(self.llm.complete_json(
            read_prompt("output_guard.md"), {"question": question,
                "draft": draft.model_dump(), "reference_documents": evidence_payload(hits)}))
        return result.supported
