import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from support_assistant.bootstrap import create_runtime
from support_assistant.domain.conversation import SupportError, Turn
from support_assistant.entrypoints.api.voice import voice_socket
from support_assistant.observability.logging import configure_logging


@asynccontextmanager
async def lifespan(app):
    configure_logging()
    app.state.runtime = await create_runtime()
    try:
        yield
    finally:
        await app.state.runtime.aclose()


app = FastAPI(title="Aegis Support API", lifespan=lifespan)
WEB = Path(__file__).resolve().parents[1] / "web"
app.mount("/assets", StaticFiles(directory=WEB), name="assets")
app.add_api_websocket_route("/sessions/{session_id}/channel", voice_socket)


@app.get("/", include_in_schema=False)
async def frontend():
    return FileResponse(WEB / "index.html")


@app.get("/admin", include_in_schema=False)
async def admin_frontend():
    return FileResponse(WEB / "admin.html")


class MessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    turn_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    text: str = Field(max_length=2000)
    channel: str = "text"


async def customer(authorization: str = Header(default="")):
    runtime = app.state.runtime
    token = (
        authorization.removeprefix("Bearer ")
        if authorization.startswith("Bearer ")
        else ""
    )
    for identity, expected in [
        ("customer-a", runtime.settings.demo_a_token),
        ("customer-b", runtime.settings.demo_b_token),
    ]:
        if (
            expected
            and token
            and secrets.compare_digest(token.encode(), expected.encode())
        ):
            return identity
    raise HTTPException(401, "Invalid demo credentials")


async def admin(authorization: str = Header(default="")):
    expected = app.state.runtime.settings.admin_token
    if not expected or not secrets.compare_digest(
        authorization.encode(), ("Bearer " + expected).encode()
    ):
        raise HTTPException(403, "Administrative credentials required")


@app.get("/health")
async def health():
    return {"status": "alive"}


@app.get("/ready")
async def ready():
    try:
        await app.state.runtime.redis.ping()
    except Exception:
        raise HTTPException(503, "Not ready") from None
    return {"status": "ready"}


@app.post("/sessions", status_code=201)
async def create_session(identity=Depends(customer)):
    session = await app.state.runtime.store.create(identity)
    return {"session_id": session.session_id, "state": session.state, "mode": "demo"}


@app.get("/sessions/{session_id}")
async def session_detail(session_id: str, identity=Depends(customer)):
    try:
        return (await app.state.runtime.store.get(session_id, identity)).model_dump(
            mode="json"
        )
    except SupportError:
        raise HTTPException(404, "Session unavailable") from None


@app.post("/sessions/{session_id}/end")
async def end_conversation(session_id: str, identity=Depends(customer)):
    try:
        session = await app.state.runtime.service.human.end_conversation(
            session_id, identity, app.state.runtime.settings.turn_timeout + 5
        )
        return {"session_id": session_id, "state": session.state}
    except SupportError as exc:
        raise HTTPException(409, exc.code) from None
    except TimeoutError:
        raise HTTPException(
            503, "Closure is waiting for an active operation; retry shortly."
        ) from None


@app.post("/sessions/{session_id}/messages")
async def message(session_id: str, body: MessageRequest, identity=Depends(customer)):
    if len(session_id) != 32 or not all(c in "0123456789abcdef" for c in session_id):
        raise HTTPException(404, "Session unavailable")
    if body.channel not in ["text", "voice"]:
        raise HTTPException(422, "Invalid channel")
    try:
        result = await app.state.runtime.service.handle(
            identity, session_id, Turn(**body.model_dump())
        )
    except SupportError as exc:
        raise HTTPException(
            409 if exc.code == "turn_id_conflict" else 404, exc.code
        ) from None
    return result.model_dump(mode="json")


@app.get("/admin/classifier-metrics", dependencies=[Depends(admin)])
async def classifier_metrics():
    return await app.state.runtime.cache.metrics()


@app.get("/admin/support-requests", dependencies=[Depends(admin)])
async def support_requests():
    # Bounded intake inspection for the demo. This endpoint exposes customer statements only to the operator.
    import json

    runtime = app.state.runtime
    rows = []
    async for key in runtime.redis.scan_iter(
        match=f"{runtime.settings.prefix}:support:*"
    ):
        raw = await runtime.redis.get(key)
        if raw:
            request = json.loads(raw)
            if request.get("mode") == "live_human_handoff" and request.get(
                "status"
            ) in ["queued", "active"]:
                rows.append(request)
        if len(rows) >= 20:
            break
    return rows


class HumanMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    message_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    text: str = Field(min_length=1, max_length=2000)


class ResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    resolution: str = Field(default="", max_length=2000)


class FaultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: str


def handoff_error(exc):
    return HTTPException(
        404
        if exc.code in ["support_request_not_available", "session_not_available"]
        else 409,
        exc.code,
    )


@app.get("/admin/support-requests/{request_id}", dependencies=[Depends(admin)])
async def handoff_detail(request_id: str):
    try:
        return await app.state.runtime.service.human.detail(request_id)
    except SupportError as exc:
        raise handoff_error(exc) from None


@app.post("/admin/support-requests/{request_id}/claim", dependencies=[Depends(admin)])
async def handoff_claim(request_id: str):
    try:
        return await app.state.runtime.service.human.claim(request_id)
    except SupportError as exc:
        raise handoff_error(exc) from None


@app.post(
    "/admin/support-requests/{request_id}/messages", dependencies=[Depends(admin)]
)
async def handoff_message(request_id: str, body: HumanMessageRequest):
    if not body.text.strip():
        raise HTTPException(422, "Message cannot be empty")
    try:
        return await app.state.runtime.service.human.message(
            request_id, "human-" + body.message_id, body.text
        )
    except SupportError as exc:
        raise handoff_error(exc) from None


@app.post("/admin/support-requests/{request_id}/resolve", dependencies=[Depends(admin)])
async def handoff_resolve(request_id: str, body: ResolutionRequest):
    try:
        return await app.state.runtime.service.human.resolve(
            request_id, body.resolution
        )
    except SupportError as exc:
        raise handoff_error(exc) from None


@app.post("/admin/sessions/{session_id}/fault", dependencies=[Depends(admin)])
async def arm_fault(session_id: str, body: FaultRequest):
    runtime = app.state.runtime
    try:
        session = await runtime.store.get_internal(session_id)
        if session.state == "terminated":
            raise SupportError("session_terminated")
        await runtime.voice.faults.arm(session_id, body.kind)
    except SupportError as exc:
        raise handoff_error(exc) from None
    return {"armed": body.kind, "expires_seconds": 300, "one_shot": True}
