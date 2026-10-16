import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

from support_assistant.domain.conversation import Session, SupportError, Turn


@dataclass(frozen=True)
class Approval:
    digest: str
    expires_at: float
    signature: str


@dataclass(frozen=True)
class ApprovedTurn:
    session: Session
    turn: Turn
    approval: Approval


class ApprovalAuthority:
    """Process-local proof of the exact immutable turn/context passed by the gate.

    This is a dispatch invariant, not a sandbox against arbitrary Python execution.
    Never deserialize approvals from public requests.
    """

    def __init__(self, lifetime=90):
        self._key = secrets.token_bytes(32)
        self.lifetime = lifetime

    def _digest(self, session, turn):
        payload = {"session": session.model_dump(), "turn": turn.model_dump()}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def _issue(self, session, turn):
        digest = self._digest(session, turn)
        expires = time.monotonic() + self.lifetime
        signature = hmac.new(
            self._key, f"{digest}:{expires}".encode(), hashlib.sha256
        ).hexdigest()
        return ApprovedTurn(session, turn, Approval(digest, expires, signature))

    def verify(self, approved):
        if not isinstance(approved, ApprovedTurn):
            raise SupportError("missing_input_approval")
        p = approved.approval
        signature = hmac.new(
            self._key, f"{p.digest}:{p.expires_at}".encode(), hashlib.sha256
        ).hexdigest()
        if (
            p.expires_at < time.monotonic()
            or not hmac.compare_digest(signature, p.signature)
            or p.digest != self._digest(approved.session, approved.turn)
        ):
            raise SupportError("invalid_input_approval")
