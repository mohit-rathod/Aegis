from dataclasses import dataclass
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

@dataclass(frozen=True)
class Document:
    document_id: str
    title: str
    path: str
    version: str
    body: str
    sha256: str

@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    text: str

@dataclass(frozen=True)
class Hit:
    document: Document
    score: float
    matched_chunk_ids: tuple[str, ...]

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

class Claim(StrictModel):
    text: str = Field(min_length=1, max_length=1200)
    citations: list[str] = Field(min_length=1, max_length=3)

class AnswerDraft(StrictModel):
    status: Literal["answer", "abstain", "tool_required"]
    claims: list[Claim] = Field(max_length=6)

class InputDecision(StrictModel):
    allowed: bool
    reason: str = Field(max_length=300)

class SupportDecision(StrictModel):
    supported: bool
    reason: str = Field(max_length=300)

