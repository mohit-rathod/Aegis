"""Authenticated API callers enter here; all state changes share the session lease."""

import asyncio
import time

from support_assistant.application.history import append_message
from support_assistant.domain.conversation import SupportError, SupportResponse
from support_assistant.observability.logging import event


class HumanSupport:
    def __init__(self, store):
        self.store = store

    async def detail(self, request_id):
        request = await self.store.get_request(request_id)
        session = await self.store.get_internal(request["session_id"])
        return {"request": request, "session": session.model_dump(mode="json")}

    async def receive(self, session, turn, token):
        response = SupportResponse(
            session_id=session.session_id,
            turn_id=turn.turn_id,
            status="human_message",
            answer="Your message has been sent to the support team.",
            intent="escalate_to_human",
            session_state=session.state,
            support_request_id=session.support_request_id,
        )
        await self.store.commit(session, turn, response, token)
        event(
            "human_customer_message",
            session_id=session.session_id,
            turn_id=turn.turn_id,
        )
        return response

    async def _current(self, request_id):
        request = await self.store.get_request(request_id)
        session = await self.store.get_internal(request["session_id"])
        if session.support_request_id != request_id or session.state not in [
            "waiting_for_human",
            "human_active",
        ]:
            raise SupportError("handoff_not_active")
        return request, session

    async def claim(self, request_id):
        request = await self.store.get_request(request_id)
        async with self.store.lease(request["session_id"]) as token:
            request, session = await self._current(request_id)
            if session.state == "human_active":
                return await self.detail(request_id)
            session = session.model_copy(
                update={"state": "human_active", "version": session.version + 1}
            )
            session, _ = append_message(
                session,
                "claim-" + request_id,
                "system",
                "A support team member has joined the conversation.",
                kind="handoff_joined",
            )
            request = {**request, "status": "active"}
            await self.store.save(session, token, request)
        return await self.detail(request_id)

    async def message(self, request_id, message_id, text):
        request = await self.store.get_request(request_id)
        async with self.store.lease(request["session_id"]) as token:
            request, session = await self._current(request_id)
            if session.state != "human_active":
                raise SupportError("claim_required")
            existing = next(
                (m for m in session.history if m.message_id == message_id), None
            )
            if existing:
                if existing.role != "human" or existing.text != text:
                    raise SupportError("message_id_conflict")
                return existing.model_dump(mode="json")
            session, item = append_message(session, message_id, "human", text)
            session = session.model_copy(update={"version": session.version + 1})
            await self.store.save(session, token, request)
            event(
                "human_reply_saved",
                session_id=session.session_id,
                message_id=message_id,
            )
            return item.model_dump(mode="json")

    async def resolve(self, request_id, resolution):
        request = await self.store.get_request(request_id)
        async with self.store.lease(request["session_id"]) as token:
            request = await self.store.get_request(request_id)
            if request.get("status") == "resolved":
                return request
            request, session = await self._current(request_id)
            if session.state != "human_active":
                raise SupportError("claim_required")
            # Extract only recorded staff guidance; provider outages cannot invent/block a resolution.
            replies = [
                m.text
                for m in session.history
                if m.role == "human"
                and m.kind != "resolution"
                and m.sequence >= request.get("history_start_sequence", 0)
            ]
            guidance = (
                "\n".join(replies[-3:])[:1400] or "No resolution details were recorded."
            )
            final_note = resolution.strip()
            summary = "Human support summary\nSupport guidance: " + guidance
            if final_note:
                summary += "\nFinal note: " + final_note
            summary += "\nYou are now back with the Aegis assistant."
            session, _ = append_message(
                session, "resolution-" + request_id, "human", summary, kind="resolution"
            )
            session = session.model_copy(
                update={
                    "state": "active",
                    "pending_intent": None,
                    "version": session.version + 1,
                    "human_resolution": summary[:2000],
                }
            )
            request = {
                **request,
                "status": "resolved",
                "resolution": summary,
                "resolved_at": time.time(),
            }
            await self.store.save(session, token, request)
            event(
                "human_handoff_resolved",
                session_id=session.session_id,
                request_id=request_id,
            )
            return request

    async def end_conversation(self, sid, customer_id, timeout=65):
        await self.store.get(sid, customer_id)
        # Serialize closure behind any already-started business operation.
        async with asyncio.timeout(timeout):
            while True:
                try:
                    async with self.store.lease(sid) as token:
                        session = await self.store.get(sid, customer_id)
                        if session.state == "terminated":
                            return session
                        request = None
                        if session.support_request_id:
                            request = await self.store.get_request(
                                session.support_request_id
                            )
                            if request.get("status") in ["queued", "active"]:
                                request = {**request, "status": "customer_closed"}
                        session = session.model_copy(
                            update={
                                "state": "terminated",
                                "version": session.version + 1,
                            }
                        )
                        session, _ = append_message(
                            session,
                            "end-" + sid,
                            "system",
                            "The customer ended the conversation.",
                            kind="conversation_ended",
                        )
                        await self.store.save(session, token, request)
                        event("conversation_ended", session_id=sid)
                        return session
                except SupportError as exc:
                    if exc.code != "session_busy":
                        raise
                    await asyncio.sleep(0.1)
