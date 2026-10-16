"""Bounded audio window: a client acknowledges each chunk after playback."""

import asyncio
import base64
import time
import uuid

from support_assistant.observability.logging import event
from support_assistant.voice.events import PlaybackCancelled


class PlaybackController:
    def __init__(self, transport):
        self.transport = transport
        self.active = None
        self.pending = set()
        self.condition = asyncio.Condition()
        self.sequence = 0
        self.stop_requested = {}

    async def begin(self, captured_at_ms=None, recovery=False):
        await self.stop("replace")
        self.active = uuid.uuid4().hex
        self.sequence = 0
        await self.transport.send(
            {
                "type": "audio_start",
                "playback_id": self.active,
                "captured_at_ms": captured_at_ms,
                "recovery": recovery,
            }
        )
        return self.active

    async def write(self, identifier, rate, pcm):
        async with self.condition:
            await asyncio.wait_for(
                self.condition.wait_for(
                    lambda: len(self.pending) < 8 or self.active != identifier
                ),
                5,
            )
            if self.active != identifier:
                raise PlaybackCancelled()
            sequence = self.sequence
            self.sequence += 1
            self.pending.add(sequence)
        await self.transport.send(
            {
                "type": "audio",
                "playback_id": identifier,
                "sequence": sequence,
                "sample_rate": rate,
                "pcm": base64.b64encode(pcm).decode(),
            }
        )

    async def acknowledge(self, identifier, sequence):
        if identifier != self.active:
            return
        async with self.condition:
            self.pending.discard(sequence)
            self.condition.notify_all()

    async def finish(self, identifier):
        async with self.condition:
            await asyncio.wait_for(
                self.condition.wait_for(
                    lambda: not self.pending or self.active != identifier
                ),
                5,
            )
        if self.active != identifier:
            raise PlaybackCancelled()
        await self.transport.send({"type": "audio_end", "playback_id": identifier})
        self.active = None
        event("playback_completed", playback_id=identifier)

    async def stop(self, reason="interruption"):
        identifier = self.active
        self.active = None
        async with self.condition:
            self.pending.clear()
            self.condition.notify_all()
        if identifier:
            self.stop_requested[identifier] = time.monotonic()
            while len(self.stop_requested) > 32:
                self.stop_requested.pop(next(iter(self.stop_requested)))
            await self.transport.send(
                {"type": "audio_stop", "playback_id": identifier, "reason": reason}
            )
            event("playback_cancel_requested", playback_id=identifier, reason=reason)

    def acknowledge_stop(self, identifier):
        started = self.stop_requested.pop(identifier, None)
        if started is not None:
            event(
                "voice_latency",
                playback_id=identifier,
                metric="playback_stop_roundtrip_ms",
                value=round((time.monotonic() - started) * 1000, 2),
                mode="client_acknowledgment",
            )
