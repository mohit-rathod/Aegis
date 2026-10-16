import hashlib
import json

from support_assistant.routing.registry import REGISTRY_VERSION


def cache_key(session, text, model, prompt_hash):
    # Routing only: do not store generated answers, approval or tool arguments here.
    context = {
        "last_order_id": session.last_order_id,
        "pending_intent": session.pending_intent,
        "human_resolution": session.human_resolution,
    }
    payload = [text.strip(), context, model, prompt_hash, REGISTRY_VERSION]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
