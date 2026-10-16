from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
import os

@dataclass(frozen=True)
class Settings:
    """Environment-backed configuration shared by every application channel."""
    kb_dir: Path = Path("data/knowledge_base")
    index_dir: Path = Path("var/indexes/aegis")
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_revision: str = "main"
    chunk_tokens: int = 160
    chunk_overlap: int = 24
    top_k_documents: int = 3
    min_similarity: float = 0.25
    groq_key: str = field(default="", repr=False)
    groq_model: str = ""
    groq_stt_model: str = "whisper-large-v3-turbo"
    provider_timeout: float = 20.0
    redis_url: str = field(default="redis://127.0.0.1:6379/0", repr=False)
    prefix: str = "aegis"
    session_ttl: int = 86400
    classifier_ttl: int = 300
    classifier_max_entries: int = 1000
    turn_timeout: float = 60
    max_active: int = 32
    provider_concurrency: int = 16
    embedding_workers: int = 2
    max_embedding_pending: int = 4
    demo_a_token: str = field(default="", repr=False)
    demo_b_token: str = field(default="", repr=False)
    admin_token: str = field(default="", repr=False)
    fixture_path: Path = Path("data/fixtures/orders.json")
    demo_as_of: str = ""

    def __post_init__(self):
        if not 1 <= self.top_k_documents <= 15:
            raise ValueError("top_k_documents must be between 1 and 15")
        if not 0 <= self.min_similarity <= 1:
            raise ValueError("min_similarity must be between 0 and 1")
        if not 16 <= self.chunk_tokens <= 512:
            raise ValueError("chunk_tokens must be between 16 and 512")
        if not 0 <= self.chunk_overlap < self.chunk_tokens:
            raise ValueError("overlap must be smaller than chunk size")
        for key in ["provider_timeout", "session_ttl", "classifier_ttl", "classifier_max_entries",
                    "turn_timeout", "max_active", "provider_concurrency", "embedding_workers", "max_embedding_pending"]:
            if getattr(self, key) <= 0:
                raise ValueError(f"{key} must be positive")
        if not self.prefix or any(c in self.prefix for c in '{}*? '):
            raise ValueError("Invalid Redis prefix")
        if self.demo_a_token and self.demo_a_token == self.demo_b_token:
            raise ValueError("Demo customer tokens must differ")
        if self.demo_as_of:
            date.fromisoformat(self.demo_as_of)

    @classmethod
    def from_env(cls):
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
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
            groq_stt_model=os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo"),
            provider_timeout=float(os.getenv("AEGIS_PROVIDER_TIMEOUT", "20")),
            redis_url=os.getenv("AEGIS_REDIS_URL", "redis://127.0.0.1:6379/0"),
            prefix=os.getenv("AEGIS_REDIS_PREFIX", "aegis"),
            session_ttl=int(os.getenv("AEGIS_SESSION_TTL", "86400")),
            classifier_ttl=int(os.getenv("AEGIS_CLASSIFIER_TTL", "300")),
            classifier_max_entries=int(os.getenv("AEGIS_CLASSIFIER_MAX_ENTRIES", "1000")),
            turn_timeout=float(os.getenv("AEGIS_TURN_TIMEOUT", "60")),
            max_active=int(os.getenv("AEGIS_MAX_ACTIVE_PER_WORKER", "32")),
            provider_concurrency=int(os.getenv("AEGIS_PROVIDER_CONCURRENCY", "16")),
            embedding_workers=int(os.getenv("AEGIS_EMBEDDING_WORKERS", "2")),
            max_embedding_pending=int(os.getenv("AEGIS_MAX_EMBEDDING_PENDING", "4")),
            demo_a_token=os.getenv("AEGIS_DEMO_CUSTOMER_A_TOKEN", ""),
            demo_b_token=os.getenv("AEGIS_DEMO_CUSTOMER_B_TOKEN", ""),
            admin_token=os.getenv("AEGIS_ADMIN_TOKEN", ""),
            fixture_path=Path(os.getenv("AEGIS_ORDER_FIXTURES", "data/fixtures/orders.json")),
            demo_as_of=os.getenv("AEGIS_DEMO_AS_OF", "").strip(),
        )
