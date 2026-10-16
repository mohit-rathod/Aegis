from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

class Session(FrozenModel):
    session_id: str
    customer_id: str
    state: Literal["active", "awaiting_clarification", "terminated"] = "active"
    last_order_id: str | None = None
    pending_intent: str | None = None
    version: int = 0
    support_request_id: str | None = None

class Turn(FrozenModel):
    turn_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    text: str = Field(max_length=2000)
    channel: Literal["text", "voice"] = "text"

class SupportResponse(FrozenModel):
    session_id: str
    turn_id: str
    status: str
    answer: str
    intent: str | None = None
    citations: tuple[str, ...] = ()
    session_state: str = "active"
    support_request_id: str | None = None

class SupportError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
