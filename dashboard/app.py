"""Streamlit dashboard for LLM drift monitoring."""
import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from sqlalchemy.orm import Session

# Add parent directory to path so `src` is importable regardless of cwd
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import SessionLocal
from src.models.orm import Conversation, Turn, Metric, Alert
from src.detectors import compute_all_scores, get_embeddings, cosine_distance


st.set_page_config(
    page_title="LLM Drift Monitor",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Styling
st.markdown("""
    <style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
    }
    .alert-danger {
        background-color: #fee;
        color: #a00;
        padding: 15px;
        border-radius: 5px;
        border-left: 4px solid #a00;
    }
    .alert-success {
        background-color: #efe;
        color: #0a0;
        padding: 15px;
        border-radius: 5px;
        border-left: 4px solid #0a0;
    }
    </style>
""", unsafe_allow_html=True)

# Page title and description
st.title("🔍 LLM Drift Monitor")
st.markdown("**Real-time monitoring of LLM conversation drift with multi-metric detection**")


@st.cache_resource
def get_db_session():
    """Get database session (cached)."""
    return SessionLocal()


def get_stats():
    """Fetch current statistics."""
    db = get_db_session()
    total = db.query(Conversation).count()
    scored = db.query(Conversation).filter(Conversation.scored_at != None).count()
    drifted = db.query(Conversation).filter(Conversation.is_drifted == True).count()
    alerts = db.query(Alert).count()
    return {
        "total": total,
        "scored": scored,
        "drifted": drifted,
        "alerts": alerts,
    }


def get_conversations_with_metrics(limit: int = 100):
    """Fetch conversations with their metrics."""
    db = get_db_session()
    conversations = db.query(Conversation).order_by(
        Conversation.scored_at.desc()
    ).limit(limit).all()

    data = []
    for conv in conversations:
        metric = db.query(Metric).filter(
            Metric.conversation_id == conv.id
        ).order_by(Metric.created_at.desc()).first()

        data.append({
            "id": conv.id,
            "is_drifted": conv.is_drifted,
            "num_turns": conv.num_turns,
            "ground_truth": "Drifted" if conv.is_drifted else "Coherent",
            "semantic_drift": metric.semantic_drift_score if metric else None,
            "rolling_window_drift": metric.rolling_window_drift_score if metric else None,
            "response_anomaly": metric.response_anomaly_score if metric else None,
            "ensemble_score": metric.ensemble_score if metric else None,
            "drift_detected": metric.drift_detected if metric else False,
            "detected_index": metric.detected_drift_index if metric else None,
            "created_at": conv.created_at,
            "scored_at": conv.scored_at,
        })

    return pd.DataFrame(data)


def get_conversation_detail(conversation_id: str):
    """Get detailed information about a conversation."""
    db = get_db_session()
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        return None

    turns = db.query(Turn).filter(
        Turn.conversation_id == conversation_id
    ).order_by(Turn.turn_index).all()

    metrics = db.query(Metric).filter(
        Metric.conversation_id == conversation_id
    ).order_by(Metric.created_at.desc()).first()

    alerts = db.query(Alert).filter(
        Alert.conversation_id == conversation_id
    ).all()

    return {
        "conversation": conv,
        "turns": turns,
        "metrics": metrics,
        "alerts": alerts,
    }


def plot_conversation_drift(conversation_id: str):
    """Plot turn-by-turn drift scores with breakpoint."""
    db = get_db_session()
    turns = db.query(Turn).filter(
        Turn.conversation_id == conversation_id
    ).order_by(Turn.turn_index).all()

    metric = db.query(Metric).filter(
        Metric.conversation_id == conversation_id
    ).order_by(Metric.created_at.desc()).first()

    # Get embeddings
    texts = [t.content for t in turns]
    embeddings = get_embeddings(texts)

    # Compute centroid
    centroid = embeddings.mean(axis=0)

    # Compute turn-by-turn distances
    distances = []
    for embedding in embeddings:
        dist = cosine_distance(embedding, centroid)
        distances.append(dist)

    # Create figure
    fig = go.Figure()

    # Add distance line
    fig.add_trace(go.Scatter(
        x=list(range(len(distances))),
        y=distances,
        mode="lines+markers",
        name="Distance to centroid",
        line=dict(color="blue", width=2),
        marker=dict(size=8),
    ))

    # Mark detected drift point
    if metric and metric.detected_drift_index is not None:
        fig.add_vline(
            x=metric.detected_drift_index,
            line_dash="dash",
            line_color="red",
            annotation_text="Detected Drift",
            annotation_position="top left",
        )

    # Mark ground truth drift point
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if conv and conv.is_drifted and conv.drift_turn_index is not None:
        fig.add_vline(
            x=conv.drift_turn_index,
            line_dash="dash",
            line_color="green",
            annotation_text=f"Ground Truth ({conv.drift_turn_index})",
            annotation_position="top right",
        )

    fig.update_layout(
        title=f"Turn-by-Turn Drift: {conversation_id}",
        xaxis_title="Turn Index",
        yaxis_title="Distance to Centroid",
        hovermode="x unified",
        height=400,
    )

    return fig


def plot_time_series_drift():
    """Plot time-series of drift rate across corpus."""
    db = get_db_session()

    # Get drift metrics by hour
    metrics = db.query(
        Metric.created_at,
        Metric.ensemble_score,
        Metric.drift_detected,
    ).all()

    if not metrics:
        st.warning("No metrics data available yet")
        return None

    # Bin by hour
    df = pd.DataFrame([
        {
            "timestamp": m.created_at,
            "ensemble_score": m.ensemble_score,
            "drift_detected": m.drift_detected,
        }
        for m in metrics
    ])

    df["hour"] = pd.to_datetime(df["timestamp"]).dt.floor("H")
    hourly = df.groupby("hour").agg({
        "drift_detected": "sum",
        "ensemble_score": "mean",
    }).reset_index()

    # Total conversations per hour
    hourly["total"] = df.groupby("hour").size().values
    hourly["drift_rate"] = hourly["drift_detected"] / hourly["total"]

    # Create figure
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=hourly["hour"],
        y=hourly["drift_rate"],
        mode="lines+markers",
        name="Drift Rate",
        line=dict(color="red", width=2),
        marker=dict(size=8),
    ))

    fig.update_layout(
        title="Drift Rate Over Time",
        xaxis_title="Time",
        yaxis_title="Drift Rate (0.0-1.0)",
        hovermode="x unified",
        height=400,
    )

    return fig


