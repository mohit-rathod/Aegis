from dataclasses import dataclass


@dataclass(frozen=True)
class Utterance:
    pcm: bytes
    ended_at: float  # Server monotonic: arrival of last speech frame.
    captured_at_ms: float  # Browser monotonic: capture callback for last speech frame.


class SpeechFailure(RuntimeError):
    """Operational category only; never include provider credentials/body."""


class PlaybackCancelled(Exception):
    pass
