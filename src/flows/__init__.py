"""Prefect flow for scoring conversations with drift detectors."""
import uuid
from datetime import datetime
from typing import Dict, Any

from prefect import flow, task, get_run_logger
from sqlalchemy.orm import Session

from src.database import SessionLocal
from src.models.orm import Conversation, Metric, Alert, Turn
from src.detectors import compute_all_scores
import os
import requests


# Configuration
DRIFT_THRESHOLD = 0.5
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")


@task(retries=3)
def fetch_unscored_conversations(batch_size: int = 50) -> list:
    """Fetch conversations that haven't been scored yet."""
    logger = get_run_logger()
    db = SessionLocal()
    try:
        unscored = db.query(Conversation).filter(
            Conversation.scored_at == None
        ).order_by(Conversation.created_at).limit(batch_size).all()

        results = []
        for conv in unscored:
            # Reconstruct conversation dict for detector
            turns = db.query(Turn).filter(
                Turn.conversation_id == conv.id
            ).order_by(Turn.turn_index).all()

            conversation_dict = {
                "id": conv.id,
                "is_drifted": conv.is_drifted,
                "drift_turn_index": conv.drift_turn_index,
                "turns": [
                    {"role": t.role, "content": t.content}
                    for t in turns
                ]
            }

            results.append((conv, conversation_dict))

        logger.info(f"Fetched {len(results)} unscored conversations")
        return results

    finally:
        db.close()


@task
def score_conversation(conv_data: tuple) -> Dict[str, Any]:
    """Compute drift scores for a single conversation."""
    logger = get_run_logger()
    conversation_orm, conversation_dict = conv_data

    try:
        scores = compute_all_scores(conversation_dict)
        scores["conversation_id"] = conversation_orm.id
        scores["is_drifted"] = conversation_orm.is_drifted
        scores["drift_turn_index"] = conversation_orm.drift_turn_index
        logger.info(f"Scored {conversation_orm.id}: ensemble={scores['ensemble_score']:.3f}")
        return scores
    except Exception as e:
        logger.error(f"Error scoring {conversation_orm.id}: {e}")
        return None


@task
def save_metrics(scores_list: list) -> int:
    """Save metrics to database."""
    logger = get_run_logger()
    db = SessionLocal()
    saved_count = 0

    try:
        for scores in scores_list:
            if not scores:
                continue

            conversation_id = scores.pop("conversation_id")
            is_drifted = scores.pop("is_drifted")
            drift_turn_index = scores.pop("drift_turn_index")

            # Determine if drift was detected
            ensemble_score = scores["ensemble_score"]
            drift_detected = ensemble_score >= DRIFT_THRESHOLD

            # Create metric record
            metric = Metric(
                id=str(uuid.uuid4()),
                conversation_id=conversation_id,
                semantic_drift_score=scores["semantic_drift"],
                rolling_window_drift_score=scores["rolling_window_drift"],
                response_anomaly_score=scores["response_anomaly"],
                ensemble_score=ensemble_score,
                drift_detected=drift_detected,
                detected_drift_index=scores.get("rolling_window_drift_index"),
            )

            db.add(metric)

            # Update conversation scored_at
            conversation = db.query(Conversation).filter(
                Conversation.id == conversation_id
            ).first()
            if conversation:
                conversation.scored_at = datetime.utcnow()

            # Check if alert should be fired
            if drift_detected:
                alert = Alert(
                    id=str(uuid.uuid4()),
                    conversation_id=conversation_id,
                    metric_id=metric.id,
                    drift_score=ensemble_score,
                    threshold=DRIFT_THRESHOLD,
                    alert_type="drift_detected",
                )
                db.add(alert)
                logger.info(
                    f"Alert fired for {conversation_id}: "
                    f"score={ensemble_score:.3f} > threshold={DRIFT_THRESHOLD}"
                )

            db.commit()
            saved_count += 1

        logger.info(f"Saved metrics for {saved_count} conversations")
        return saved_count

    except Exception as e:
        logger.error(f"Error saving metrics: {e}")
        db.rollback()
        raise
    finally:
        db.close()


@task
def send_alerts(alerts_list: list = None) -> int:
    """Send Slack notifications for fired alerts."""
    logger = get_run_logger()

    if not SLACK_WEBHOOK_URL:
        logger.info("SLACK_WEBHOOK_URL not set, skipping alerts")
        return 0

    db = SessionLocal()
    sent_count = 0

    try:
        # Get unsent alerts
        unsent_alerts = db.query(Alert).filter(
            Alert.webhook_sent == False
        ).order_by(Alert.fired_at.desc()).limit(10).all()

        for alert in unsent_alerts:
            conversation = db.query(Conversation).filter(
                Conversation.id == alert.conversation_id
            ).first()

            if not conversation:
                continue

            message = {
                "text": f"🚨 LLM Drift Alert",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"*LLM Drift Detected*\n"
                                f"Conversation: `{alert.conversation_id}`\n"
                                f"Drift Score: `{alert.drift_score:.3f}`\n"
                                f"Threshold: `{alert.threshold:.3f}`\n"
                                f"Ground Truth: `{'Drifted' if conversation.is_drifted else 'Coherent'}`"
                            )
                        }
                    }
                ]
            }

            try:
                response = requests.post(SLACK_WEBHOOK_URL, json=message, timeout=5)
                if response.status_code == 200:
                    alert.webhook_sent = True
                    alert.webhook_response = "sent"
                    sent_count += 1
                    logger.info(f"Slack alert sent for {alert.conversation_id}")
                else:
                    alert.webhook_response = f"failed: {response.status_code}"
                    logger.warning(f"Slack alert failed: {response.status_code}")
            except Exception as e:
                alert.webhook_response = f"error: {str(e)}"
                logger.error(f"Error sending Slack alert: {e}")

            db.commit()

        return sent_count

    except Exception as e:
        logger.error(f"Error sending alerts: {e}")
        raise
    finally:
        db.close()


@flow(name="score_conversations", log_prints=True)
def score_conversations_flow(batch_size: int = 50):
    """
    Main Prefect flow: fetch unscored conversations, score them, save metrics, send alerts.
    
    This flow is designed to run on a schedule (e.g., every 5 minutes).
    """
    logger = get_run_logger()
    logger.info(f"Starting scoring flow (batch_size={batch_size})")

    # Fetch unscored conversations
    conv_data_list = fetch_unscored_conversations(batch_size)

    if not conv_data_list:
        logger.info("No unscored conversations, exiting")
        return {"scored": 0, "alerts_sent": 0}

    # Score each conversation in parallel
    scores_list = []
    for conv_data in conv_data_list:
        score = score_conversation(conv_data)
        if score:
            scores_list.append(score)

    # Save all metrics
    saved_count = save_metrics(scores_list)

    # Send alerts
    alerts_sent = send_alerts()

    logger.info(f"Flow completed: {saved_count} scored, {alerts_sent} alerts sent")
    return {"scored": saved_count, "alerts_sent": alerts_sent}


if __name__ == "__main__":
    # Run once for testing
    score_conversations_flow.serve(
        cron="*/5 * * * *",  # Every 5 minutes
        name="score-conversations-deployment",
    )
