from dataclasses import dataclass
from pathlib import Path
import os

@dataclass(frozen=True)
class Settings:
    kb_dir: Path = Path("data/knowledge_base")
    index_dir: Path = Path("var/indexes/aegis")
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_revision: str = "main"
    chunk_tokens: int = 160
    chunk_overlap: int = 24
    top_k_documents: int = 3
    min_similarity: float = 0.25
    groq_key: str = ""
    groq_model: str = ""
    provider_timeout: float = 20.0

    def __post_init__(self):
        if not 1 <= self.top_k_documents <= 15:
            raise ValueError("top_k_documents must be between 1 and 15")
        if not 0 <= self.min_similarity <= 1:
            raise ValueError("min_similarity must be between 0 and 1")
        if not 16 <= self.chunk_tokens <= 512:
            raise ValueError("chunk_tokens must be between 16 and 512")
        if not 0 <= self.chunk_overlap < self.chunk_tokens:
            raise ValueError("overlap must be smaller than chunk size")
        if self.provider_timeout <= 0:
            raise ValueError("provider timeout must be positive")

    @classmethod
    def from_env(cls):
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
        except ImportError:
            pass
        return cls(
            kb_dir=Path(os.getenv("AEGIS_KB_DIR", "data/knowledge_base")),
            index_dir=Path(os.getenv("AEGIS_INDEX_DIR", "var/indexes/aegis")),
            embedding_model=os.getenv("AEGIS_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
            embedding_revision=os.getenv("AEGIS_EMBEDDING_REVISION", "main"),
            chunk_tokens=int(os.getenv("AEGIS_CHUNK_TOKENS", "160")),
            chunk_overlap=int(os.getenv("AEGIS_CHUNK_OVERLAP", "24")),
            top_k_documents=int(os.getenv("AEGIS_TOP_K_DOCUMENTS", "3")),
            min_similarity=float(os.getenv("AEGIS_MIN_SIMILARITY", "0.25")),
            groq_key=os.getenv("GROQ_API_KEY", ""),
            groq_model=os.getenv("GROQ_MODEL", ""),
            provider_timeout=float(os.getenv("AEGIS_PROVIDER_TIMEOUT", "20")),
        )
