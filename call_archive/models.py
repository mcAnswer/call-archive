from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class RetentionDecision(StrEnum):
    DEFAULT = "default"
    KEEP = "keep"
    DELETE = "delete"
    REVIEW = "review"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    REVIEWED = "reviewed"


class ProcessingStatus(StrEnum):
    NEW = "new"
    DONE = "done"
    FAILED = "failed"


class CallNote(BaseModel):
    participants: list[str] = Field(default_factory=list)
    caller_or_contact: str = "unknown"
    category: str
    topic: str
    summary: str
    agreements: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    importance: str = "unknown"
    contains_sensitive_or_legal_content: bool = False
    recommended_retention: RetentionDecision
    reason: str

    @field_validator("importance")
    @classmethod
    def validate_importance(cls, value: str) -> str:
        allowed: set[str] = {"low", "medium", "high", "unknown"}
        if value not in allowed:
            return "unknown"
        return value
