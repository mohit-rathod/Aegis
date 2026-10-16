import re
from support_assistant.domain.evidence import SupportDecision
from support_assistant.rag.grounding import read_prompt,evidence_payload
from support_assistant.rag.citations import validate_citations
from support_assistant.safety.safe_responses import MESSAGES,REFUND_INITIATED,ESCALATED
from support_assistant.domain.conversation import SupportError

class ResponseService:
    def __init__(self,llm,executor): self.llm,self.executor=llm,executor

    async def render(self,approved,result):
        if result.kind=="product":
            validate_citations(result.draft,result.hits)
            # A static KB cannot establish the customer's current refund or ticket state.
            # Conservative: this can reject a quoted template, documented in red-team notes.
            transactional = re.compile(r"\b(?:your|the) refund (?:is|has been) (?:approved|initiated)\b|\bI (?:have )?(?:created|raised|submitted) (?:a |your )?(?:ticket|support request)\b", re.I)
            if any(transactional.search(claim.text) for claim in result.draft.claims):
                return "abstain", MESSAGES["abstain"], ()
            verdict=SupportDecision.model_validate(await self.llm.complete_json(read_prompt("output_guard.md"),
                {"question":approved.turn.text,"draft":result.draft.model_dump(),
                    "reference_documents":evidence_payload(result.hits)}))
            if not verdict.supported: return "abstain",MESSAGES["abstain"],()
            text="\n".join(f"{c.text} [{', '.join(c.citations)}]" for c in result.draft.claims)
            citations=tuple(sorted({x for c in result.draft.claims for x in c.citations}))
            return "answer",text,citations
        if result.kind=="order":
            records=self.executor.verify_records(approved,result.data["records"])
            lines=[]
            for record in records:
                data=record["data"]
                if record["tool"]=="get_order_status":
                    if data["refund_status"]=="approved_and_initiated":
                        if not data.get("refund_initiated_at") or data.get("refund_destination")!="original_payment_source":
                            raise SupportError("unsupported_refund_claim")
                        lines.append(REFUND_INITIATED)
                    else:
                        lines.append(f"Order {data['order_id']} status: {data['status']}.")
                        if data.get("estimated_delivery"):
                            lines.append(f"Estimated delivery: {data['estimated_delivery']}. This is an estimate, not a guarantee.")
                        if data["refund_status"]=="under_review":
                            lines.append("The refund request is under review; approval and initiation are not confirmed.")
                elif record["tool"]=="check_return_eligibility":
                    state=data["eligibility"]
                    if state=="eligible":
                        lines.append("This order is eligible to request a return. Eligibility does not approve or initiate a refund.")
                    elif state=="ineligible": lines.append("This order is not eligible under the recorded return-request conditions.")
                    else: lines.append("This return request needs human review; eligibility is not confirmed.")
                    lines.append(data["reason"]+".")
                else: raise SupportError("unknown_evidence_tool")
            if not lines: raise SupportError("missing_tool_evidence")
            # Controlled strings and exact trusted fields: the LLM's final prose is discarded.
            return "answer","\n".join(dict.fromkeys(lines)),tuple(r["evidence_id"] for r in records)
        if result.kind=="escalation":
            # Prepared response only. The service must atomically persist the request
            # and terminated session before returning this text to any caller.
            return "escalated",ESCALATED,()
        if result.kind in MESSAGES:
            return ("clarify" if result.kind in ["clarify","order_reference","tool_required"] else result.kind,
                MESSAGES[result.kind],())
        raise SupportError("unknown_handler_result")
