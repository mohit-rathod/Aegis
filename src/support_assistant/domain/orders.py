from dataclasses import dataclass, field
from typing import Any

@dataclass
class HandlerResult:
    kind: str
    data: dict[str, Any] = field(default_factory=dict)
    hits: tuple = ()
    draft: Any = None
    verified_order_id: str | None = None
