import asyncio
import os
import unittest
import uuid
from pathlib import Path

import httpx
from redis.asyncio import Redis

from support_assistant.config import Settings
from support_assistant.domain.conversation import SupportError, Turn
from support_assistant.entrypoints.api.app import app
from support_assistant.voice.coordinator import VoiceCoordinator
from support_assistant.voice.faults import DemoFaults
from tests.fakes.audio import Detector, components
from tests.fakes.support import make_service

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.getenv("AEGIS_TEST_REDIS_URL"), "Set AEGIS_TEST_REDIS_URL")
class HumanSupportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.redis = Redis.from_url(
            os.environ["AEGIS_TEST_REDIS_URL"], decode_responses=True
        )
        self.prefix = "aegis-human-test-" + uuid.uuid4().hex
        self.r = make_service(self.redis, self.prefix, ROOT)
        self.r.settings = Settings(
            demo_a_token="customer-a-token",
            demo_b_token="customer-b-token",
            admin_token="staff-only",
            prefix=self.prefix,
            redis_url=os.environ["AEGIS_TEST_REDIS_URL"],
            turn_timeout=2,
        )
        self.r.redis = self.redis
        _, self.resources, self.transport = components()
        self.resources.connections = 0
        self.resources.faults = DemoFaults(self.redis, self.prefix, False)
        self.resources.mode = "test_double"
        self.r.voice = self.resources
        self.session = await self.r.store.create("customer-a")
        self.sid = self.session.session_id
        self.previous = getattr(app.state, "runtime", None)
        app.state.runtime = self.r
        self.http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        )
        self.admin = {"Authorization": "Bearer staff-only"}
        self.customer = {"Authorization": "Bearer customer-a-token"}
        self.coordinator = None

    async def asyncTearDown(self):
        if self.coordinator:
            await self.coordinator.aclose()
        await self.http.aclose()
        app.state.runtime = self.previous
        keys = [k async for k in self.redis.scan_iter(match=self.prefix + ":*")]
        if keys:
            await self.redis.delete(*keys)
        await self.redis.aclose()

    async def ask(self, text, tid=None):
        return await self.r.service.handle(
            "customer-a", self.sid, Turn(turn_id=tid or uuid.uuid4().hex, text=text)
        )

    async def escalate(self):
        self.r.llm.route = "escalate_to_human"
        response = await self.ask("I need a human to help with this order.")
        return response.support_request_id

    async def wait(self, predicate):
        async with asyncio.timeout(3):
            while not predicate():
                await asyncio.sleep(0.02)

    async def test_handoff_summary_contains_context_and_verified_order(self):
        await self.ask("Where is AEG-1001?")
        rid = await self.escalate()
        detail = await self.r.service.human.detail(rid)
        self.assertEqual(detail["session"]["state"], "waiting_for_human")
        self.assertEqual(detail["request"]["summary"]["verified_order_id"], "AEG-1001")
        self.assertIn("Where is AEG-1001?", detail["request"]["summary"]["overview"])
        self.assertIn("human", detail["request"]["summary"]["help_needed"])

    async def test_human_messages_bypass_classifier_but_not_ownership(self):
        rid = await self.escalate()
        await self.r.service.human.claim(rid)
        before = list(self.r.llm.calls)
        response = await self.ask("Here is more information.")
        self.assertEqual(response.status, "human_message")
        self.assertEqual(self.r.llm.calls, before)
        with self.assertRaises(SupportError):
            await self.r.service.handle(
                "customer-b", self.sid, Turn(turn_id="wrong", text="hello")
            )

    async def test_customer_cannot_use_admin_chat_or_fault_controls(self):
        rid = await self.escalate()
        for path, body in [
            (f"/admin/support-requests/{rid}/claim", None),
            (
                f"/admin/support-requests/{rid}/messages",
                {"message_id": "one", "text": "spoof"},
            ),
            (f"/admin/sessions/{self.sid}/fault", {"kind": "tts_midstream"}),
        ]:
            response = await self.http.post(path, headers=self.customer, json=body)
            self.assertEqual(response.status_code, 403)

    async def test_admin_must_claim_an_actual_pending_handoff(self):
        self.assertEqual(
            (await self.http.get("/admin/support-requests", headers=self.admin)).json(),
            [],
        )
        response = await self.http.post(
            "/admin/support-requests/SUP-nonexistent/claim", headers=self.admin
        )
        self.assertEqual(response.status_code, 404)
        rid = await self.escalate()
        response = await self.http.post(
            f"/admin/support-requests/{rid}/messages",
            headers=self.admin,
            json={"message_id": "x", "text": "Hello"},
        )
        self.assertEqual(response.status_code, 409)

    async def test_admin_reply_is_idempotent_and_conflicts_are_rejected(self):
        rid = await self.escalate()
        await self.r.service.human.claim(rid)
        first = await self.r.service.human.message(
            rid, "human-one", "Please inspect the filter."
        )
        second = await self.r.service.human.message(
            rid, "human-one", "Please inspect the filter."
        )
        self.assertEqual(first, second)
        with self.assertRaisesRegex(SupportError, "message_id_conflict"):
            await self.r.service.human.message(rid, "human-one", "Different reply")
        session = await self.r.store.get(self.sid, "customer-a")
        self.assertEqual(sum(m.message_id == "human-one" for m in session.history), 1)

    async def test_resolution_is_extracted_and_agent_resumes(self):
        rid = await self.escalate()
        await self.r.service.human.claim(rid)
        await self.r.service.human.message(
            rid, "human-one", "Use the AF-P1 filter for Pure Plus."
        )
        request = await self.r.service.human.resolve(rid, "")
        self.assertIn("AF-P1", request["resolution"])
        session = await self.r.store.get(self.sid, "customer-a")
        self.assertEqual(session.state, "active")
        self.assertIn("AF-P1", session.human_resolution)
        self.r.llm.route = "order_status"
        self.assertEqual((await self.ask("Where is AEG-1001?")).status, "answer")
        with self.assertRaisesRegex(SupportError, "handoff_not_active"):
            await self.r.service.human.message(rid, "late", "Late staff message")

    async def test_repeated_resolution_does_not_duplicate_or_reopen_closed_session(
        self,
    ):
        rid = await self.escalate()
        await self.r.service.human.claim(rid)
        first = await self.r.service.human.resolve(rid, "Guidance provided.")
        await self.r.service.human.end_conversation(self.sid, "customer-a")
        self.assertEqual(
            await self.r.service.human.resolve(rid, "Different retry"), first
        )
        self.assertEqual(
            (await self.r.store.get(self.sid, "customer-a")).state, "terminated"
        )

    async def test_customer_end_closes_human_and_ai(self):
        rid = await self.escalate()
        await self.r.service.human.claim(rid)
        response = await self.http.post(
            f"/sessions/{self.sid}/end", headers=self.customer
        )
        self.assertEqual(response.json()["state"], "terminated")
        self.assertEqual(
            (await self.r.store.get_request(rid))["status"], "customer_closed"
        )
        self.assertEqual((await self.ask("Another question")).status, "terminated")
        with self.assertRaises(SupportError):
            await self.r.service.human.message(rid, "late", "Not allowed")

    async def test_customer_b_cannot_read_or_close_customer_a(self):
        headers = {"Authorization": "Bearer customer-b-token"}
        self.assertEqual(
            (await self.http.get(f"/sessions/{self.sid}", headers=headers)).status_code,
            404,
        )
        self.assertNotEqual(
            (
                await self.http.post(f"/sessions/{self.sid}/end", headers=headers)
            ).status_code,
            200,
        )
        self.assertEqual(
            (await self.r.store.get(self.sid, "customer-a")).state, "active"
        )

    async def test_new_escalation_after_resolution_creates_new_ticket(self):
        first = await self.escalate()
        await self.r.service.human.claim(first)
        await self.r.service.human.resolve(first, "Done.")
        second = await self.escalate()
        self.assertNotEqual(first, second)
        with self.assertRaises(SupportError):
            await self.r.service.human.message(first, "old", "Old ticket")

    async def test_history_redacts_blocked_credentials(self):
        await self.ask("password=super-secret-demo")
        history = (await self.r.store.get(self.sid, "customer-a")).history
        self.assertNotIn("super-secret-demo", str(history))
        self.assertIn("Blocked input", history[0].text)

    async def test_history_is_bounded_and_sequence_survives_trimming(self):
        from support_assistant.application.history import append_message

        session = self.session
        for i in range(150):
            session, _ = append_message(session, str(i), "customer", "hello")
        self.assertEqual(len(session.history), 120)
        self.assertEqual(session.message_sequence, 150)

    async def test_human_reply_and_resolution_reach_voice_coordinator(self):
        rid = await self.escalate()
        self.coordinator = VoiceCoordinator(
            self.r, "customer-a", self.sid, self.transport, self.resources
        )
        self.transport.coordinator = self.coordinator
        self.coordinator.detector = Detector()
        self.coordinator.enabled = True
        await self.coordinator.start()
        await self.r.service.human.claim(rid)
        await self.r.service.human.message(
            rid, "human-live", "Please check the filter seal."
        )
        await self.wait(
            lambda: any(
                p["type"] == "chat_event" and p.get("message_id") == "human-live"
                for p in self.transport.rows
            )
        )
        await self.coordinator.queue.join()
        self.assertGreater(self.resources.tts.calls, 0)
        await self.r.service.human.resolve(rid, "Filter troubleshooting completed.")
        await self.wait(
            lambda: any(
                p["type"] == "chat_event" and p.get("kind") == "resolution"
                for p in self.transport.rows
            )
        )
        await self.coordinator.queue.join()
        self.assertTrue(
            any(
                p["type"] == "session_state" and p["state"] == "active"
                for p in self.transport.rows
            )
        )

    async def test_fault_controls_are_disabled_by_default_and_one_shot_when_enabled(
        self,
    ):
        response = await self.http.post(
            f"/admin/sessions/{self.sid}/fault",
            headers=self.admin,
            json={"kind": "stt_auth"},
        )
        self.assertEqual(response.status_code, 409)
        self.resources.faults.enabled = True
        response = await self.http.post(
            f"/admin/sessions/{self.sid}/fault",
            headers=self.admin,
            json={"kind": "stt_auth"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(await self.resources.faults.consume(self.sid, "stt_auth"))
        self.assertFalse(await self.resources.faults.consume(self.sid, "stt_auth"))


class RoleConfigTests(unittest.TestCase):
    def test_admin_token_must_not_equal_customer_token(self):
        with self.assertRaises(ValueError):
            Settings(demo_a_token="same", admin_token="same")
