from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Intent = Literal["product_question", "order_status", "escalate_to_human"]


class Route(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    intent: Intent
    needs_clarification: bool
    reason: str = Field(max_length=300)
