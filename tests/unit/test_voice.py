import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from support_assistant.voice.coordinator import VoiceCoordinator
from support_assistant.voice.endpointing import Endpointer
from support_assistant.voice.events import SpeechFailure
from support_assistant.voice.settings import VoiceSettings
from tests.fakes.audio import Detector, components


class EndpointTests(unittest.TestCase):
    def test_silence_and_noise_do_not_start_speech(self):
        endpoint = Endpointer(VoiceSettings())
        self.assertEqual(
            [
                event
                for p in [0.01] * 50 + [0.99] * 2 + [0.01] * 30
                for event in endpoint.feed(b"\0" * 1024, p, 1, 1)
            ],
            [],
        )

    def test_one_utterance_with_preroll(self):
        endpoint = Endpointer(VoiceSettings())
        events = []
        for i, p in enumerate([0.01] * 10 + [0.99] * 12 + [0.01] * 30):
            events += endpoint.feed(b"\0" * 1024, p, i * 0.032, i * 32)
        self.assertEqual([e[0] for e in events], ["speech_start", "utterance"])
        self.assertEqual(events[1][1].captured_at_ms, 21 * 32)

    def test_maximum_utterance_is_bounded(self):
        endpoint = Endpointer(VoiceSettings(max_utterance_seconds=1))
        events = []
        for i in range(40):
            events += endpoint.feed(b"\0" * 1024, 0.99, i * 0.032, i * 32)
        self.assertIn("too_long", [e[0] for e in events])
        self.assertLess(len(endpoint.frames), 32)

    def test_invalid_frame_rejected(self):
        with self.assertRaises(ValueError):
            Endpointer(VoiceSettings()).feed(b"bad", 0.9, 0, 0)

    def test_invalid_thresholds_rejected(self):
        with self.assertRaises(ValueError):
            VoiceSettings(start_threshold=0.2, stop_threshold=0.6)


