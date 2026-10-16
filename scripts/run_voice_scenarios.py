"""Paced fixture replay through the real coordinator/VAD/Piper (no microphone needed).

--scripted substitutes STT and the LLM; --live uses Groq and the actual RAG runtime.
The playback sink is virtual and paced. Use the browser for a physical-audio demo.
"""

import argparse
import asyncio
import json
import logging
import sys
import time
import uuid
from dataclasses import replace
from pathlib import Path

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from support_assistant.adapters.audio.codecs import wav_to_pcm
from support_assistant.config import Settings
from support_assistant.observability.logging import configure_logging, event, logger
from support_assistant.voice.coordinator import VoiceCoordinator
from support_assistant.voice.events import SpeechFailure
from support_assistant.voice.resources import VoiceResources


class ScriptedSTT:
    def __init__(self):
        self.calls = 0

    async def transcribe(self, pcm):
        self.calls += 1
        return "Wait, wrong order."

    async def aclose(self):
        pass


class FailAfterFirstChunk:
    def __init__(self, tts):
        self.tts = tts

    async def stream(self, text):
        stream = self.tts.stream(text)
        try:
            yield await anext(stream)
            raise SpeechFailure("injected_tts_midstream_failure")
        finally:
            await stream.aclose()


class ReplayTransport:
    def __init__(self):
        self.rows = []
        self.coordinator = None
        self.tasks = []
        self.next_at = 0
        self.first_audio = asyncio.Event()

    async def send(self, packet):
        self.rows.append({k: v for k, v in packet.items() if k != "pcm"})
        if packet["type"] in ("transcript", "response", "recovery", "audio_stop"):
            event(
                "demo_packet",
                mode="fixture_replay",
                packet={k: v for k, v in packet.items() if k != "pcm"},
            )
        if packet["type"] == "audio_start":
            self.next_at = time.monotonic()
        if packet["type"] == "audio_stop":
            for task in self.tasks:
                task.cancel()
            self.tasks = []
            self.coordinator.playback.acknowledge_stop(packet["playback_id"])
            event(
                "playback_cancel_ack",
                mode="virtual_sink",
                playback_id=packet["playback_id"],
            )
        if packet["type"] == "audio":
            import base64

            self.first_audio.set()
            duration = len(base64.b64decode(packet["pcm"])) / 2 / packet["sample_rate"]
            self.next_at = max(time.monotonic(), self.next_at) + duration

            async def acknowledge(deadline):
                await asyncio.sleep(max(0, deadline - time.monotonic()))
                await self.coordinator.playback.acknowledge(
                    packet["playback_id"], packet["sequence"]
                )

            self.tasks.append(asyncio.create_task(acknowledge(self.next_at)))

    async def close(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)


async def feed(coordinator, pcm):
    # Intentionally paced at the real 16kHz rate; endpoint delay is included.
    for offset in range(0, len(pcm), 1024):
        frame = pcm[offset : offset + 1024].ljust(1024, b"\0")
        await coordinator.frame(frame, time.monotonic() * 1000)
        await asyncio.sleep(0.032)


