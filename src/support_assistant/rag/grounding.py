from importlib.resources import files
from support_assistant.domain.evidence import AnswerDraft
from support_assistant.rag.citations import validate_citations

def read_prompt(name):
    return files("support_assistant").joinpath("prompts", name).read_text(encoding="utf-8")

def evidence_payload(hits):
    return [{"document_id": h.document.document_id, "title": h.document.title,
        "version": h.document.version, "content": h.document.body} for h in hits]

class GroundedAnswerer:
    def __init__(self, llm):
        self.llm = llm

    def draft(self, question, hits):
        result = self.llm.complete_json(read_prompt("product_answer.md"),
            {"question": question, "reference_documents": evidence_payload(hits)})
        draft = AnswerDraft.model_validate(result)
        validate_citations(draft, hits)
        return draft
