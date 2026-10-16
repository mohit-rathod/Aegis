"""Full-duplex channel. Accepted user jobs are FIFO; only playback is superseded."""

import asyncio
import re
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
from support_assistant.voice.faults import fail_midstream
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
        self.worker = self.observer = self.play_task = None
        self.detector: VoiceActivityDetector | None = None
        self.enabled = self.closed = self.disconnected = self.stopping = False
        self.accepting = True
        self.processing = False
        self.state = VoiceState.LISTENING
        self.sequence = 0
        self.playback_metadata = {}
        self.accepted_ids = set()

    async def start(self):
        self.worker = asyncio.create_task(self._run())
        await self.transport.send(
            {
                "type": "ready",
                "session_id": self.sid,
                "provider_mode": getattr(self.resources, "mode", "test_double"),
                "pipeline": "microphone → Silero VAD → Groq Whisper → guarded Groq support → Piper → speakers",
            }
        )
        if getattr(self.runtime, "store", None):
            session = await self.runtime.store.get(self.sid, self.identity)
            self.sequence = session.message_sequence
            await self.transport.send(
                {
                    "type": "history",
                    "messages": [m.model_dump(mode="json") for m in session.history],
                    "state": session.state,
                    "support_request_id": session.support_request_id,
                }
            )
            self.observer = asyncio.create_task(self._observe())

    async def status(self, state):
        self.state = state
        if not self.disconnected:
            await self.transport.send({"type": "state", "state": state.value})

    async def enable(self):
        if self.closed or self.stopping:
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
        if not self.enabled or not self.accepting or self.closed:
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
                await self._enqueue({"audio": value, "speak": True})
            elif kind == "too_long":
                await self._interrupt("utterance_limit")
                await self.recover("long")

    async def text(self, text, turn_id=None, submitted_at_ms=None):
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            await self.transport.send(
                {"type": "error", "message": "Enter a message of 1–2000 characters."}
            )
            return
        if turn_id is not None and (
            not isinstance(turn_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", turn_id)
        ):
            raise ValueError("Invalid turn ID")
        await self._interrupt("text_input")
        await self._enqueue(
            {
                "text": text,
                "turn_id": turn_id,
                "speak": self.enabled,
                "submitted_at_ms": submitted_at_ms,
            }
        )

    async def _enqueue(self, job):
        identifier = job.get("turn_id") or self.tracker.new_id()
        job.update(
            turn_id=identifier,
            generation=self.tracker.generation,
            accepted_at=time.monotonic(),
        )
        if not self.accepting or self.closed or self.stopping:
            await self.transport.send(
                {
                    "type": "turn_rejected",
                    "turn_id": identifier,
                    "reason": "conversation_closed",
                }
            )
            return
        if identifier in self.accepted_ids:
            await self.transport.send({"type": "turn_pending", "turn_id": identifier})
            return
        try:
            self.queue.put_nowait(job)
        except asyncio.QueueFull:
            await self.transport.send(
                {
                    "type": "turn_rejected",
                    "turn_id": identifier,
                    "reason": "queue_full",
                    "message": "The input queue is full. This message was not accepted; please retry.",
                }
            )
            return
        self.accepted_ids.add(identifier)
        await self.transport.send(
            {
                "type": "turn_accepted",
                "turn_id": identifier,
                "channel": "voice" if "audio" in job else "text",
            }
        )
        event(
            "turn_accepted",
            session_id=self.sid,
            turn_id=identifier,
            queue_depth=self.queue.qsize(),
        )

    async def _run(self):
        while True:
            job = await self.queue.get()
            self.processing = True
            try:
                if job.get("delivery"):
                    if (
                        self.enabled
                        and not self.disconnected
                        and self.tracker.current(job["generation"])
                    ):
                        self.play_task = asyncio.create_task(
                            self._speak(job["text"], job=job, speaker="human")
                        )
                        try:
                            await self.play_task
                        except asyncio.CancelledError:
                            pass
                elif self.closed:
                    await self._outcome(job, "cancelled", "conversation_closed")
                else:
                    # Never compare user-job generation here: accepted input survives barge-in.
                    await self._process(job)
            except asyncio.CancelledError:
                if not job.get("delivery"):
                    await self._outcome(job, "failed", "shutdown_deadline")
                raise
            except Exception as exc:
                event(
                    "voice_turn_failed",
                    session_id=self.sid,
                    turn_id=job.get("turn_id"),
                    category=type(exc).__name__,
                )
                if not job.get("delivery"):
                    await self._outcome(job, "failed", type(exc).__name__)
                if not self.disconnected and not self.closed:
                    await self.recover("stt" if "audio" in job else "tts")
            finally:
                self.accepted_ids.discard(job.get("turn_id"))
                self.processing = False
                self.queue.task_done()
            if self.stopping and self.queue.empty():
                return

    async def _outcome(self, job, status, reason=None):
        packet = {
            "type": "turn_result",
            "turn_id": job["turn_id"],
            "status": status,
            "reason": reason,
        }
        event(
            "turn_disposition",
            session_id=self.sid,
            turn_id=job["turn_id"],
            status=status,
            reason=reason,
        )
        if not self.disconnected:
            await self.transport.send(packet)

    async def _transcribe(self, pcm):
        faults = getattr(self.resources, "faults", None)
        fault = None
        if faults:
            for kind in ["stt_auth", "stt_transient"]:
                if await faults.consume(self.sid, kind):
                    fault = kind
                    break
        async with asyncio.timeout(self.settings.stt_timeout + 1):
            async with self.resources.capacity:
                if fault:
                    return await self.resources.stt.transcribe(pcm, fault=fault)
                return await self.resources.stt.transcribe(pcm)

    async def _process(self, job):
        utterance = job.get("audio")
        start = time.monotonic()
        origin = utterance.ended_at if utterance else job["accepted_at"]
        timings = {
            "queue_ms": round((start - job["accepted_at"]) * 1000, 2),
            "endpoint_ms": round((job["accepted_at"] - origin) * 1000, 2)
            if utterance
            else 0,
            "stt_ms": 0.0,
            "agent_ms": 0.0,
            "provider_mode": getattr(self.resources, "mode", "test_double"),
        }
        text = job.get("text")
        if utterance:
            await self.status(VoiceState.TRANSCRIBING)
            stage = time.monotonic()
            try:
                text = await self._transcribe(utterance.pcm)
            except (SpeechFailure, TimeoutError) as exc:
                event(
                    "speech_provider_failed",
                    provider="stt",
                    category=str(exc) if isinstance(exc, SpeechFailure) else "deadline",
                )
                await self._outcome(job, "failed", "transcription_unavailable")
                if not self.disconnected:
                    await self.recover("stt")
                return
            timings["stt_ms"] = round((time.monotonic() - stage) * 1000, 2)
            if not text or not text.strip() or len(text) > 2000:
                await self._outcome(job, "failed", "empty_or_invalid_transcript")
                if not self.disconnected:
                    await self.recover("stt")
                return
        await self.transport.send(
            {
                "type": "transcript",
                "text": text,
                "turn_id": job["turn_id"],
                "channel": "voice" if utterance else "text",
            }
        )
        await self.status(VoiceState.PROCESSING)
        stage = time.monotonic()
        response = await self.runtime.service.handle(
            self.identity,
            self.sid,
            Turn(
                turn_id=job["turn_id"],
                text=text,
                channel="voice" if utterance else "text",
            ),
        )
        timings["agent_ms"] = round((time.monotonic() - stage) * 1000, 2)
        timings["end_to_text_server_ms"] = round((time.monotonic() - origin) * 1000, 2)
        job.update(timings=timings, origin=origin)
        current = self.tracker.current(job["generation"])
        await self.transport.send(
            {
                "type": "response",
                **response.model_dump(mode="json"),
                "superseded": not current,
                "timings": timings,
            }
        )
        event(
            "voice_response_timing",
            session_id=self.sid,
            turn_id=job["turn_id"],
            **timings,
        )
        await self._outcome(
            job,
            "failed" if response.status in ["busy", "unavailable"] else "completed",
            response.status,
        )
        if (
            current
            and job["speak"]
            and self.enabled
            and not self.disconnected
            and not self.closed
            and response.status not in ["human_message", "terminated"]
        ):
            self.play_task = asyncio.create_task(
                self._speak(response.answer, utterance, job)
            )
            try:
                await self.play_task
            except asyncio.CancelledError:
                pass
        if response.session_state == "terminated":
            self.closed = True
            self.accepting = False
            self.enabled = False
            await self.status(VoiceState.CLOSED)
            await self.transport.send(
                {"type": "closed", "reason": "session_terminated"}
            )
        elif current and not self.closed:
            await self.status(VoiceState.LISTENING)

    async def _speak(self, text, utterance=None, job=None, speaker="assistant"):
        job = job or {}
        synthesis_started = time.monotonic()
        await self.status(VoiceState.SPEAKING)
        capture = utterance.captured_at_ms if utterance else job.get("submitted_at_ms")
        identifier = await self.playback.begin(capture)
        metadata = {
            "turn_id": job.get("turn_id"),
            "speaker": speaker,
            "timings": job.get("timings", {}),
        }
        self.playback_metadata[identifier] = metadata
        while len(self.playback_metadata) > 32:
            self.playback_metadata.pop(next(iter(self.playback_metadata)))
        await self.transport.send(
            {"type": "audio_context", "playback_id": identifier, **metadata}
        )
        first = True
        stream = None
        try:
            async with asyncio.timeout(self.settings.tts_timeout + 8):
                async with self.resources.capacity:
                    faults = getattr(self.resources, "faults", None)
                    injected = faults and await faults.consume(
                        self.sid, "tts_midstream"
                    )
                    stream = (
                        fail_midstream(self.resources.tts, text)
                        if injected
                        else self.resources.tts.stream(text)
                    )
                    async for rate, pcm in stream:
                        await self.playback.write(identifier, rate, pcm)
                        if first:
                            first = False
                            metrics = {
                                **job.get("timings", {}),
                                "tts_first_chunk_ms": round(
                                    (time.monotonic() - synthesis_started) * 1000, 2
                                ),
                            }
                            if job.get("origin") is not None:
                                metrics["end_to_audio_server_ms"] = round(
                                    (time.monotonic() - job["origin"]) * 1000, 2
                                )
                            metadata["timings"] = metrics
                            await self.transport.send(
                                {
                                    "type": "metrics",
                                    "playback_id": identifier,
                                    "turn_id": job.get("turn_id"),
                                    "speaker": speaker,
                                    **metrics,
                                }
                            )
                            event(
                                "voice_audio_timing",
                                session_id=self.sid,
                                turn_id=job.get("turn_id"),
                                playback_id=identifier,
                                speaker=speaker,
                                **metrics,
                            )
                            if "end_to_audio_server_ms" in metrics:
                                event(
                                    "voice_latency",
                                    session_id=self.sid,
                                    turn_id=job.get("turn_id"),
                                    playback_id=identifier,
                                    metric="speech_frame_arrival_to_first_audio_sent_ms"
                                    if utterance
                                    else "text_accept_to_first_audio_sent_ms",
                                    value=metrics["end_to_audio_server_ms"],
                                    mode=getattr(self.resources, "mode", "test_double"),
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
            if not self.disconnected:
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
        if self.enabled and not self.disconnected:
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

    async def _observe(self):
        previous = None
        try:
            while not self.disconnected:
                session = await self.runtime.store.get(self.sid, self.identity)
                if session.history and self.sequence < session.history[0].sequence - 1:
                    await self.transport.send(
                        {
                            "type": "history_gap",
                            "message": "Older transcript entries are outside the retained history window.",
                        }
                    )
                for message in session.history:
                    if message.sequence <= self.sequence:
                        continue
                    await self.transport.send(
                        {"type": "chat_event", **message.model_dump(mode="json")}
                    )
                    if message.role == "human" and self.enabled and not self.closed:
                        await self.queue.put(
                            {
                                "delivery": True,
                                "text": message.text,
                                "turn_id": message.message_id,
                                "generation": self.tracker.generation,
                            }
                        )
                    self.sequence = message.sequence
                if session.state != previous:
                    await self.transport.send(
                        {
                            "type": "session_state",
                            "state": session.state,
                            "support_request_id": session.support_request_id,
                        }
                    )
                    previous = session.state
                if session.state == "terminated":
                    self.closed = True
                    self.accepting = False
                    self.enabled = False
                    await self._interrupt("conversation_ended")
                    await self.transport.send(
                        {"type": "closed", "reason": "conversation_ended"}
                    )
                    return
                await asyncio.sleep(0.25)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            event(
                "conversation_watch_failed",
                session_id=self.sid,
                category=type(exc).__name__,
            )
            if not self.disconnected:
                await self.transport.send(
                    {
                        "type": "error",
                        "message": "Conversation updates paused. Reconnect to restore the transcript.",
                    }
                )

    async def end_conversation(self):
        self.accepting = False
        self.enabled = False
        self.closed = True
        await self._interrupt("customer_ended_conversation")
        await self.runtime.service.human.end_conversation(
            self.sid, self.identity, self.runtime.settings.turn_timeout + 5
        )
        await self.transport.send(
            {"type": "closed", "reason": "customer_ended_conversation"}
        )

    async def aclose(self):
        self.accepting = False
        self.stopping = True
        self.disconnected = True
        self.enabled = False
        if self.observer:
            self.observer.cancel()
            await asyncio.gather(self.observer, return_exceptions=True)
        if self.play_task and not self.play_task.done():
            self.play_task.cancel()
        if self.worker:
            if not self.processing and self.queue.empty():
                self.worker.cancel()
            budget = (
                self.runtime.settings.turn_timeout + self.settings.stt_timeout + 5
            ) * (self.queue.qsize() + 1)
            try:
                await asyncio.wait_for(asyncio.shield(self.worker), budget)
            except TimeoutError:
                self.worker.cancel()
            except asyncio.CancelledError:
                pass
            await asyncio.gather(self.worker, return_exceptions=True)
            # If shutdown exceeded its deadline, explicitly account for every accepted job.
            while not self.queue.empty():
                job = self.queue.get_nowait()
                if not job.get("delivery"):
                    await self._outcome(job, "failed", "shutdown_deadline")
                self.queue.task_done()
        if self.play_task:
            await asyncio.gather(self.play_task, return_exceptions=True)
