"""Pydantic schemas for API validation."""
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class TurnSchema(BaseModel):
    """Single turn in a conversation."""
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1)


class ConversationIngestSchema(BaseModel):
    """Conversation payload for ingest."""
    id: str = Field(..., min_length=1)
    is_drifted: bool
    drift_turn_index: Optional[int] = None
    topic_a: str
    topic_b: Optional[str] = None
    num_turns: int = Field(..., gt=0)
    turns: List[TurnSchema] = Field(..., min_items=1)

    class Config:
        json_schema_extra = {
            "example": {
                "id": "conv_0001",
                "is_drifted": True,
                "drift_turn_index": 3,
                "topic_a": "learning Python",
                "topic_b": "cooking recipes",
                "num_turns": 6,
                "turns": [
                    {"role": "user", "content": "How do I learn Python?"},
                    {"role": "assistant", "content": "Start with basics..."},
                ]
            }
        }


class MetricsSchema(BaseModel):
    """Drift detection metrics."""
    semantic_drift: Optional[float] = None
    rolling_window_drift: Optional[float] = None
    rolling_window_drift_index: Optional[int] = None
    response_anomaly: Optional[float] = None
    ensemble_score: Optional[float] = None
    drift_detected: bool
    detected_drift_index: Optional[int] = None


class ConversationResponseSchema(BaseModel):
    """Response with conversation + metrics."""
    id: str
    is_drifted: bool
    drift_turn_index: Optional[int]
    num_turns: int
    created_at: datetime
    scored_at: Optional[datetime]
    metrics: Optional[MetricsSchema] = None

    class Config:
        from_attributes = True
