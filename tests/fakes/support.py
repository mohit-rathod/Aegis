import asyncio
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from support_assistant.adapters.cache.redis_cache import RedisClassifierCache
from support_assistant.adapters.persistence.fixture_orders import FixtureOrders
from support_assistant.adapters.persistence.redis_sessions import RedisSessionStore
from support_assistant.agents.human_escalation import HumanEscalationAgent
from support_assistant.agents.order_status import OrderStatusAgent
from support_assistant.application.guarded_dispatcher import GuardedDispatcher
from support_assistant.application.response_service import ResponseService
from support_assistant.application.support_service import SupportService
from support_assistant.domain.orders import HandlerResult
from support_assistant.domain.safety import ApprovalAuthority
from support_assistant.routing.classifier import Classifier
from support_assistant.safety.regex_guard import RegexGuard
from support_assistant.tools.executor import ToolExecutor


class FakeLLM:
    """Scripted provider for structural tests/load only. Never use for live quality claims."""

    model = "fake-test-model"

    def __init__(self):
        self.calls = []
        self.route = "order_status"
        self.allow = True
        self.supported = True
        self.fail_gate = False
        self.delay = 0
        self.tool_name = "get_order_status"
        self.tool_calls = 0
        self.repeat_tools = False
        self.forced_order = None

    async def complete_json(self, system, payload):
        if self.delay:
            await asyncio.sleep(self.delay)
        if "semantic input safety gate" in system:
            self.calls.append("input")
            if self.fail_gate:
                raise TimeoutError()
            return {"allowed": self.allow, "reason": "scripted decision"}
        if "intent classifier" in system:
            self.calls.append("router")
            return {
                "intent": self.route,
                "needs_clarification": False,
                "reason": "scripted route",
            }
        if "verify an Aegis answer" in system:
            self.calls.append("output")
            return {"supported": self.supported, "reason": "scripted decision"}
        raise AssertionError("Unexpected fake request")

    async def chat(self, messages, tools=None, force_tool=False):
        self.calls.append("tool_planner")
        previous = [m for m in messages if m.get("role") == "tool"]
        if previous and not self.repeat_tools:
            return {"content": '{"done":true}'}
        body = json.loads(messages[1]["content"])
        oid = self.forced_order or body["order_reference"]
        self.tool_calls += 1
        return {
            "tool_calls": [
                {
                    "id": f"call-{self.tool_calls}",
                    "type": "function",
                    "function": {
                        "name": self.tool_name,
                        "arguments": json.dumps({"order_id": oid}),
                    },
                }
            ]
        }

    async def aclose(self):
        pass


class FakeProduct:
    def __init__(self, authority):
        self.authority = authority
        self.calls = 0

    async def run(self, approved):
        self.authority.verify(approved)
        self.calls += 1
        return HandlerResult("abstain")


def make_service(redis, prefix, root, llm=None):
    llm = llm or FakeLLM()
    authority = ApprovalAuthority(30)
    store = RedisSessionStore(redis, prefix, 300, 15)
    cache = RedisClassifierCache(redis, prefix, 300, 1000)
    executor = ToolExecutor(
        FixtureOrders(Path(root) / "data/fixtures/orders.json"),
        authority,
        lambda: date(2026, 10, 16),
    )
    product = FakeProduct(authority)
    handlers = {
        "product_question": product,
        "order_status": OrderStatusAgent(llm, executor, authority),
        "escalate_to_human": HumanEscalationAgent(authority),
    }
    dispatcher = GuardedDispatcher(authority, handlers)
    responses = ResponseService(llm, executor)
    service = SupportService(
        store,
        RegexGuard(),
        llm,
        Classifier(llm, cache),
        dispatcher,
        responses,
        authority,
        executor,
        turn_timeout=5,
        max_active=32,
    )
    return SimpleNamespace(
        service=service,
        store=store,
        cache=cache,
        llm=llm,
        authority=authority,
        executor=executor,
        product=product,
        dispatcher=dispatcher,
        responses=responses,
    )
