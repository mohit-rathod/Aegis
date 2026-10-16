from dataclasses import dataclass,field
from pathlib import Path
import os

@dataclass(frozen=True)
class PartASettings:
    redis_url: str=field(default="redis://127.0.0.1:6379/0",repr=False)
    prefix: str="aegis"
    session_ttl: int=86400
    classifier_ttl: int=300
    classifier_max_entries: int=1000
    turn_timeout: float=60
    max_active: int=32
    provider_concurrency: int=16
    embedding_workers: int=2
    max_embedding_pending: int=4
    demo_a_token: str=field(default="",repr=False)
    demo_b_token: str=field(default="",repr=False)
    admin_token: str=field(default="",repr=False)
    fixture_path: Path=Path("data/fixtures/orders.json")

    def __post_init__(self):
        for key in ["session_ttl","classifier_ttl","classifier_max_entries","turn_timeout","max_active",
                    "provider_concurrency","embedding_workers","max_embedding_pending"]:
            if getattr(self,key)<=0: raise ValueError(f"{key} must be positive")
        if not self.prefix or any(c in self.prefix for c in '{}*? '): raise ValueError("Invalid Redis prefix")
        if self.demo_a_token and self.demo_a_token==self.demo_b_token:
            raise ValueError("Demo customer tokens must differ")

    @classmethod
    def from_env(cls):
        return cls(redis_url=os.getenv("AEGIS_REDIS_URL","redis://127.0.0.1:6379/0"),
            prefix=os.getenv("AEGIS_REDIS_PREFIX","aegis"),
            session_ttl=int(os.getenv("AEGIS_SESSION_TTL","86400")),
            classifier_ttl=int(os.getenv("AEGIS_CLASSIFIER_TTL","300")),
            classifier_max_entries=int(os.getenv("AEGIS_CLASSIFIER_MAX_ENTRIES","1000")),
            turn_timeout=float(os.getenv("AEGIS_TURN_TIMEOUT","60")),
            max_active=int(os.getenv("AEGIS_MAX_ACTIVE_PER_WORKER","32")),
            provider_concurrency=int(os.getenv("AEGIS_PROVIDER_CONCURRENCY","16")),
            embedding_workers=int(os.getenv("AEGIS_EMBEDDING_WORKERS","2")),
            max_embedding_pending=int(os.getenv("AEGIS_MAX_EMBEDDING_PENDING","4")),
            demo_a_token=os.getenv("AEGIS_DEMO_CUSTOMER_A_TOKEN",""),
            demo_b_token=os.getenv("AEGIS_DEMO_CUSTOMER_B_TOKEN",""),
            admin_token=os.getenv("AEGIS_ADMIN_TOKEN",""),
            fixture_path=Path(os.getenv("AEGIS_ORDER_FIXTURES","data/fixtures/orders.json")))
