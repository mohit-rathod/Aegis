from collections.abc import AsyncIterator
from typing import Protocol


class TextToSpeech(Protocol):
    def stream(self, text: str) -> AsyncIterator[tuple[int, bytes]]: ...
