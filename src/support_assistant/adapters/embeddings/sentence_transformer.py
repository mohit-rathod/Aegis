import os

import numpy as np


class SentenceTransformerEmbedder:
    def __init__(self, model_id: str, revision: str = "main"):
        from sentence_transformers import SentenceTransformer

        self.model_id = model_id
        self.revision = revision
        self.model = SentenceTransformer(
            model_id,
            revision=revision,
            device="cpu",
            token=os.getenv("HF_TOKEN", "").strip() or None,
        )
        if not self.model.tokenizer.is_fast:
            raise ValueError(
                "A fast tokenizer is required for offset-preserving chunks"
            )
        self.max_tokens = int(self.model.max_seq_length)  # type:ignore

    def spans(self, text: str, size: int, overlap: int) -> list[str]:
        offsets = self.model.tokenizer(
            text,
            add_special_tokens=False,
            return_offsets_mapping=True,
            truncation=False,
        )["offset_mapping"]
        if not offsets:
            return []
        result = []
        for start in range(0, len(offsets), size - overlap):
            end = min(start + size, len(offsets))
            result.append(text[offsets[start][0] : offsets[end - 1][1]])
            if end == len(offsets):
                break
        return result

    def encode(self, texts: list[str]) -> np.ndarray:
        for text in texts:
            count = len(
                self.model.tokenizer(text, add_special_tokens=True, truncation=False)[
                    "input_ids"
                ]
            )
            if count > self.max_tokens:
                raise ValueError(
                    "Embedding input exceeds model limit; shorten question/chunks"
                )
        vectors = self.model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)