class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.runtime, self.resources, self.transport = components()
        self.coordinator = VoiceCoordinator(
            self.runtime, "customer-a", "s" * 32, self.transport, self.resources
        )
        self.transport.coordinator = self.coordinator
        self.coordinator.detector = Detector()
        self.coordinator.enabled = True
        await self.coordinator.start()

    async def asyncTearDown(self):
        await self.coordinator.aclose()

    async def wait(self, predicate):
        async with asyncio.timeout(2):
            while not predicate():
                await asyncio.sleep(0.002)

    async def frames(self, probabilities):
        for p in probabilities:
            await self.coordinator.frame(
                (b"\1" if p else b"\0") + b"\0" * 1023, time.monotonic() * 1000
            )

    async def test_silence_does_not_transcribe(self):
        await self.frames([0] * 40)
        self.assertEqual(self.resources.stt.calls, 0)

    async def test_noise_does_not_cancel_playback(self):
        self.resources.tts.hold = asyncio.Event()
        await self.coordinator.text("Order details")
        await self.wait(lambda: self.coordinator.playback.active)
        before = self.coordinator.playback.active
        await self.frames([1] * 2 + [0] * 30)
        self.assertEqual(self.coordinator.playback.active, before)
        self.assertEqual(self.resources.stt.calls, 0)
        self.resources.tts.hold.set()
        await self.coordinator.queue.join()

    async def test_real_interruption_dispatches_once(self):
        self.resources.tts.hold = asyncio.Event()
        await self.coordinator.text("Order details")
        await self.wait(lambda: self.coordinator.playback.active)
        await self.frames([1] * 10 + [0] * 24)
        self.resources.tts.hold.set()
        await self.coordinator.queue.join()
        self.assertEqual(self.resources.stt.calls, 1)
        self.assertEqual(len(self.runtime.service.turns), 2)
        self.assertEqual(self.runtime.service.turns[-1].channel, "voice")
        self.assertTrue(
            any(
                r["type"] == "audio_stop" and r["reason"] == "confirmed_speech"
                for r in self.transport.rows
            )
        )

    async def test_false_start_then_real_speech(self):
        await self.frames([1] * 2 + [0] * 8 + [1] * 9 + [0] * 24)
        await self.coordinator.queue.join()
        self.assertEqual(self.resources.stt.calls, 1)
        self.assertEqual(len(self.runtime.service.turns), 1)

    async def test_empty_transcript_never_dispatches(self):
        self.resources.stt.text = ""
        await self.frames([1] * 8 + [0] * 24)
        await self.coordinator.queue.join()
        self.assertEqual(self.runtime.service.turns, [])
        self.assertTrue(any(r["type"] == "recovery" for r in self.transport.rows))

    async def test_stt_failure_never_dispatches_and_recovers(self):
        self.resources.stt.error = SpeechFailure("stt_authentication_failed")
        await self.frames([1] * 8 + [0] * 24)
        await self.coordinator.queue.join()
        self.assertEqual(self.runtime.service.turns, [])
        self.assertTrue(any(r["type"] == "audio" for r in self.transport.rows))

    async def test_tts_midstream_failure_uses_recording(self):
        self.resources.tts.error = SpeechFailure("tts_failed")
        await self.coordinator.text("Order details")
        await self.coordinator.queue.join()
        self.assertTrue(
            any(
                r["type"] == "audio_stop" and r["reason"] == "tts_failure"
                for r in self.transport.rows
            )
        )
        self.assertTrue(
            any(
                r["type"] == "audio_start" and r["recovery"]
                for r in self.transport.rows
            )
        )

    async def test_text_and_voice_share_identity_and_service(self):
        await self.coordinator.text("Order details")
        await self.coordinator.queue.join()
        await self.frames([1] * 8 + [0] * 24)
        await self.coordinator.queue.join()
        self.assertEqual(
            [t.channel for t in self.runtime.service.turns], ["text", "voice"]
        )

    async def test_no_business_cancellation_on_interruption(self):
        self.runtime.service.hold = asyncio.Event()
        await self.coordinator.text("Order details")
        await self.runtime.service.started.wait()
        await self.frames([1] * 8 + [0] * 24)
        self.runtime.service.hold.set()
        await self.coordinator.queue.join()
        self.assertEqual(len(self.runtime.service.turns), 2)
        responses = [r for r in self.transport.rows if r["type"] == "response"]
        self.assertTrue(responses[0]["superseded"])
        self.assertFalse(responses[1]["superseded"])

    async def test_terminated_session_cannot_dispatch_another_turn(self):
        self.runtime.service.terminated = True
        await self.coordinator.text("Human please")
        await self.coordinator.queue.join()
        await self.coordinator.text("Another question")
        self.assertTrue(self.coordinator.closed)
        self.assertEqual(len(self.runtime.service.turns), 1)

    async def test_queue_bounded(self):
        for _ in range(10):
            await self.coordinator.text("question")
        self.assertLessEqual(self.coordinator.queue.qsize(), 2)
        self.assertTrue(any(r["type"] == "turn_rejected" for r in self.transport.rows))

    async def test_disconnect_finishes_business_without_starting_audio(self):
        self.runtime.service.hold = asyncio.Event()
        await self.coordinator.text("Order details")
        await self.runtime.service.started.wait()
        closing = asyncio.create_task(self.coordinator.aclose())
        await asyncio.sleep(0.01)
        self.runtime.service.hold.set()
        await closing
        self.assertEqual(len(self.runtime.service.turns), 1)
        self.assertEqual(self.resources.tts.calls, 0)

    async def test_all_accepted_turns_survive_newer_input_fifo(self):
        self.runtime.service.hold = asyncio.Event()
        await self.coordinator.text("first", "first")
        await self.runtime.service.started.wait()
        await self.coordinator.text("second", "second")
        await self.coordinator.text("third", "third")
        self.runtime.service.hold.set()
        await self.coordinator.queue.join()
        self.assertEqual(
            [t.text for t in self.runtime.service.turns], ["first", "second", "third"]
        )
        outcomes = [r for r in self.transport.rows if r["type"] == "turn_result"]
        self.assertEqual(len(outcomes), 3)
        self.assertTrue(all(r["status"] == "completed" for r in outcomes))

    async def test_disconnect_drains_accepted_pending_turns(self):
        self.runtime.service.hold = asyncio.Event()
        await self.coordinator.text("first", "first")
        await self.runtime.service.started.wait()
        await self.coordinator.text("second", "second")
        closing = asyncio.create_task(self.coordinator.aclose())
        await asyncio.sleep(0.01)
        self.runtime.service.hold.set()
        await closing
        self.assertEqual(
            [t.text for t in self.runtime.service.turns], ["first", "second"]
        )

    async def test_same_pending_turn_does_not_dispatch_twice(self):
        self.runtime.service.hold = asyncio.Event()
        await self.coordinator.text("first", "same")
        await self.runtime.service.started.wait()
        await self.coordinator.text("first", "same")
        self.runtime.service.hold.set()
        await self.coordinator.queue.join()
        self.assertEqual(len(self.runtime.service.turns), 1)
        self.assertTrue(any(r["type"] == "turn_pending" for r in self.transport.rows))

    async def test_latency_contains_real_stage_boundaries(self):
        await self.coordinator.text("Order details", "timed")
        await self.coordinator.queue.join()
        metric = next(r for r in self.transport.rows if r["type"] == "metrics")
        self.assertEqual(metric["turn_id"], "timed")
        for field in [
            "queue_ms",
            "endpoint_ms",
            "stt_ms",
            "agent_ms",
            "tts_first_chunk_ms",
            "end_to_audio_server_ms",
        ]:
            self.assertGreaterEqual(metric[field], 0)
        self.assertGreaterEqual(metric["end_to_audio_server_ms"], metric["agent_ms"])

    async def test_stale_ack_cannot_ack_current_playback(self):
        playback = self.coordinator.playback
        self.transport.auto_ack = False
        old = await playback.begin()
        await playback.write(old, 16000, b"\0" * 2048)
        new = await playback.begin()
        await playback.write(new, 16000, b"\0" * 2048)
        await playback.acknowledge(old, 0)
        self.assertEqual(playback.pending, {0})
        await playback.stop()


