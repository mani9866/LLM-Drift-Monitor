"""FastAPI application for ingesting conversations and serving metrics."""
import logging
import os
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, Depends, Header, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from src.database import get_db, init_db
from src.models.orm import Conversation, Turn, Metric
from src.api.schemas import ConversationIngestSchema, ConversationResponseSchema, MetricsSchema
from src.flows.scoring import score_and_persist_conversation

logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="LLM Drift Monitor - Ingest Service",
    description="API for ingesting conversations and accessing drift metrics",
    version="1.0.0"
)


def verify_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    """Require a matching X-API-Key header when API_KEY is configured.

    If the API_KEY env var is unset, auth is skipped entirely so local/dev
    usage is unaffected.
    """
    expected = os.getenv("API_KEY")
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    init_db()


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/conversations", dependencies=[Depends(verify_api_key)])
async def ingest_conversation(
    payload: ConversationIngestSchema,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Ingest a conversation with ground-truth labels.

    Stores the conversation and its turns in Postgres.
    Metrics will be computed by the Prefect flow.
    """
    # Check if conversation already exists
    existing = db.query(Conversation).filter(Conversation.id == payload.id).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Conversation {payload.id} already exists")

    try:
        # Create conversation record
        conversation = Conversation(
            id=payload.id,
            is_drifted=payload.is_drifted,
            drift_turn_index=payload.drift_turn_index,
            topic_a=payload.topic_a,
            topic_b=payload.topic_b,
            num_turns=payload.num_turns,
        )
        db.add(conversation)
        db.flush()

        # Create turn records
        for idx, turn in enumerate(payload.turns):
            turn_record = Turn(
                id=f"{payload.id}_turn_{idx}",
                conversation_id=payload.id,
                turn_index=idx,
                role=turn.role,
                content=turn.content,
                response_length=len(turn.content),
            )
            db.add(turn_record)

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error ingesting conversation: {str(e)}")

    # Scoring is best-effort at ingest time: the conversation is already
    # persisted above, so a scoring failure here must not be reported as an
    # ingest failure (a client retry would otherwise hit a 409).
    scored = True
    score_error = None
    try:
        score_payload = {
            "id": payload.id,
            "is_drifted": payload.is_drifted,
            "drift_turn_index": payload.drift_turn_index,
            "turns": [
                {"role": turn.role, "content": turn.content}
                for turn in payload.turns
            ],
        }
        score_and_persist_conversation(score_payload, db=db)
    except Exception as e:
        logger.warning("Scoring failed for conversation %s: %s", payload.id, e)
        scored = False
        score_error = str(e)

    return {
        "id": payload.id,
        "status": "ingested",
        "scored": scored,
        "score_error": score_error,
        "num_turns": payload.num_turns,
        "message": "Conversation ingested." if scored else
                    "Conversation ingested, but scoring failed and will need to be retried via /score.",
    }


@app.get("/conversations/{conversation_id}/metrics", response_model=ConversationResponseSchema)
async def get_conversation_metrics(
    conversation_id: str,
    db: Session = Depends(get_db),
):
    """
    Get conversation with computed metrics.
    
    Returns the conversation record plus the most recent metrics if available.
    """
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id
    ).first()

    if not conversation:
        raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")

    # Get most recent metrics
    metrics = db.query(Metric).filter(
        Metric.conversation_id == conversation_id
    ).order_by(Metric.created_at.desc()).first()

    metrics_schema = None
    if metrics:
        metrics_schema = MetricsSchema(
            semantic_drift=metrics.semantic_drift_score,
            rolling_window_drift=metrics.rolling_window_drift_score,
            rolling_window_drift_index=metrics.detected_drift_index,
            response_anomaly=metrics.response_anomaly_score,
            ensemble_score=metrics.ensemble_score,
            drift_detected=metrics.drift_detected,
            detected_drift_index=metrics.detected_drift_index,
        )

    return ConversationResponseSchema(
        id=conversation.id,
        is_drifted=conversation.is_drifted,
        drift_turn_index=conversation.drift_turn_index,
        num_turns=conversation.num_turns,
        created_at=conversation.created_at,
        scored_at=conversation.scored_at,
        metrics=metrics_schema,
    )


@app.get("/conversations", response_model=List[ConversationResponseSchema])
async def list_conversations(
    skip: int = 0,
    limit: int = 100,
    unscored_only: bool = False,
    db: Session = Depends(get_db),
):
    """
    List conversations with optional filtering.
    
    Query parameters:
    - skip: Number of conversations to skip (default: 0)
    - limit: Max conversations to return (default: 100, max: 1000)
    - unscored_only: Only return conversations without metrics (default: False)
    """
    limit = min(limit, 1000)

    query = db.query(Conversation)

    if unscored_only:
        query = query.filter(Conversation.scored_at == None)

    conversations = query.order_by(
        Conversation.created_at.desc()
    ).offset(skip).limit(limit).all()

    results = []
    for conv in conversations:
        metrics = db.query(Metric).filter(
            Metric.conversation_id == conv.id
        ).order_by(Metric.created_at.desc()).first()

        metrics_schema = None
        if metrics:
            metrics_schema = MetricsSchema(
                semantic_drift=metrics.semantic_drift_score,
                rolling_window_drift=metrics.rolling_window_drift_score,
                rolling_window_drift_index=metrics.detected_drift_index,
                response_anomaly=metrics.response_anomaly_score,
                ensemble_score=metrics.ensemble_score,
                drift_detected=metrics.drift_detected,
                detected_drift_index=metrics.detected_drift_index,
            )

        results.append(ConversationResponseSchema(
            id=conv.id,
            is_drifted=conv.is_drifted,
            drift_turn_index=conv.drift_turn_index,
            num_turns=conv.num_turns,
            created_at=conv.created_at,
            scored_at=conv.scored_at,
            metrics=metrics_schema,
        ))

    return results


@app.post("/conversations/{conversation_id}/score", dependencies=[Depends(verify_api_key)])
async def score_conversation_endpoint(
    conversation_id: str,
    threshold: float = 0.5,
    db: Session = Depends(get_db),
):
    """Recompute metrics for a specific conversation and persist them."""
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")

    turns = db.query(Turn).filter(Turn.conversation_id == conversation_id).order_by(Turn.turn_index).all()
    payload = {
        "id": conversation.id,
        "is_drifted": conversation.is_drifted,
        "drift_turn_index": conversation.drift_turn_index,
        "turns": [{"role": turn.role, "content": turn.content} for turn in turns],
    }
    metrics = score_and_persist_conversation(payload, db=db, threshold=threshold)
    return {"id": conversation_id, "status": "scored", **metrics}


@app.get("/stats")
async def get_stats(db: Session = Depends(get_db)):
    """Get basic statistics about the dataset."""
    total_conversations = db.query(Conversation).count()
    scored_conversations = db.query(Conversation).filter(
        Conversation.scored_at != None
    ).count()
    drifted_conversations = db.query(Conversation).filter(
        Conversation.is_drifted == True
    ).count()

    return {
        "total_conversations": total_conversations,
        "scored_conversations": scored_conversations,
        "unscored_conversations": total_conversations - scored_conversations,
        "drifted_conversations": drifted_conversations,
        "coherent_conversations": total_conversations - drifted_conversations,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