async def run(args):
    settings = Settings.from_env()
    voice = replace(
        settings.voice,
        vad_model=args.vad_model or settings.voice.vad_model,
        tts_model=args.tts_model or settings.voice.tts_model,
    )
    settings = replace(settings, voice=voice)
    args.output.mkdir(parents=True, exist_ok=True)
    configure_logging()
    handler = logging.FileHandler(args.output / "traces.jsonl", mode="w")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    owned = None
    if args.scripted:
        from redis.asyncio import Redis

        from tests.fakes.support import make_service

        redis = Redis.from_url(
            args.redis_url or settings.redis_url, decode_responses=True
        )
        prefix = "aegis-voice-demo-" + uuid.uuid4().hex
        runtime = make_service(redis, prefix, ROOT)
        runtime.settings = settings
        resources = VoiceResources(settings)
        await resources.stt.aclose()
        resources.stt = ScriptedSTT()
    else:
        from support_assistant.bootstrap import create_runtime

        owned = await create_runtime(settings)
        runtime = owned
        redis = runtime.redis
        prefix = None
        resources = runtime.voice
    original_stt, original_tts = resources.stt, resources.tts
    speech = wav_to_pcm(ROOT / "tests/fixtures/audio/interruption.wav")
    silence = b"\0" * (16000 * 2)
    rng = np.random.default_rng(7)
    noise = np.zeros(16000, dtype="<i2")
    noise[100:740] = rng.integers(-10000, 10000, 640, dtype=np.int16)
    results = []
    try:
        for name in [
            "silence",
            "noise",
            "interruption",
            "false_start_then_interruption",
            "stt_failure",
            "tts_failure",
        ]:
            session = await runtime.store.create("customer-a")
            transport = ReplayTransport()
            coordinator = VoiceCoordinator(
                runtime, "customer-a", session.session_id, transport, resources
            )
            transport.coordinator = coordinator
            coordinator.detector = await resources.detector()
            coordinator.enabled = True
            resources.stt, resources.tts = original_stt, original_tts
            fault_client = None
            if name == "stt_failure":
                from support_assistant.adapters.groq.speech_to_text import (
                    GroqSpeechToText,
                )

                fault_client = httpx.AsyncClient(
                    transport=httpx.MockTransport(lambda request: httpx.Response(401))
                )
                resources.stt = GroqSpeechToText(
                    "invalid-demo-key", settings.groq_stt_model, client=fault_client
                )
            if name == "tts_failure":
                resources.tts = FailAfterFirstChunk(original_tts)
            await coordinator.start()
            event(
                "demo_scenario_started",
                scenario=name,
                mode="scripted_stt_llm_real_vad_piper"
                if args.scripted
                else "live_groq_real_vad_piper",
            )
            try:
                if name == "stt_failure":
                    await feed(coordinator, speech + silence)
                else:
                    await coordinator.text("Where is AEG-1001?")
                    await asyncio.wait_for(transport.first_audio.wait(), 60)
                    if name == "silence":
                        await feed(coordinator, silence)
                    elif name == "noise":
                        await feed(coordinator, noise.tobytes())
                    elif name == "interruption":
                        await feed(coordinator, speech + silence)
                    elif name == "false_start_then_interruption":
                        await feed(
                            coordinator,
                            speech[8192:10240] + silence[:16000] + speech + silence,
                        )
                await asyncio.wait_for(coordinator.queue.join(), 90)
                stops = [
                    r
                    for r in transport.rows
                    if r["type"] == "audio_stop" and r["reason"] == "confirmed_speech"
                ]
                transcripts = [
                    r
                    for r in transport.rows
                    if r["type"] == "transcript" and r["channel"] == "voice"
                ]
                recovery = [r for r in transport.rows if r["type"] == "recovery"]
                if name in ("silence", "noise"):
                    passed = not stops and not transcripts
                elif name in ("interruption", "false_start_then_interruption"):
                    passed = bool(stops) and len(transcripts) == 1
                elif name == "stt_failure":
                    passed = (
                        any(r["category"] == "stt" for r in recovery)
                        and not transcripts
                    )
                else:
                    passed = any(r["category"] == "tts" for r in recovery)
                result = {
                    "scenario": name,
                    "passed": passed,
                    "speech_interruptions": len(stops),
                    "voice_turns": len(transcripts),
                    "recoveries": [r["category"] for r in recovery],
                    "events": transport.rows,
                }
                results.append(result)
                event("demo_scenario_finished", scenario=name, passed=passed)
            finally:
                await coordinator.aclose()
                await transport.close()
                if fault_client:
                    await fault_client.aclose()
        report = {
            "mode": "scripted_stt_llm_real_vad_piper"
            if args.scripted
            else "live_groq_real_vad_piper",
            "audio_sink": "paced_virtual_playback",
            "physical_microphone_tested": False,
            "scenarios": results,
        }
        (args.output / "scenarios.json").write_text(json.dumps(report, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "passed": sum(r["passed"] for r in results),
                    "total": len(results),
                    "output": str(args.output),
                }
            )
        )
        if not all(r["passed"] for r in results):
            raise SystemExit(1)
    finally:
        resources.stt, resources.tts = original_stt, original_tts
        if owned:
            await owned.aclose()
        else:
            await resources.aclose()
            keys = [key async for key in redis.scan_iter(match=prefix + ":*")]
            if keys:
                await redis.delete(*keys)
            await redis.aclose()
        logger.removeHandler(handler)
        handler.close()


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--scripted", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--redis-url")
    parser.add_argument("--vad-model", type=Path)
    parser.add_argument("--tts-model", type=Path)
    parser.add_argument("--output", type=Path, default=Path("var/evaluation/voice"))
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
