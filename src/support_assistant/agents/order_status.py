import json
import re

from support_assistant.domain.conversation import SupportError
from support_assistant.domain.orders import HandlerResult
from support_assistant.rag.grounding import read_prompt
from support_assistant.tools.schemas import TOOLS


class OrderStatusAgent:
    def __init__(self, llm, executor, authority):
        self.llm, self.executor, self.authority = llm, executor, authority

    async def run(self, approved):
        self.authority.verify(approved)
        # STT commonly inserts spaces into spoken order prefixes. Normalize only
        # explicit digits; never guess an order ID from number words.
        ids = {
            "AEG-" + digits
            for digits in re.findall(
                r"\bA\s*E\s*G[\s-]*([0-9]{4,12})\b", approved.turn.text, re.I
            )
        }
        if len(ids) > 1:
            return HandlerResult("clarify")
        correction = re.search(
            r"\b(?:wrong|different|another)\s+order\b|\bnot\s+(?:that|this|the)\s+order\b",
            approved.turn.text,
            re.I,
        )
        if correction and not ids:
            return HandlerResult("order_reference")
        order_id = next(iter(ids), approved.session.last_order_id)
        if not order_id:
            return HandlerResult("order_reference")
        messages = [
            {"role": "system", "content": read_prompt("order_agent.md")},
            {
                "role": "user",
                "content": json.dumps(
                    {"message": approved.turn.text, "order_reference": order_id}
                ),
            },
        ]
        ledger = {}
        for round_number in range(3):
            # At most two tool rounds, one call per round, then final JSON.
            message = await self.llm.chat(
                messages,
                tools=TOOLS if round_number < 2 else None,
                force_tool=(round_number == 0),
            )
            calls = message.get("tool_calls") or []
            if calls:
                if round_number >= 2 or len(calls) != 1:
                    raise SupportError("tool_budget_exceeded")
                call = calls[0]
                if call.get("type") != "function":
                    raise SupportError("invalid_tool_call")
                function = call["function"]
                arguments = json.loads(function["arguments"])
                if arguments.get("order_id") != order_id:
                    raise SupportError("tool_order_reference_mismatch")
                result = await self.executor.execute(
                    approved,
                    function["name"],
                    function["arguments"],
                    call["id"],
                    ledger,
                )
                messages.append(
                    {"role": "assistant", "content": None, "tool_calls": calls}
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps(result),
                    }
                )
                continue
            if not ledger:
                raise SupportError("missing_tool_evidence")
            # The model's final prose is not authoritative. Render recorded fields centrally.
            records = list(ledger.values())
            return HandlerResult(
                "order", {"records": records}, verified_order_id=order_id
            )
        raise SupportError("tool_budget_exceeded")
