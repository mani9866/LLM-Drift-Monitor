"""SQLAlchemy ORM models."""
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from src.database import Base


class Conversation(Base):
    """Stores conversations with ground-truth labels."""
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, index=True)
    is_drifted = Column(Boolean, nullable=False)
    drift_turn_index = Column(Integer, nullable=True)
    topic_a = Column(String, nullable=False)
    topic_b = Column(String, nullable=True)
    num_turns = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    scored_at = Column(DateTime, nullable=True, index=True)

    # Relationships
    turns = relationship("Turn", back_populates="conversation", cascade="all, delete-orphan")
    metrics = relationship("Metric", back_populates="conversation", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="conversation", cascade="all, delete-orphan")


class Turn(Base):
    """Individual turns within a conversation."""
    __tablename__ = "turns"

    id = Column(String, primary_key=True, index=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False, index=True)
    turn_index = Column(Integer, nullable=False)
    role = Column(String, nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    embedding = Column(JSON, nullable=True)  # Store embedding as list of floats
    response_length = Column(Integer, nullable=True)
    response_latency_ms = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    conversation = relationship("Conversation", back_populates="turns")


class Metric(Base):
    """Drift detection scores for conversations."""
    __tablename__ = "metrics"

    id = Column(String, primary_key=True, index=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False, index=True)
    
    # Three detection scores (0.0 to 1.0)
    semantic_drift_score = Column(Float, nullable=True)
    rolling_window_drift_score = Column(Float, nullable=True)
    response_anomaly_score = Column(Float, nullable=True)
    
    # Drift detection details
    drift_detected = Column(Boolean, default=False, index=True)
    detected_drift_index = Column(Integer, nullable=True)  # Estimated drift turn from rolling window
    
    # Ensemble score (weighted average)
    ensemble_score = Column(Float, nullable=True, index=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="metrics")


class Alert(Base):
    """Alerts fired when drift threshold exceeded."""
    __tablename__ = "alerts"

    id = Column(String, primary_key=True, index=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False, index=True)
    metric_id = Column(String, nullable=True)
    
    drift_score = Column(Float, nullable=False)
    threshold = Column(Float, nullable=False)
    alert_type = Column(String, default="drift_detected")  # "drift_detected", "anomaly", etc.
    
    # Alert status
    fired_at = Column(DateTime, default=datetime.utcnow, index=True)
    webhook_sent = Column(Boolean, default=False)
    webhook_response = Column(String, nullable=True)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="alerts")
