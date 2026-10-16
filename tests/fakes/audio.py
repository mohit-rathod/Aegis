import asyncio
from types import SimpleNamespace

from support_assistant.domain.conversation import SupportResponse
from support_assistant.voice.settings import VoiceSettings


class Detector:
    def probability(self, pcm):
        return 0.99 if pcm[0] else 0.01


class STT:
    def __init__(self):
        self.calls = 0
        self.text = "Wait, wrong order."
        self.error = None

    async def transcribe(self, pcm):
        self.calls += 1
        if self.error:
            raise self.error
        return self.text


class TTS:
    def __init__(self):
        self.calls = 0
        self.hold = None
        self.error = None
        self.cancelled = False

    async def stream(self, text):
        self.calls += 1
        try:
            yield 16000, b"\0" * 2048
            if self.hold:
                await self.hold.wait()
            if self.error:
                raise self.error
            yield 16000, b"\0" * 2048
        finally:
            self.cancelled = True


class Service:
    def __init__(self):
        self.turns = []
        self.hold = None
        self.started = asyncio.Event()
        self.terminated = False

    async def handle(self, identity, sid, turn):
        self.turns.append(turn)
        self.started.set()
        if self.hold:
            await self.hold.wait()
        return SupportResponse(
            session_id=sid,
            turn_id=turn.turn_id,
            status="answer",
            answer="Validated answer.",
            session_state="terminated" if self.terminated else "active",
        )


class Transport:
    def __init__(self):
        self.rows = []
        self.coordinator = None
        self.auto_ack = True

    async def send(self, packet):
        self.rows.append(packet)
        if packet["type"] == "audio" and self.auto_ack:
            await self.coordinator.playback.acknowledge(
                packet["playback_id"], packet["sequence"]
            )


def components():
    service = Service()
    stt = STT()
    tts = TTS()
    transport = Transport()
    runtime = SimpleNamespace(
        settings=SimpleNamespace(voice=VoiceSettings(), turn_timeout=0.2),
        service=service,
    )
    resources = SimpleNamespace(stt=stt, tts=tts, capacity=asyncio.Semaphore(2))
    return runtime, resources, transport
