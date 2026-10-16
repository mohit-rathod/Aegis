from enum import StrEnum


class VoiceState(StrEnum):
    LISTENING = "listening"
    CAPTURING = "capturing"
    TRANSCRIBING = "transcribing"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    RECOVERING = "recovering"
    CLOSED = "closed"
