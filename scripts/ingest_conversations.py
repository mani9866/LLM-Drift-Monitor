"""Script to ingest conversations from JSONL into database."""
import json
import argparse
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import SessionLocal, init_db
from src.models.orm import Conversation, Turn


def ingest_conversations(data_dir: str = "data"):
    """Load conversations from JSONL and insert into database."""
    data_path = Path(data_dir)
    conversations_file = data_path / "conversations.jsonl"

    if not conversations_file.exists():
        print(f"Error: {conversations_file} not found")
        return

    # Initialize database
    init_db()
    db = SessionLocal()

    try:
        total = 0
        skipped = 0

        with open(conversations_file, "r") as f:
            for line in f:
                record = json.loads(line)

                # Check if already exists
                existing = db.query(Conversation).filter(
                    Conversation.id == record["id"]
                ).first()

                if existing:
                    skipped += 1
                    continue

                # Create conversation
                conversation = Conversation(
                    id=record["id"],
                    is_drifted=record["is_drifted"],
                    drift_turn_index=record.get("drift_turn_index"),
                    topic_a=record["topic_a"],
                    topic_b=record.get("topic_b"),
                    num_turns=record["num_turns"],
                )
                db.add(conversation)

                # Create turns
                for idx, turn in enumerate(record["turns"]):
                    turn_record = Turn(
                        id=f"{record['id']}_turn_{idx}",
                        conversation_id=record["id"],
                        turn_index=idx,
                        role=turn["role"],
                        content=turn["content"],
                        response_length=len(turn["content"]),
                    )
                    db.add(turn_record)

                db.commit()
                total += 1

                if (total + skipped) % 100 == 0:
                    print(f"Progress: {total} ingested, {skipped} skipped...")

        print(f"\nDone! {total} conversations ingested, {skipped} already existed.")

    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data", help="Directory with conversations.jsonl")
    args = parser.parse_args()

    ingest_conversations(args.data_dir)
