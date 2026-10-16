from dataclasses import asdict
from pathlib import Path
import json
import os
import uuid
import numpy as np
from support_assistant.domain.evidence import Chunk

class NumpyIndex:
    def __init__(self, vectors, chunks, metadata):
        self.vectors = np.asarray(vectors, dtype=np.float32)
        self.chunks = chunks
        self.metadata = metadata
        if self.vectors.ndim != 2 or self.vectors.shape[0] != len(chunks) or not chunks:
            raise ValueError("Invalid index shape")
        if not np.isfinite(self.vectors).all():
            raise ValueError("Non-finite index vectors")
        if not np.allclose(np.linalg.norm(self.vectors, axis=1), 1, atol=1e-4):
            raise ValueError("Index vectors must be normalized")
        if len({c.chunk_id for c in chunks}) != len(chunks):
            raise ValueError("Duplicate chunk IDs")

    def save(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        temp = directory / f".index-{uuid.uuid4().hex}.npz"
        try:
            np.savez_compressed(temp, vectors=self.vectors,
                chunks=np.array(json.dumps([asdict(c) for c in self.chunks])),
                metadata=np.array(json.dumps(self.metadata)))
            os.replace(temp, directory / "index.npz")
        finally:
            temp.unlink(missing_ok=True)

    @classmethod
    def load(cls, directory: Path):
        with np.load(directory / "index.npz", allow_pickle=False) as data:
            return cls(data["vectors"].copy(),
                [Chunk(**c) for c in json.loads(data["chunks"].item())],
                json.loads(data["metadata"].item()))

    def ranked_chunks(self, query_vector):
        q = np.asarray(query_vector, dtype=np.float32)
        if q.shape != (self.vectors.shape[1],) or not np.isfinite(q).all():
            raise ValueError("Query embedding dimension/values do not match index")
        norm = np.linalg.norm(q)
        if norm < 1e-8:
            raise ValueError("Empty query vector")
        scores = self.vectors @ (q / norm)
        return [(self.chunks[int(i)], float(scores[i]))
            for i in np.argsort(-scores, kind="stable")]
