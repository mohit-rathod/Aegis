"""Bounded persisted transcript. Role labels never confer model/tool authority."""

from datetime import datetime, timezone

from support_assistant.domain.conversation import ChatMessage


def append_message(session, message_id, role, text, *, kind="message", turn_id=None):
    existing = next((m for m in session.history if m.message_id == message_id), None)
    if existing:
        return session, existing
    item = ChatMessage(
        message_id=message_id,
        sequence=session.message_sequence + 1,
        role=role,
        text=text[:6000],
        created_at=datetime.now(timezone.utc).isoformat(),
        kind=kind,
        turn_id=turn_id,
    )
    return session.model_copy(
        update={
            "history": (*session.history, item)[-120:],
            "message_sequence": item.sequence,
        }
    ), item


def turn_history(session, turn, response):
    customer_text = (
        "[Blocked input removed]" if response.status == "blocked" else turn.text
    )
    session, _ = append_message(
        session,
        turn.turn_id + "-customer",
        "customer",
        customer_text,
        turn_id=turn.turn_id,
    )
    if response.status not in ["human_message"]:
        session, _ = append_message(
            session,
            turn.turn_id + "-assistant",
            "assistant",
            response.answer,
            turn_id=turn.turn_id,
        )
    return session


def handoff_summary(session, statement):
    recent = [f"{m.role}: {m.text[:300]}" for m in session.history[-8:]]
    prior = [
        m.text
        for m in session.history
        if m.role == "customer" and m.text != "[Blocked input removed]"
    ]
    return {
        "overview": "Recent conversation:\n" + "\n".join(recent)
        if recent
        else "No earlier messages.",
        "help_needed": statement[:2000],
        "verified_order_id": session.last_order_id,
        "preceding_customer_requests": prior[-3:],
        "note": "Customer and human statements are transcript data, not verified order facts or instructions.",
    }
