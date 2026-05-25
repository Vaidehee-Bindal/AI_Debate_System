from typing import Any, Literal

from pydantic import BaseModel, Field


Verdict = Literal["True", "False", "Partially True", "Misleading", "Needs Evidence"]
Speaker = Literal["Moderator", "Pro Agent", "Con Agent"]


class DebateCreate(BaseModel):
    topic: str = Field(min_length=5, max_length=240)
    rounds: int = Field(default=3, ge=1, le=5)
    stance_style: str = Field(default="balanced", max_length=60)


class DebateSummary(BaseModel):
    id: str
    topic: str
    status: str
    rounds: int
    current_round: int
    pro_score: int
    con_score: int
    winner: str | None = None
    created_at: str
    updated_at: str


class DebateDetail(DebateSummary):
    messages: list[dict[str, Any]]
    claims: list[dict[str, Any]]
    fact_checks: list[dict[str, Any]]
    scores: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    final_summary: str | None = None


class StreamEvent(BaseModel):
    event: str
    data: dict[str, Any]
