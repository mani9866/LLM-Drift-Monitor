"""
Generate a labeled dataset of synthetic multi-turn conversations for the
LLM observability / drift-monitoring project (Week 1: data + ingest).

Two conversation classes are produced:
  - coherent: every turn stays on one topic
  - drifted:  the topic shifts at a known turn index (the ground-truth label)

Usage:
    export ANTHROPIC_API_KEY=...   # or `ant auth login`
    python scripts/generate_conversations.py --num-total 800

Output (in --output-dir, default ./data):
    conversations.jsonl  - full conversation records with embedded labels
    labels.csv           - lightweight ground-truth file for scoring

Uses the Message Batches API (50% cheaper, no latency requirement) since
this is a one-shot bulk generation job, not an interactive workload.
"""

import argparse
import csv
import json
import random
import sys
import time
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

from topics import TOPICS

TURN_SCHEMA = {
    "type": "object",
    "properties": {
        "turns": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "role": {"type": "string", "enum": ["user", "assistant"]},
                    "content": {"type": "string"},
                },
                "required": ["role", "content"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["turns"],
    "additionalProperties": False,
}


def build_jobs(num_total: int, coherent_ratio: float, min_turns: int, max_turns: int, rng: random.Random):
    """Create job specs (not yet API requests) for every conversation to generate."""
    num_coherent = round(num_total * coherent_ratio)
    jobs = []

    for i in range(num_total):
        is_drifted = i >= num_coherent
        # even turn count so the conversation ends on an assistant turn
        num_turns = rng.randrange(min_turns, max_turns + 1, 2)

        if not is_drifted:
            topic_a = rng.choice(TOPICS)
            jobs.append({
                "id": f"conv_{i:04d}",
                "is_drifted": False,
                "topic_a": topic_a,
                "topic_b": None,
                "num_turns": num_turns,
                "drift_turn_index": None,
            })
        else:
            topic_a, topic_b = rng.sample(TOPICS, 2)
            user_indices = list(range(0, num_turns, 2))
            # need at least one exchange before and after the drift
            valid_drift_indices = user_indices[1:-1] if len(user_indices) >= 3 else user_indices[1:]
            drift_turn_index = rng.choice(valid_drift_indices)
            jobs.append({
                "id": f"conv_{i:04d}",
                "is_drifted": True,
                "topic_a": topic_a,
                "topic_b": topic_b,
                "num_turns": num_turns,
                "drift_turn_index": drift_turn_index,
            })

    rng.shuffle(jobs)
    return jobs


def build_prompt(job: dict) -> str:
    if not job["is_drifted"]:
        return (
            f"Write a realistic, natural multi-turn text conversation between a user "
            f"and an AI assistant. The entire conversation must stay tightly focused on "
            f"this single topic: '{job['topic_a']}'. Generate exactly {job['num_turns']} "
            f"turns total, alternating starting with the user (user, assistant, user, "
            f"assistant, ...). Each user turn should build naturally on the assistant's "
            f"previous reply (follow-up questions, requests for more detail, related "
            f"sub-questions) — do not introduce any unrelated topic. Keep each message "
            f"realistic in length (1-4 sentences), like a real chat log, not a lecture. "
            f"Return only the conversation."
        )
    return (
        f"Write a realistic, natural multi-turn text conversation between a user and an "
        f"AI assistant. Generate exactly {job['num_turns']} turns total, alternating "
        f"starting with the user (user, assistant, user, assistant, ...).\n\n"
        f"For turn indices 0 through {job['drift_turn_index'] - 1}, the conversation "
        f"should stay tightly focused on this topic: '{job['topic_a']}'.\n\n"
        f"Starting at turn index {job['drift_turn_index']} (a user message), the user "
        f"should abruptly shift the conversation to a new, unrelated topic: "
        f"'{job['topic_b']}'. Make the shift feel like something a real person might do "
        f"mid-chat — do not explicitly announce it as a topic change (avoid phrases like "
        f"'changing the subject'). From that point through the end of the conversation, "
        f"stay focused on '{job['topic_b']}'.\n\n"
        f"Keep each message realistic in length (1-4 sentences). Return only the "
        f"conversation."
    )


def build_batch_request(job: dict, model: str) -> Request:
    return Request(
        custom_id=job["id"],
        params=MessageCreateParamsNonStreaming(
            model=model,
            max_tokens=2048,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": TURN_SCHEMA}},
            messages=[{"role": "user", "content": build_prompt(job)}],
        ),
    )


def poll_batch(client: anthropic.Anthropic, batch_id: str, interval_s: int):
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        counts = batch.request_counts
        print(
            f"  status={batch.processing_status} "
            f"processing={counts.processing} succeeded={counts.succeeded} "
            f"errored={counts.errored} canceled={counts.canceled} expired={counts.expired}",
            file=sys.stderr,
        )
        if batch.processing_status == "ended":
            return batch
        time.sleep(interval_s)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--num-total", type=int, default=800, help="total conversations to generate")
    parser.add_argument("--coherent-ratio", type=float, default=0.5, help="fraction that stay on-topic (rest drift)")
    parser.add_argument("--min-turns", type=int, default=6, help="minimum turns per conversation (even)")
    parser.add_argument("--max-turns", type=int, default=12, help="maximum turns per conversation (even)")
    parser.add_argument("--model", default="claude-opus-4-8", help="model to use for generation")
    parser.add_argument("--output-dir", default="data", help="directory to write conversations.jsonl and labels.csv")
    parser.add_argument("--seed", type=int, default=42, help="random seed for topic/drift-index selection")
    parser.add_argument("--poll-interval", type=int, default=20, help="seconds between batch status checks")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    jobs = build_jobs(args.num_total, args.coherent_ratio, args.min_turns, args.max_turns, rng)
    jobs_by_id = {job["id"]: job for job in jobs}

    print(f"Built {len(jobs)} job specs "
          f"({sum(not j['is_drifted'] for j in jobs)} coherent, "
          f"{sum(j['is_drifted'] for j in jobs)} drifted). Submitting batch...", file=sys.stderr)

    client = anthropic.Anthropic()
    requests = [build_batch_request(job, args.model) for job in jobs]
    batch = client.messages.batches.create(requests=requests)
    print(f"Batch created: {batch.id}", file=sys.stderr)

    batch = poll_batch(client, batch.id, args.poll_interval)

    conversations_path = output_dir / "conversations.jsonl"
    labels_path = output_dir / "labels.csv"

    num_written = 0
    num_errored = 0
    num_shape_mismatch = 0

    with open(conversations_path, "w", encoding="utf-8") as conv_f, \
         open(labels_path, "w", encoding="utf-8", newline="") as labels_f:

        labels_writer = csv.writer(labels_f)
        labels_writer.writerow(["id", "is_drifted", "drift_turn_index", "topic_a", "topic_b", "num_turns"])

        for result in client.messages.batches.results(batch.id):
            job = jobs_by_id[result.custom_id]

            if result.result.type != "succeeded":
                num_errored += 1
                continue

            text = next(
                (b.text for b in result.result.message.content if b.type == "text"),
                None,
            )
            if text is None:
                num_errored += 1
                continue

            try:
                turns = json.loads(text)["turns"]
            except (json.JSONDecodeError, KeyError, TypeError):
                num_errored += 1
                continue

            if len(turns) != job["num_turns"] or any(
                t["role"] != ("user" if i % 2 == 0 else "assistant") for i, t in enumerate(turns)
            ):
                num_shape_mismatch += 1
                continue

            record = {
                "id": job["id"],
                "is_drifted": job["is_drifted"],
                "topic_a": job["topic_a"],
                "topic_b": job["topic_b"],
                "drift_turn_index": job["drift_turn_index"],
                "num_turns": job["num_turns"],
                "turns": turns,
            }
            conv_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            labels_writer.writerow([
                job["id"], job["is_drifted"], job["drift_turn_index"],
                job["topic_a"], job["topic_b"], job["num_turns"],
            ])
            num_written += 1

    print(
        f"\nDone. {num_written} conversations written to {conversations_path} "
        f"and {labels_path}.\n"
        f"Discarded: {num_errored} API errors, {num_shape_mismatch} shape mismatches "
        f"(out of {len(jobs)} requested).",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
