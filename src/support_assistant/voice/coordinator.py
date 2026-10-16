"""Audio is a channel adapter. All business turns go through SupportService."""

import asyncio
import time

from support_assistant.adapters.tts.local_recovery import RECOVERY_TEXT, recording
from support_assistant.application.ports.audio import (
    VoiceActivityDetector,
    VoiceTransport,
)
from support_assistant.domain.conversation import Turn
from support_assistant.observability.logging import event
from support_assistant.voice.endpointing import Endpointer
from support_assistant.voice.events import PlaybackCancelled, SpeechFailure
from support_assistant.voice.playback_controller import PlaybackController
from support_assistant.voice.state import VoiceState
from support_assistant.voice.turn_tracker import TurnTracker


class VoiceCoordinator:
    def __init__(
        self, runtime, identity, session_id, transport: VoiceTransport, resources
    ):
        self.runtime, self.identity, self.sid = runtime, identity, session_id
        self.transport, self.resources = transport, resources
        self.settings = runtime.settings.voice
        self.endpoint = Endpointer(self.settings)
        self.tracker = TurnTracker()
        self.playback = PlaybackController(transport)
        self.queue = asyncio.Queue(maxsize=2)
        self.worker = None
        self.play_task = None
        self.detector: VoiceActivityDetector | None = None
        self.enabled = False
        self.closed = False
        self.state = VoiceState.LISTENING
        self.processing = False

    async def start(self):
        self.worker = asyncio.create_task(self._run())
        await self.transport.send({"type": "ready", "session_id": self.sid})

    async def status(self, state):
        self.state = state
        await self.transport.send({"type": "state", "state": state.value})

    async def enable(self):
        if self.closed:
            return
        if not self.detector:
            self.detector = await self.resources.detector()
        self.enabled = True
        self.endpoint.reset()
        await self.transport.send({"type": "voice_ready"})
        await self.status(VoiceState.LISTENING)

    async def disable(self):
        self.enabled = False
        self.endpoint.reset()
        await self._interrupt("microphone_stopped")
        await self.status(VoiceState.LISTENING)

    async def _interrupt(self, reason):
        generation = self.tracker.interrupt()
        await self.playback.stop(reason)
        if self.play_task and not self.play_task.done():
            self.play_task.cancel()
        event(
            "voice_interruption",
            session_id=self.sid,
            generation=generation,
            reason=reason,
        )
        return generation

    async def frame(self, pcm, captured_at_ms):
        if not self.enabled or self.closed:
            return
        probability = await asyncio.wait_for(
            asyncio.to_thread(self.detector.probability, pcm), 1
        )
        for kind, value in self.endpoint.feed(
            pcm, probability, time.monotonic(), captured_at_ms
        ):
            if kind == "speech_start":
                await self._interrupt("confirmed_speech")
                await self.status(VoiceState.CAPTURING)
            elif kind == "utterance":
                await self._enqueue(
                    {
                        "audio": value,
                        "generation": self.tracker.generation,
                        "speak": True,
                    }
                )
            elif kind == "too_long":
                await self._interrupt("utterance_limit")
                await self.recover("long")

    async def text(self, text, turn_id=None):
        if self.closed:
            return
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            await self.transport.send(
                {"type": "error", "message": "Enter a message of 1–2000 characters."}
            )
            return
        generation = await self._interrupt("text_input")
        await self._enqueue(
            {
                "text": text,
                "turn_id": turn_id,
                "generation": generation,
                "speak": self.enabled,
            }
        )

    async def _enqueue(self, job):
        try:
            self.queue.put_nowait(job)
        except asyncio.QueueFull:
            await self.transport.send(
                {
                    "type": "error",
                    "message": "Please wait for the current turn and try again.",
                }
            )

    async def _run(self):
        while not self.closed:
            job = await self.queue.get()
            self.processing = True
            try:
                if "audio" not in job or self.tracker.current(job["generation"]):
                    await self._process(job)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                event(
                    "voice_turn_failed",
                    session_id=self.sid,
                    category=type(exc).__name__,
                )
                if not self.closed:
                    await self.recover("stt" if "audio" in job else "tts")
            finally:
                self.processing = False
                self.queue.task_done()

    async def _process(self, job):
        utterance = job.get("audio")
        generation = job["generation"]
        started = time.monotonic()
        text = job.get("text")
        if utterance:
            await self.status(VoiceState.TRANSCRIBING)
            try:
                async with asyncio.timeout(self.settings.stt_timeout + 1):
                    async with self.resources.capacity:
                        text = await self.resources.stt.transcribe(utterance.pcm)
            except (SpeechFailure, TimeoutError) as exc:
                event(
                    "speech_provider_failed",
                    provider="stt",
                    category=str(exc) if isinstance(exc, SpeechFailure) else "deadline",
                )
                if self.tracker.current(generation):
                    await self.recover("stt")
                return
            if not self.tracker.current(generation):
                return
            if not text or not text.strip() or len(text) > 2000:
                await self.recover("stt")
                return
        turn_id = job.get("turn_id") or self.tracker.new_id()
        await self.transport.send(
            {
                "type": "transcript",
                "text": text,
                "turn_id": turn_id,
                "channel": "voice" if utterance else "text",
            }
        )
        await self.status(VoiceState.PROCESSING)
        # Never cancel a business turn merely because its audio was superseded.
        response = await self.runtime.service.handle(
            self.identity,
            self.sid,
            Turn(turn_id=turn_id, text=text, channel="voice" if utterance else "text"),
        )
        current = self.tracker.current(generation)
        await self.transport.send(
            {
                "type": "response",
                **response.model_dump(mode="json"),
                "superseded": not current,
            }
        )
        event(
            "voice_business_completed",
            session_id=self.sid,
            turn_id=turn_id,
            superseded=not current,
            duration_ms=round((time.monotonic() - started) * 1000, 2),
        )
        if current and job["speak"] and not self.closed and self.enabled:
            self.play_task = asyncio.create_task(
                self._speak(response.answer, utterance)
            )
            try:
                await self.play_task
            except asyncio.CancelledError:
                if self.closed:
                    raise
        if response.session_state == "terminated":
            self.closed = True
            self.enabled = False
            await self.status(VoiceState.CLOSED)
            await self.transport.send(
                {"type": "closed", "reason": "session_terminated"}
            )
        elif self.tracker.current(generation):
            await self.status(VoiceState.LISTENING)

    async def _speak(self, text, utterance=None):
        synthesis_started = time.monotonic()
        await self.status(VoiceState.SPEAKING)
        identifier = await self.playback.begin(
            utterance.captured_at_ms if utterance else None
        )
        first = True
        stream = None
        try:
            async with asyncio.timeout(self.settings.tts_timeout + 8):
                async with self.resources.capacity:
                    stream = self.resources.tts.stream(text)
                    async for rate, pcm in stream:
                        await self.playback.write(identifier, rate, pcm)
                        if first:
                            first = False
                            event(
                                "tts_first_chunk",
                                session_id=self.sid,
                                duration_ms=round(
                                    (time.monotonic() - synthesis_started) * 1000, 2
                                ),
                            )
                            if utterance:
                                event(
                                    "voice_latency",
                                    session_id=self.sid,
                                    playback_id=identifier,
                                    metric="speech_frame_arrival_to_first_audio_sent_ms",
                                    value=round(
                                        (time.monotonic() - utterance.ended_at) * 1000,
                                        2,
                                    ),
                                    mode="server_estimate",
                                )
                    if first:
                        raise SpeechFailure("tts_empty_audio")
                    await self.playback.finish(identifier)
        except PlaybackCancelled:
            pass
        except (SpeechFailure, TimeoutError, OSError) as exc:
            event(
                "speech_provider_failed",
                provider="tts",
                category=str(exc)
                if isinstance(exc, SpeechFailure)
                else type(exc).__name__,
            )
            await self.playback.stop("tts_failure")
            await self.recover("tts")
        finally:
            if stream and hasattr(stream, "aclose"):
                await stream.aclose()

    async def recover(self, kind):
        await self.status(VoiceState.RECOVERING)
        await self.transport.send(
            {"type": "recovery", "category": kind, "message": RECOVERY_TEXT[kind]}
        )
        event("voice_recovery", session_id=self.sid, category=kind)
        if self.enabled:
            identifier = await self.playback.begin(recovery=True)
            try:
                async with asyncio.timeout(10):
                    async for rate, pcm in recording(kind):
                        await self.playback.write(identifier, rate, pcm)
                    await self.playback.finish(identifier)
            except (TimeoutError, PlaybackCancelled, OSError):
                await self.playback.stop("recovery_unavailable")
        if not self.closed:
            await self.status(VoiceState.LISTENING)

    async def aclose(self):
        self.closed = True
        self.enabled = False
        if self.play_task and not self.play_task.done():
            self.play_task.cancel()
        # Allow the shared service to finish/commit; do not kill business work on disconnect.
        if self.worker:
            if not self.processing:
                self.worker.cancel()
            try:
                await asyncio.wait_for(
                    asyncio.shield(self.worker), self.runtime.settings.turn_timeout + 2
                )
            except TimeoutError:
                self.worker.cancel()
            except asyncio.CancelledError:
                pass
            if not self.worker.done():
                self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)
        if self.play_task:
            await asyncio.gather(self.play_task, return_exceptions=True)
