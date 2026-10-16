from typing import Protocol


class VoiceTransport(Protocol):
    async def send(self, packet: dict) -> None: ...


class VoiceActivityDetector(Protocol):
    def probability(self, pcm: bytes) -> float: ...
