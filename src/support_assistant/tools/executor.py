import json
import time
import uuid
from support_assistant.domain.conversation import SupportError
from support_assistant.safety.authorization import authorize_order
from support_assistant.tools.schemas import OrderArguments
from support_assistant.tools.registry import FUNCTIONS
from support_assistant.observability.logging import event

class ToolExecutor:
    def __init__(self,repository,authority,today):
        self.repository,self.authority,self.today=repository,authority,today
        self._records={}

    async def execute(self,approved,name,arguments,call_id,ledger):
        self.authority.verify(approved)
        if name not in FUNCTIONS: raise SupportError("unknown_tool")
        parsed=OrderArguments.model_validate_json(arguments)
        cache_key=(name,parsed.order_id)
        if cache_key in ledger: return ledger[cache_key]
        start=time.monotonic()
        order=self.repository.get(parsed.order_id)
        try:
            authorize_order(order,approved.session.customer_id)
        except SupportError:
            event("tool_authorization",turn_id=approved.turn.turn_id,tool=name,call_id=call_id,allowed=False)
            raise
        event("tool_authorization",turn_id=approved.turn.turn_id,tool=name,call_id=call_id,allowed=True)
        data=FUNCTIONS[name](order,self.today()) if name=="check_return_eligibility" else FUNCTIONS[name](order)
        result={"evidence_id":"tool-"+uuid.uuid4().hex,"tool":name,"call_id":call_id,"data":data}
        ledger[cache_key]=result
        self._records[(approved.session.session_id,approved.turn.turn_id,result["evidence_id"])]=json.dumps(result,sort_keys=True)
        event("tool_completed",turn_id=approved.turn.turn_id,tool=name,call_id=call_id,
            evidence_id=result["evidence_id"],duration_ms=round((time.monotonic()-start)*1000,2))
        return result

    def verify_records(self,approved,records):
        self.authority.verify(approved)
        if not records: raise SupportError("missing_tool_evidence")
        verified=[]
        for record in records:
            key=(approved.session.session_id,approved.turn.turn_id,record.get("evidence_id"))
            saved=self._records.get(key)
            if not saved or saved!=json.dumps(record,sort_keys=True):
                raise SupportError("forged_tool_evidence")
            verified.append(json.loads(saved))
        return verified

    def discard(self,sid,tid):
        for key in list(self._records):
            if key[:2]==(sid,tid): self._records.pop(key,None)
