import asyncio
import os
import unittest
from pathlib import Path

import httpx

from support_assistant.adapters.groq.speech_to_text import GroqSpeechToText
from support_assistant.adapters.tts.piper import PiperTTS
from support_assistant.voice.events import SpeechFailure


class STTTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, handler):
        self.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(self.client.aclose)
        return GroqSpeechToText(
            "dummy", "whisper-large-v3-turbo", client=self.client, timeout=0.8
        )

    async def test_multipart_contract(self):
        async def handler(request):
            self.assertEqual(request.url.path, "/openai/v1/audio/transcriptions")
            self.assertIn(b"whisper-large-v3-turbo", request.content)
            self.assertIn(b"RIFF", request.content)
            return httpx.Response(200, json={"text": "Where is my order?"})

        self.assertEqual(
            await (await self.request(handler)).transcribe(b"\0" * 1024),
            "Where is my order?",
        )

    async def test_auth_failure_is_not_retried(self):
        calls = []

        async def handler(request):
            calls.append(1)
            return httpx.Response(401)

        with self.assertRaisesRegex(SpeechFailure, "authentication"):
            await (await self.request(handler)).transcribe(b"\0" * 1024)
        self.assertEqual(len(calls), 1)

    async def test_transient_failure_retries_same_audio(self):
        calls = []

        async def handler(request):
            calls.append(request.content)
            return (
                httpx.Response(503)
                if len(calls) == 1
                else httpx.Response(200, json={"text": "hello"})
            )

        result = await (await self.request(handler)).transcribe(b"\1" * 1024)
        self.assertEqual(result, "hello")
        self.assertEqual(len(calls), 2)
        # Multipart boundaries may vary; both requests contain the same WAV payload.
        self.assertTrue(all(b"\1" * 1024 in body for body in calls))

    async def test_stalled_provider_has_total_deadline(self):
        async def handler(request):
            await asyncio.sleep(2)
            return httpx.Response(200, json={"text": "late"})

        adapter = await self.request(handler)
        adapter.timeout = 0.02
        with self.assertRaisesRegex(SpeechFailure, "deadline"):
            await adapter.transcribe(b"\0" * 1024)

    async def test_long_rate_limit_does_not_sleep_indefinitely(self):
        async def handler(request):
            return httpx.Response(429, headers={"retry-after": "300"})

        with self.assertRaises(SpeechFailure):
            await (await self.request(handler)).transcribe(b"\0" * 1024)


class TTSRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_retry_only_before_first_audio(self):
        class Provider(PiperTTS):
            def __init__(self):
                self.calls = 0

            async def _once(self, text):
                self.calls += 1
                if self.calls == 1:
                    raise SpeechFailure("tts_worker_failed")
                yield 16000, b"\0" * 100

        provider = Provider()
        output = [chunk async for chunk in provider.stream("hello")]
        self.assertEqual(provider.calls, 2)
        self.assertEqual(len(output), 1)

    async def test_midstream_failure_does_not_replay_audio(self):
        class Provider(PiperTTS):
            def __init__(self):
                self.calls = 0

            async def _once(self, text):
                self.calls += 1
                yield 16000, b"\0" * 100
                raise SpeechFailure("tts_worker_failed")

        provider = Provider()
        with self.assertRaises(SpeechFailure):
            async for _ in provider.stream("hello"):
                pass
        self.assertEqual(provider.calls, 1)


@unittest.skipUnless(
    os.getenv("AEGIS_TEST_PIPER_MODEL"),
    "Set AEGIS_TEST_PIPER_MODEL for native synthesis",
)
class NativeSpeechTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_piper_produces_pcm(self):
        output = [
            (rate, pcm)
            async for rate, pcm in PiperTTS(
                Path(os.environ["AEGIS_TEST_PIPER_MODEL"])
            ).stream("Welcome to Aegis support.")
        ]
        self.assertTrue(output)
        self.assertGreater(sum(len(p) for _, p in output), 1000)

    async def test_cancel_reaps_native_worker(self):
        stream = PiperTTS(Path(os.environ["AEGIS_TEST_PIPER_MODEL"])).stream(
            "Please listen to these order details. " * 20
        )
        await anext(stream)
        await asyncio.wait_for(stream.aclose(), 2)