class SpokenOrderTests(unittest.IsolatedAsyncioTestCase):
    async def test_wrong_order_does_not_reuse_previous_reference(self):
        from support_assistant.agents.order_status import OrderStatusAgent

        llm = AsyncMock()
        executor = AsyncMock()
        authority = Mock()
        approved = SimpleNamespace(
            turn=SimpleNamespace(text="Wait, wrong order."),
            session=SimpleNamespace(last_order_id="AEG-1001"),
        )
        result = await OrderStatusAgent(llm, executor, authority).run(approved)
        self.assertEqual(result.kind, "order_reference")
        llm.chat.assert_not_called()
        executor.execute.assert_not_called()

    async def test_explicit_spaced_prefix_is_normalized(self):
        from support_assistant.agents.order_status import OrderStatusAgent
        from tests.fakes.support import FakeLLM

        calls = []

        class Executor:
            async def execute(self, approved, name, arguments, call_id, ledger):
                import json

                calls.append(json.loads(arguments)["order_id"])
                ledger[call_id] = {"verified": "test-only"}
                return {"status": "test-only"}

        approved = SimpleNamespace(
            turn=SimpleNamespace(text="Where is A E G 1003?"),
            session=SimpleNamespace(last_order_id=None),
        )
        result = await OrderStatusAgent(FakeLLM(), Executor(), Mock()).run(approved)
        self.assertEqual(calls, ["AEG-1003"])
        self.assertEqual(result.verified_order_id, "AEG-1003")


if __name__ == "__main__":
    unittest.main()
