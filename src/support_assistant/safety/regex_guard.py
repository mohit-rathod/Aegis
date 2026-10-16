import re
import unicodedata
from support_assistant.safety.safe_responses import MESSAGES

# Narrow command patterns. Contextual or encoded attacks still require the LLM gate.
RULES = [
    ("instruction_override", re.compile(r"^\s*(?:please\s+)?(?:ignore|disregard|forget)\s+(?:all\s+)?(?:previous|prior|system|developer)\s+(?:instructions|prompts|rules)\b", re.I)),
    ("prompt_extraction", re.compile(r"^\s*(?:please\s+)?(?:show|reveal|print|repeat|display)\s+(?:me\s+)?(?:your\s+|the\s+)?(?:system|developer|internal)\s+(?:prompt|instructions)\b", re.I)),
    ("credential_request", re.compile(r"^\s*(?:please\s+)?(?:give|show|reveal|send)\s+(?:me\s+)?(?:your|the|another customer's)\s+(?:api[ _-]?key|password|otp|verification code)\b", re.I)),
    ("credential_pasted", re.compile(r"\b(?:hf_[A-Za-z0-9]{20,}|gsk_[A-Za-z0-9]{20,})\b")),
    ("credential_pasted", re.compile(r"\b(?:password|api[ _-]?key|otp|verification code)\s*[:=]\s*[^\s,;]{4,}", re.I)),
]

class RegexGuard:
    def check(self, text):
        if not text.strip(): return "empty"
        if len(text) > 2000: return "too_long"
        normalized = unicodedata.normalize("NFKC", text)
        for name, pattern in RULES:
            if pattern.search(normalized): return name
        return None
