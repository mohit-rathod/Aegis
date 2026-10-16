"""Voice channel configuration, nested in the application's shared Settings."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VoiceSettings:
    vad_model: Path = Path("var/models/silero_vad.onnx")
    tts_model: Path = Path("var/models/en_US-lessac-medium.onnx")
    language: str = "en"
    start_threshold: float = 0.65
    stop_threshold: float = 0.35
    onset_ms: int = 160
    silence_ms: int = 768
    max_utterance_seconds: int = 30
    stt_timeout: float = 12
    tts_timeout: float = 30
    max_connections: int = 32
    provider_concurrency: int = 4

    def __post_init__(self):
        if not 0 < self.stop_threshold < self.start_threshold < 1:
            raise ValueError("Invalid voice VAD thresholds")
        if not 64 <= self.onset_ms <= 1000 or not 128 <= self.silence_ms <= 3000:
            raise ValueError("Invalid voice endpoint timing")
        if not 1 <= self.max_utterance_seconds <= 60:
            raise ValueError("Voice utterance limit must be 1..60 seconds")
        if (
            min(
                self.stt_timeout,
                self.tts_timeout,
                self.max_connections,
                self.provider_concurrency,
            )
            <= 0
        ):
            raise ValueError("Voice timeouts and capacities must be positive")

    @classmethod
    def from_env(cls):
        return cls(
            vad_model=Path(os.getenv("AEGIS_VAD_MODEL", "var/models/silero_vad.onnx")),
            tts_model=Path(
                os.getenv("AEGIS_TTS_MODEL", "var/models/en_US-lessac-medium.onnx")
            ),
            language=os.getenv("AEGIS_STT_LANGUAGE", "en"),
            onset_ms=int(os.getenv("AEGIS_VOICE_ONSET_MS", "160")),
            silence_ms=int(os.getenv("AEGIS_VOICE_SILENCE_MS", "768")),
            stt_timeout=float(os.getenv("AEGIS_STT_TIMEOUT", "12")),
            tts_timeout=float(os.getenv("AEGIS_TTS_TIMEOUT", "30")),
            max_connections=int(os.getenv("AEGIS_VOICE_MAX_CONNECTIONS", "32")),
            provider_concurrency=int(os.getenv("AEGIS_SPEECH_CONCURRENCY", "4")),
        )
