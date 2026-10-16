"""512-sample/32ms PCM frames; bounded memory and configurable hysteresis."""

import math

from support_assistant.voice.audio_buffer import AudioBuffer
from support_assistant.voice.events import Utterance


class Endpointer:
    def __init__(self, settings):
        self.settings = settings
        self.buffer = AudioBuffer(max(10, math.ceil(settings.onset_ms / 32) + 2))
        self.reset()

    def reset(self):
        self.active = False
        self.onset = 0
        self.silence = 0
        self.frames = []
        self.last_at = 0.0
        self.last_client = 0.0
        self.buffer.clear()

    def feed(self, pcm, probability, now, captured_at_ms):
        if len(pcm) != 1024:
            raise ValueError("Expected 512 int16 samples")
        events = []
        self.buffer.append(pcm)
        if not self.active:
            self.onset = (
                self.onset + 1 if probability >= self.settings.start_threshold else 0
            )
            if self.onset < math.ceil(self.settings.onset_ms / 32):
                return events
            self.active = True
            self.frames = self.buffer.snapshot()
            events.append(("speech_start", None))
        else:
            self.frames.append(pcm)
        if probability >= self.settings.stop_threshold:
            self.silence = 0
            self.last_at = now
            self.last_client = captured_at_ms
        else:
            self.silence += 1
        if len(self.frames) * 32 >= self.settings.max_utterance_seconds * 1000:
            self.reset()
            events.append(("too_long", None))
        elif self.silence >= math.ceil(self.settings.silence_ms / 32):
            events.append(
                (
                    "utterance",
                    Utterance(b"".join(self.frames), self.last_at, self.last_client),
                )
            )
            self.reset()
        return events
