from contextlib import asynccontextmanager
import hashlib
import json
import uuid
from support_assistant.domain.conversation import Session, SupportResponse, SupportError

COMMIT = """
if redis.call('GET',KEYS[1]) ~= ARGV[1] then return 0 end
-- One MSET atomically records every business value. No stream/index write can
-- fail later and leave a success reply without the support request.
if ARGV[5] ~= '' then
  redis.call('MSET',KEYS[2],ARGV[2],KEYS[3],ARGV[3],KEYS[4],ARGV[5])
else
  redis.call('MSET',KEYS[2],ARGV[2],KEYS[3],ARGV[3])
end
redis.call('EXPIRE',KEYS[2],ARGV[4])
redis.call('EXPIRE',KEYS[3],ARGV[4])
return 1
"""

class RedisSessionStore:
    def __init__(self,redis,prefix="aegis",ttl=86400,lease_seconds=75):
        self.redis,self.prefix,self.ttl,self.lease_seconds=redis,prefix,ttl,lease_seconds

    def key(self,sid): return f"{self.prefix}:session:{sid}"
    def turn_key(self,sid,tid): return f"{self.key(sid)}:turn:{tid}"

    async def create(self,customer_id):
        session=Session(session_id=uuid.uuid4().hex,customer_id=customer_id)
        await self.redis.set(self.key(session.session_id),session.model_dump_json(),ex=self.ttl)
        return session

    async def get(self,sid,customer_id):
        raw=await self.redis.get(self.key(sid))
        if raw is None: raise SupportError("session_not_available")
        session=Session.model_validate_json(raw)
        if session.customer_id != customer_id: raise SupportError("session_not_available")
        return session

    @asynccontextmanager
    async def lease(self,sid):
        key=f"{self.key(sid)}:lock"
        token=uuid.uuid4().hex
        if not await self.redis.set(key,token,nx=True,ex=self.lease_seconds):
            raise SupportError("session_busy")
        try:
            yield token
        finally:
            await self.redis.eval("if redis.call('GET',KEYS[1]) == ARGV[1] then return redis.call('DEL',KEYS[1]) end return 0",1,key,token)

    def fingerprint(self,turn):
        return hashlib.sha256(turn.model_dump_json().encode()).hexdigest()

    async def replay(self,session,turn):
        raw=await self.redis.get(self.turn_key(session.session_id,turn.turn_id))
        if not raw: return None
        saved=json.loads(raw)
        if saved["fingerprint"] != self.fingerprint(turn):
            raise SupportError("turn_id_conflict")
        return SupportResponse.model_validate(saved["response"])

    async def commit(self,session,turn,response,token,support_request=None):
        reply=json.dumps({"fingerprint":self.fingerprint(turn),"response":response.model_dump(mode="json")})
        request=json.dumps(support_request) if support_request else ""
        request_id=support_request["request_id"] if support_request else "none"
        ok=await self.redis.eval(COMMIT,4,
            f"{self.key(session.session_id)}:lock",self.key(session.session_id),
            self.turn_key(session.session_id,turn.turn_id),f"{self.prefix}:support:{request_id}",
            token,session.model_dump_json(),reply,self.ttl,request)
        if not ok: raise SupportError("session_lease_lost")
