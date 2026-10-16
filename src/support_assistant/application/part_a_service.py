import asyncio
import hashlib
import time
import uuid
from datetime import datetime,timezone
from support_assistant.domain.conversation import SupportResponse,SupportError
from support_assistant.domain.evidence import InputDecision
from support_assistant.domain.errors import ProviderError
from support_assistant.rag.grounding import read_prompt
from support_assistant.safety.safe_responses import MESSAGES
from support_assistant.observability.logging import event

class PartASupportService:
    def __init__(self,store,regex,llm,classifier,dispatcher,responses,authority,executor,
                 turn_timeout=60,max_active=32):
        self.store,self.regex,self.llm,self.classifier=store,regex,llm,classifier
        self.dispatcher,self.responses,self.authority,self.executor=dispatcher,responses,authority,executor
        self.turn_timeout=turn_timeout
        self.max_active=max_active
        self.active=0

    async def handle(self,customer_id,session_id,turn):
        started=time.monotonic()
        event("turn_received",session_id=session_id,turn_id=turn.turn_id,channel=turn.channel)
        if self.active>=self.max_active:
            return SupportResponse(session_id=session_id,turn_id=turn.turn_id,status="busy",answer=MESSAGES["busy"])
        self.active+=1
        owns_turn=[]
        try:
            async with asyncio.timeout(self.turn_timeout):
                return await self._handle(customer_id,session_id,turn,owns_turn)
        except asyncio.TimeoutError:
            event("turn_failed",session_id=session_id,turn_id=turn.turn_id,category="turn_deadline")
            return SupportResponse(session_id=session_id,turn_id=turn.turn_id,status="unavailable",answer=MESSAGES["unavailable"])
        except SupportError as exc:
            # Invalid session/identity and reused turn IDs are explicit client errors.
            if exc.code in ["session_not_available","turn_id_conflict"]: raise
            status="busy" if exc.code in ["session_busy","classifier_busy"] else "unavailable"
            event("turn_failed",session_id=session_id,turn_id=turn.turn_id,category=exc.code)
            return SupportResponse(session_id=session_id,turn_id=turn.turn_id,status=status,answer=MESSAGES[status])
        except Exception as exc:
            category=str(exc) if isinstance(exc,ProviderError) else type(exc).__name__
            event("turn_failed",session_id=session_id,turn_id=turn.turn_id,category=category)
            return SupportResponse(session_id=session_id,turn_id=turn.turn_id,status="unavailable",answer=MESSAGES["unavailable"])
        finally:
            if owns_turn: self.executor.discard(session_id,turn.turn_id)
            self.active-=1
            event("turn_finished",session_id=session_id,turn_id=turn.turn_id,
                total_ms=round((time.monotonic()-started)*1000,2))

    async def _handle(self,customer_id,sid,turn,owns_turn):
        # Check ownership before acquiring a session lease.
        await self.store.get(sid,customer_id)
        async with self.store.lease(sid) as token:
            owns_turn.append(True)
            session=await self.store.get(sid,customer_id)
            replay=await self.store.replay(session,turn)
            if replay:
                event("turn_replayed",session_id=sid,turn_id=turn.turn_id)
                return replay
            if session.state=="terminated":
                return SupportResponse(session_id=sid,turn_id=turn.turn_id,status="terminated",
                    answer=MESSAGES["terminated"],session_state="terminated",support_request_id=session.support_request_id)
            rule=self.regex.check(turn.text)
            if rule:
                event("input_rejected",session_id=sid,turn_id=turn.turn_id,rule=rule)
                response=SupportResponse(session_id=sid,turn_id=turn.turn_id,status="blocked",answer=MESSAGES[rule],session_state=session.state)
                await self.store.commit(session,turn,response,token)
                return response
            check_start=time.monotonic()
            decision=InputDecision.model_validate(await self.llm.complete_json(read_prompt("input_guard.md"),
                {"untrusted_customer_message":turn.text,"context":{"last_order_id":session.last_order_id,
                    "pending_intent":session.pending_intent}}))
            event("input_checked",session_id=sid,turn_id=turn.turn_id,allowed=decision.allowed,
                duration_ms=round((time.monotonic()-check_start)*1000,2))
            if not decision.allowed:
                response=SupportResponse(session_id=sid,turn_id=turn.turn_id,status="blocked",answer=MESSAGES["semantic_block"],session_state=session.state)
                await self.store.commit(session,turn,response,token)
                return response
            approved=self.authority._issue(session,turn)
            route=await self.classifier.classify(approved)
            self.authority.verify(approved)
            if route.needs_clarification:
                from support_assistant.domain.orders import HandlerResult
                result=HandlerResult("clarify")
            else:
                event("handler_started",session_id=sid,turn_id=turn.turn_id,intent=route.intent)
                try:
                    result=await self.dispatcher.dispatch(approved,route)
                except SupportError as exc:
                    if exc.code!="order_not_available": raise
                    from support_assistant.domain.orders import HandlerResult
                    result=HandlerResult("order_not_available")
            output_start=time.monotonic()
            status,answer,citations=await self.responses.render(approved,result)
            event("output_checked",session_id=sid,turn_id=turn.turn_id,status=status,source_count=len(citations),duration_ms=round((time.monotonic()-output_start)*1000,2))
            request=None
            next_session=session.model_copy(update={"version":session.version+1})
            if status=="clarify":
                next_session=next_session.model_copy(update={"state":"awaiting_clarification","pending_intent":route.intent})
            elif status=="escalated":
                request_id="SUP-"+uuid.uuid5(uuid.NAMESPACE_URL,sid).hex[:16]
                request={"request_id":request_id,"session_id":sid,"customer_id":customer_id,
                    "customer_statement":result.data["customer_statement"],
                    "verified_order_id":result.data["verified_order_id"],
                    "created_at":datetime.now(timezone.utc).isoformat(),"status":"queued",
                    "mode":"demo_support_intake"}
                next_session=next_session.model_copy(update={"state":"terminated","pending_intent":None,"support_request_id":request_id})
            elif status=="answer":
                next_session=next_session.model_copy(update={"state":"active","pending_intent":None,
                    "last_order_id":result.verified_order_id or session.last_order_id})
            response=SupportResponse(session_id=sid,turn_id=turn.turn_id,status=status,answer=answer,
                intent=route.intent,citations=citations,session_state=next_session.state,
                support_request_id=next_session.support_request_id)
            await self.store.commit(next_session,turn,response,token,request)
            event("session_updated",session_id=sid,turn_id=turn.turn_id,
                previous_state=session.state,state=next_session.state,support_request_id=next_session.support_request_id)
            return response
