from support_assistant.domain.orders import HandlerResult


class HumanEscalationAgent:
    def __init__(self, authority):
        self.authority = authority

    async def run(self, approved):
        self.authority.verify(approved)
        # Customer statement is explicitly distinguished from verified context.
        return HandlerResult(
            "escalation",
            {
                "customer_statement": approved.turn.text[:500],
                "verified_order_id": approved.session.last_order_id,
            },
        )
