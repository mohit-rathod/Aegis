"""Explicit, expiring admin-only demo controls. Never enabled by default."""

from support_assistant.domain.conversation import SupportError
from support_assistant.observability.logging import event
from support_assistant.voice.events import SpeechFailure


class DemoFaults:
    KINDS = {"stt_auth", "stt_transient", "tts_midstream"}

    def __init__(self, redis, prefix, enabled):
        self.redis, self.prefix, self.enabled = redis, prefix, enabled

    def key(self, sid, kind):
        return f"{self.prefix}:demo-fault:{sid}:{kind}"

    async def arm(self, sid, kind):
        if not self.enabled:
            raise SupportError("demo_faults_disabled")
        if kind not in self.KINDS:
            raise SupportError("invalid_fault")
        await self.redis.set(self.key(sid, kind), "1", ex=300)
        event("demo_fault_armed", session_id=sid, category=kind, expires_seconds=300)

    async def consume(self, sid, kind):
        if not self.enabled:
            return False
        active = bool(await self.redis.getdel(self.key(sid, kind)))
        if active:
            event("demo_fault_injected", session_id=sid, category=kind)
        return active


async def fail_midstream(provider, text):
    """Let real audio play before failing; cancellation still closes the real worker."""
    stream = provider.stream(text)
    seconds = 0
    try:
        async for rate, pcm in stream:
            yield rate, pcm
            seconds += len(pcm) / 2 / rate
            if seconds >= 0.6:
                raise SpeechFailure("demo_tts_midstream_failure")
        raise SpeechFailure("demo_tts_failure_after_short_output")
    finally:
        await stream.aclose()
