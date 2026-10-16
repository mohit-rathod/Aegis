from typing import Protocol

class JsonLLM(Protocol):
    def complete_json(self, system: str, payload: dict) -> dict: ...
