"""Scoring helpers for drift detection workflows."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Mapping, Optional

from sqlalchemy.orm import Session

from src.database import SessionLocal
from src.detectors import compute_all_scores
from src.models.orm import Conversation, Metric, Turn


def _normalize_turns(turns: Any) -> list[dict[str, str]]:
    """Normalize turn objects from either dicts or Pydantic objects."""
    normalized = []
    for turn in turns or []:
        if isinstance(turn, dict):
            role = turn.get("role")
            content = turn.get("content")
        else:
            role = getattr(turn, "role", None)
            content = getattr(turn, "content", None)

        if role is None or content is None:
            continue

        normalized.append({"role": str(role), "content": str(content)})
    return normalized


def score_conversation_payload(payload: Mapping[str, Any], threshold: float = 0.5) -> Dict[str, Any]:
    """Compute drift metrics for a conversation payload."""
    turns = _normalize_turns(payload.get("turns", []))
    conversation = {
        "id": str(payload.get("id", "conversation")),
        "turns": turns,
        "is_drifted": bool(payload.get("is_drifted", False)),
        "drift_turn_index": payload.get("drift_turn_index"),
    }

    scores = compute_all_scores(conversation)
    ensemble_score = float(scores["ensemble_score"])
    drift_detected = ensemble_score >= threshold

    return {
        "semantic_drift": float(scores["semantic_drift"]),
        "rolling_window_drift": float(scores["rolling_window_drift"]),
        "rolling_window_drift_index": int(scores["rolling_window_drift_index"]),
        "response_anomaly": float(scores["response_anomaly"]),
        "ensemble_score": ensemble_score,
        "drift_detected": drift_detected,
        "detected_drift_index": int(scores["rolling_window_drift_index"]),
    }


def score_and_persist_conversation(
    payload: Mapping[str, Any],
    db: Optional[Session] = None,
    threshold: float = 0.5,
) -> Dict[str, Any]:
    """Compute scores and persist them to the database."""
    if db is None:
        db = SessionLocal()

    conversation_id = str(payload.get("id", "conversation"))
    conversation_record = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if conversation_record is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    metrics = score_conversation_payload(payload, threshold=threshold)

    metric_record = Metric(
        id=f"{conversation_id}_metric_{uuid.uuid4().hex[:8]}",
        conversation_id=conversation_id,
        semantic_drift_score=metrics["semantic_drift"],
        rolling_window_drift_score=metrics["rolling_window_drift"],
        response_anomaly_score=metrics["response_anomaly"],
        drift_detected=metrics["drift_detected"],
        detected_drift_index=metrics["detected_drift_index"],
        ensemble_score=metrics["ensemble_score"],
    )
    db.add(metric_record)
    conversation_record.scored_at = datetime.utcnow()
    db.commit()

    return metrics
