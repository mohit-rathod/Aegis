from contextlib import asynccontextmanager
import secrets
from fastapi import FastAPI,Header,HTTPException,Depends
from pydantic import BaseModel,ConfigDict,Field
from support_assistant.bootstrap_part_a import create_runtime
from support_assistant.domain.conversation import Turn,SupportError
from support_assistant.observability.logging import configure_logging

@asynccontextmanager
async def lifespan(app):
    configure_logging()
    app.state.runtime=await create_runtime()
    try: yield
    finally: await app.state.runtime.aclose()

app=FastAPI(title="Aegis Part A (demo authentication)",lifespan=lifespan)

class MessageRequest(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    turn_id: str=Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    text: str=Field(max_length=2000)
    channel: str="text"

async def customer(authorization: str=Header(default="")):
    runtime=app.state.runtime
    token=authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
    for identity,expected in [("customer-a",runtime.part.demo_a_token),("customer-b",runtime.part.demo_b_token)]:
        if expected and token and secrets.compare_digest(token.encode(),expected.encode()): return identity
    raise HTTPException(401,"Invalid demo credentials")

async def admin(authorization: str=Header(default="")):
    expected=app.state.runtime.part.admin_token
    if not expected or not secrets.compare_digest(authorization.encode(),("Bearer "+expected).encode()):
        raise HTTPException(403,"Administrative credentials required")

@app.get("/health")
async def health(): return {"status":"alive"}

@app.get("/ready")
async def ready():
    try: await app.state.runtime.redis.ping()
    except Exception: raise HTTPException(503,"Not ready") from None
    return {"status":"ready"}

@app.post("/sessions",status_code=201)
async def create_session(identity=Depends(customer)):
    session=await app.state.runtime.store.create(identity)
    return {"session_id":session.session_id,"state":session.state,"mode":"demo"}

@app.post("/sessions/{session_id}/messages")
async def message(session_id:str,body:MessageRequest,identity=Depends(customer)):
    if len(session_id)!=32 or not all(c in "0123456789abcdef" for c in session_id):
        raise HTTPException(404,"Session unavailable")
    if body.channel not in ["text","voice"]: raise HTTPException(422,"Invalid channel")
    try:
        result=await app.state.runtime.service.handle(identity,session_id,Turn(**body.model_dump()))
    except SupportError as exc:
        raise HTTPException(409 if exc.code=="turn_id_conflict" else 404,exc.code) from None
    return result.model_dump(mode="json")

@app.get("/admin/classifier-metrics",dependencies=[Depends(admin)])
async def classifier_metrics(): return await app.state.runtime.cache.metrics()

@app.get("/admin/support-requests",dependencies=[Depends(admin)])
async def support_requests():
    # Bounded intake inspection for the demo. This endpoint exposes customer statements only to the operator.
    import json
    runtime = app.state.runtime
    rows = []
    async for key in runtime.redis.scan_iter(match=f"{runtime.part.prefix}:support:*"):
        raw = await runtime.redis.get(key)
        if raw: rows.append(json.loads(raw))
        if len(rows) >= 20: break
    return rows
