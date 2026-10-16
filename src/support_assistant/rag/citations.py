def validate_citations(draft, hits):
    allowed = {h.document.document_id for h in hits}
    if draft.status == "answer" and not draft.claims:
        raise ValueError("An answer requires at least one supported claim")
    if draft.status != "answer" and draft.claims:
        raise ValueError("Non-answer statuses cannot include generated claims")
    for claim in draft.claims:
        if len(set(claim.citations)) != len(claim.citations):
            raise ValueError("Duplicate citation")
        if not set(claim.citations) <= allowed:
            raise ValueError("Citation was not retrieved")
