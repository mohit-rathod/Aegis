from typing import Protocol
import numpy as np

class Embedder(Protocol):
    model_id: str
    revision: str
    max_tokens: int
    def spans(self, text: str, size: int, overlap: int) -> list[str]: ...
    def encode(self, texts: list[str]) -> np.ndarray: ...