# Sidebar navigation
st.sidebar.title("Navigation")
page = st.sidebar.radio(
    "Select View:",
    ["Overview", "Conversation List", "Conversation Detail", "Time Series Analysis"],
    label_visibility="collapsed",
)

# Configuration in sidebar
st.sidebar.markdown("---")
st.sidebar.title("⚙️ Configuration")
drift_threshold = st.sidebar.slider("Drift Threshold", 0.0, 1.0, 0.5, 0.05)
st.sidebar.markdown(f"Using threshold: **{drift_threshold:.2f}**")

# Main content
if page == "Overview":
    st.header("📊 Overview")

    # Stats
    stats = get_stats()
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Conversations", stats["total"])

    with col2:
        st.metric("Scored", stats["scored"])

    with col3:
        st.metric("Ground-Truth Drifted", stats["drifted"])

    with col4:
        st.metric("Alerts Fired", stats["alerts"])

    st.markdown("---")

    # Recent alerts
    st.subheader("🚨 Recent Alerts")
    db = get_db_session()
    recent_alerts = db.query(Alert).order_by(Alert.fired_at.desc()).limit(5).all()

    if recent_alerts:
        alert_data = []
        for alert in recent_alerts:
            conv = db.query(Conversation).filter(Conversation.id == alert.conversation_id).first()
            alert_data.append({
                "Conversation": alert.conversation_id,
                "Score": f"{alert.drift_score:.3f}",
                "Ground Truth": "Drifted" if conv and conv.is_drifted else "Coherent",
                "Time": alert.fired_at.strftime("%Y-%m-%d %H:%M:%S"),
            })
        st.table(pd.DataFrame(alert_data))
    else:
        st.info("No alerts fired yet")

    st.markdown("---")

    # Score distribution
    st.subheader("📈 Ensemble Score Distribution")
    df_conversations = get_conversations_with_metrics(500)

    if len(df_conversations) > 0:
        fig = px.histogram(
            df_conversations[df_conversations["ensemble_score"].notna()],
            x="ensemble_score",
            nbins=30,
            color="ground_truth",
            barmode="overlay",
            title="Ensemble Score Distribution",
            labels={"ensemble_score": "Ensemble Score", "ground_truth": "Ground Truth"},
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)


elif page == "Conversation List":
    st.header("📋 Conversation List")

    # Filters
    col1, col2 = st.columns(2)
    with col1:
        ground_truth_filter = st.selectbox(
            "Filter by Ground Truth:",
            ["All", "Drifted", "Coherent"],
        )
    with col2:
        limit = st.selectbox("Show top N:", [50, 100, 200, 500])

    # Load data
    df = get_conversations_with_metrics(limit)

    if len(df) > 0:
        # Apply filter
        if ground_truth_filter == "Drifted":
            df = df[df["is_drifted"] == True]
        elif ground_truth_filter == "Coherent":
            df = df[df["is_drifted"] == False]

        # Display table
        display_cols = [
            "id", "ground_truth", "num_turns", "ensemble_score",
            "semantic_drift", "rolling_window_drift", "response_anomaly",
            "drift_detected", "detected_index"
        ]
        df_display = df[display_cols].copy()
        df_display.columns = [
            "ID", "Ground Truth", "Turns", "Ensemble",
            "Semantic", "Rolling", "Anomaly",
            "Detected", "Detected Index"
        ]

        st.dataframe(df_display, use_container_width=True, height=600)


elif page == "Conversation Detail":
    st.header("🔬 Conversation Detail")

    # Select conversation
    df = get_conversations_with_metrics(500)
    if len(df) > 0:
        selected_id = st.selectbox(
            "Select Conversation:",
            df["id"].tolist(),
        )

        detail = get_conversation_detail(selected_id)

        if detail:
            conv = detail["conversation"]
            turns = detail["turns"]
            metric = detail["metrics"]
            alerts = detail["alerts"]

            # Header
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Turns", len(turns))
            with col2:
                st.metric("Ground Truth", "Drifted" if conv.is_drifted else "Coherent")
            with col3:
                st.metric("Detected", "Drifted" if metric and metric.drift_detected else "Coherent")

            if metric:
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Ensemble", f"{metric.ensemble_score:.3f}")
                with col2:
                    st.metric("Semantic", f"{metric.semantic_drift_score:.3f}")
                with col3:
                    st.metric("Rolling Window", f"{metric.rolling_window_drift_score:.3f}")
                with col4:
                    st.metric("Anomaly", f"{metric.response_anomaly_score:.3f}")

            st.markdown("---")

            # Drift visualization
            st.subheader("Turn-by-Turn Drift")
            fig = plot_conversation_drift(selected_id)
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("---")

            # Conversation turns
            st.subheader("Conversation Transcript")
            for turn in turns:
                if turn.role == "user":
                    st.markdown(f"👤 **User:** {turn.content}")
                else:
                    st.markdown(f"🤖 **Assistant:** {turn.content}")

            # Alerts
            if alerts:
                st.markdown("---")
                st.subheader("⚠️ Alerts")
                for alert in alerts:
                    with st.container():
                        st.markdown(
                            f"<div class='alert-danger'>"
                            f"<strong>Alert:</strong> Score {alert.drift_score:.3f} > Threshold {alert.threshold:.3f}<br>"
                            f"<strong>Time:</strong> {alert.fired_at}<br>"
                            f"<strong>Status:</strong> {'Sent to Slack' if alert.webhook_sent else 'Pending'}"
                            f"</div>",
                            unsafe_allow_html=True,
                        )


elif page == "Time Series Analysis":
    st.header("📈 Time Series Analysis")

    fig = plot_time_series_drift()
    if fig:
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Statistics by hour
    st.subheader("Hourly Statistics")
    db = get_db_session()
    metrics = db.query(
        Metric.created_at,
        Metric.drift_detected,
    ).all()

    if metrics:
        df = pd.DataFrame([
            {
                "timestamp": m.created_at,
                "drift_detected": m.drift_detected,
            }
            for m in metrics
        ])

        df["hour"] = pd.to_datetime(df["timestamp"]).dt.floor("H")
        hourly = df.groupby("hour").agg({
            "drift_detected": ["sum", "count"],
        }).reset_index()
        hourly.columns = ["Hour", "Drifted", "Total"]
        hourly["Drift Rate %"] = (hourly["Drifted"] / hourly["Total"] * 100).round(1)

        st.dataframe(hourly, use_container_width=True)
    else:
        st.info("No time-series data available yet")

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #999; font-size: 0.8em;'>
    LLM Drift Monitor • Real-time observability for LLM drift
    </div>
    """,
    unsafe_allow_html=True,
)
