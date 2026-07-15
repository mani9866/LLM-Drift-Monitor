"""
Generate synthetic conversations WITHOUT API calls.

Uses templates and random selection to create realistic multi-turn conversations
with ground-truth drift labels. Fast, free, reproducible.

Usage:
    python scripts/generate_mock_conversations.py --num-total 800
"""

import argparse
import csv
import json
import random
from pathlib import Path
from typing import List, Dict, Any


TOPICS = [
    "planning a two-week trip to Japan",
    "debugging a Python memory leak",
    "starting a ketogenic diet",
    "basics of index fund investing",
    "training a puppy not to bite",
    "writing a college application essay",
    "budgeting a kitchen renovation",
    "routine car maintenance schedules",
    "learning acoustic guitar as a beginner",
    "starting a small online business",
    "improving marathon running times",
    "meal-prepping for a busy work week",
    "choosing a home security system",
    "basics of home gardening in containers",
    "understanding mortgage interest rates",
    "preparing for a coding interview",
    "writing a professional resume",
    "learning conversational Spanish",
    "astronomy for backyard stargazing",
    "getting started with film photography",
    "planning a small backyard wedding",
    "adopting a rescue cat",
    "understanding basic tax deductions",
    "starting a meditation practice",
    "picking a new gaming PC build",
    "improving sleep quality",
    "learning to bake sourdough bread",
    "choosing health insurance plans",
    "getting into rock climbing",
    "building a personal finance spreadsheet",
    "watercolor painting for beginners",
    "understanding climate change basics",
    "starting a vegetable compost bin",
    "preparing for a job interview",
    "learning basic woodworking",
    "picking a language to learn next",
    "understanding cryptocurrency basics",
    "training for a first triathlon",
    "choosing a college major",
    "planning a cross-country move",
    "improving public speaking skills",
]

# Conversation templates (coherent conversations)
COHERENT_PATTERNS = [
    [
        "How do I get started with {topic}?",
        "I'd recommend starting with the basics. First, {advice1}. This will give you a foundation.",
        "That makes sense. What's the next step?",
        "After you're comfortable with that, {advice2}. This usually takes a few weeks of practice.",
        "How long did it take you to reach this level?",
        "For most people, it takes {time} to build solid fundamentals. The key is consistent practice and patience.",
    ],
    [
        "I'm interested in {topic}. What should I know?",
        "{topic_description} The most important thing to understand is {key_concept}.",
        "Can you give me a concrete example?",
        "Sure. {example}. This demonstrates {example_principle}.",
        "That's really helpful. Any resources you'd recommend?",
        "I'd suggest starting with {resource}. It covers everything you need to know.",
    ],
    [
        "What are the biggest challenges with {topic}?",
        "The main challenges are {challenge1} and {challenge2}. Most people struggle with these early on.",
        "How can I overcome those challenges?",
        "The best approach is to {technique}. This helps you avoid common pitfalls.",
        "Is there anything else I should be aware of?",
        "Make sure to {warning}. This can save you a lot of time and frustration.",
    ],
]

# Drift patterns (conversations that abruptly change topic)
DRIFT_CONTEXT = [
    ("question about {topic_a}", "But actually, I wanted to ask about {topic_b}"),
    ("discussing {topic_a}", "Actually, can I change the subject? I'm curious about {topic_b}"),
    ("talking about {topic_a}", "Wait, before we go further—do you know anything about {topic_b}?"),
    ("focused on {topic_a}", "This has been great, but I just realized I should ask about {topic_b}"),
]

ADVICE_SNIPPETS = {
    "planning a trip": [
        "research the season and climate",
        "book accommodations well in advance",
        "plan your daily itinerary",
        "arrange transportation ahead of time",
    ],
    "debugging": [
        "enable verbose logging",
        "use a debugger to step through the code",
        "isolate the problematic section",
        "check memory usage with tools like valgrind",
    ],
    "diet": [
        "calculate your macronutrient targets",
        "meal prep on Sundays",
        "find keto-friendly recipes",
        "track your meals with an app",
    ],
    "investing": [
        "start with low-cost index funds",
        "understand your risk tolerance",
        "diversify across asset classes",
        "avoid trying to time the market",
    ],
    "pets": [
        "establish consistent routines",
        "use positive reinforcement",
        "socialize early and often",
        "work with a professional trainer",
    ],
    "writing": [
        "brainstorm your main themes",
        "create an outline first",
        "write multiple drafts",
        "have someone else read it",
    ],
}

EXAMPLE_SNIPPETS = {
    "planning a trip": "If you're going in cherry blossom season (March-April), book hotels 2-3 months ahead. Prices triple during peak times.",
    "debugging": "Add print statements or use pdb to track variable values at each step. You'll often spot the issue within minutes.",
    "diet": "Start by calculating your daily calorie needs, then aim for 70-75% of calories from fat, 20-25% from protein.",
    "investing": "A simple portfolio is 70% VOO (S&P 500 index) and 30% BND (bond index). Rebalance annually.",
    "pets": "Spend 15 minutes daily doing training sessions with small treats. Dogs learn better with frequent, short sessions.",
    "writing": "Outline should list main arguments in order, then spend 1-2 hours writing without editing. Save editing for draft 2.",
}

RESOURCE_SNIPPETS = {
    "planning a trip": "Lonely Planet guides and Google Maps offline mode",
    "debugging": "Python's pdb debugger or print-based debugging",
    "diet": "MyFitnessPal app and keto subreddits",
    "investing": "Bogleheads forum and Mr. Money Mustache blog",
    "pets": "Zak George's YouTube channel",
    "writing": "The book 'Elements of Style' and feedback from peers",
}

TIME_SNIPPETS = {
    "planning a trip": "2-3 months to plan properly",
    "debugging": "hours to days depending on complexity",
    "diet": "weeks to see results, months to adapt",
    "investing": "years to build real wealth",
    "pets": "weeks to see behavior change",
    "writing": "weeks to several months",
}

WARNINGS = {
    "planning a trip": "check visa requirements early—some take weeks to process",
    "debugging": "print statements can slow down performance significantly",
    "diet": "consult a doctor before major diet changes",
    "investing": "high-risk investments are not for beginners",
    "pets": "punishment-based training can cause behavioral issues",
    "writing": "perfectionism can prevent you from finishing",
}


def get_advice(topic: str, rng: random.Random) -> tuple:
    """Get advice, example, resource, and warning for a topic."""
    # Extract base topic (first 2-3 words)
    base_topic = " ".join(topic.split()[:2]).lower()
    
    advice1 = rng.choice(ADVICE_SNIPPETS.get(base_topic, ["get the fundamentals down", "start small and build up"]))
    advice2 = rng.choice(ADVICE_SNIPPETS.get(base_topic, ["practice regularly", "join a community"]))
    
    example = EXAMPLE_SNIPPETS.get(base_topic, "This principle applies in practice as well.")
    resource = RESOURCE_SNIPPETS.get(base_topic, "online tutorials and communities")
    time_val = TIME_SNIPPETS.get(base_topic, "a few weeks")
    warning = WARNINGS.get(base_topic, "take things one step at a time")
    
    return advice1, advice2, example, resource, time_val, warning


def generate_coherent_conversation(topic: str, num_turns: int, rng: random.Random) -> List[Dict[str, str]]:
    """Generate a coherent multi-turn conversation on a single topic."""
    pattern = rng.choice(COHERENT_PATTERNS)
    advice1, advice2, example, resource, time_val, warning = get_advice(topic, rng)
    
    # Fill template with values
    template = pattern[:]
    filled = []
    
    for turn_text in template:
        filled_turn = (
            turn_text
            .replace("{topic}", topic)
            .replace("{topic_description}", f"Learning {topic} is a great goal.")
            .replace("{key_concept}", "understanding the fundamentals first")
            .replace("{advice1}", advice1)
            .replace("{advice2}", advice2)
            .replace("{example}", example)
            .replace("{example_principle}", "the core principle")
            .replace("{resource}", resource)
            .replace("{time}", time_val)
            .replace("{challenge1}", "getting started")
            .replace("{challenge2}", "staying motivated")
            .replace("{technique}", "breaking it into smaller steps")
            .replace("{warning}", warning)
        )
        filled.append(filled_turn)
    
    # Cycle through turns if we need more than the template
    turns = []
    for i in range(num_turns):
        role = "user" if i % 2 == 0 else "assistant"
        content = filled[i % len(filled)]
        # Slightly vary the content to avoid exact repetition
        if role == "user" and i > 0:
            variants = [
                f"Tell me more about that.",
                f"That's interesting. What else?",
                f"How does that help?",
                f"Can you explain that better?",
                f"What's an example?",
            ]
            if i > 1:
                content = rng.choice(variants)
        
        turns.append({"role": role, "content": content})
    
    return turns


def generate_drifted_conversation(topic_a: str, topic_b: str, num_turns: int, drift_turn_index: int, rng: random.Random) -> List[Dict[str, str]]:
    """Generate a conversation that drifts from topic_a to topic_b."""
    advice_a1, advice_a2, example_a, resource_a, time_a, warning_a = get_advice(topic_a, rng)
    advice_b1, advice_b2, example_b, resource_b, time_b, warning_b = get_advice(topic_b, rng)
    
    turns = []
    
    # First half: coherent on topic_a
    for i in range(drift_turn_index):
        role = "user" if i % 2 == 0 else "assistant"
        if role == "user":
            content = f"What about {topic_a}?"
        else:
            content = f"For {topic_a}, I recommend starting with {advice_a1}."
        turns.append({"role": role, "content": content})
    
    # Drift point: user introduces new topic
    turns.append({
        "role": "user",
        "content": f"Actually, I wanted to ask about {topic_b} instead."
    })
    
    # Second half: coherent on topic_b
    for i in range(drift_turn_index + 1, num_turns):
        role = "user" if i % 2 == 0 else "assistant"
        if role == "user":
            content = f"So how do I start with {topic_b}?"
        else:
            content = f"For {topic_b}, the key is to {advice_b1}."
        turns.append({"role": role, "content": content})
    
    return turns


def generate_conversations(num_total: int, coherent_ratio: float, min_turns: int, max_turns: int, seed: int):
    """Generate all conversations."""
    rng = random.Random(seed)
    
    num_coherent = round(num_total * coherent_ratio)
    conversations = []
    
    print(f"Generating {num_total} conversations ({num_coherent} coherent, {num_total - num_coherent} drifted)...")
    
    for i in range(num_total):
        # Even turn count (ends on assistant turn)
        num_turns = rng.randrange(min_turns, max_turns + 1, 2)
        
        if i < num_coherent:
            # Coherent conversation
            topic = rng.choice(TOPICS)
            turns = generate_coherent_conversation(topic, num_turns, rng)
            
            record = {
                "id": f"conv_{i:04d}",
                "is_drifted": False,
                "topic_a": topic,
                "topic_b": None,
                "drift_turn_index": None,
                "num_turns": num_turns,
                "turns": turns,
            }
        else:
            # Drifted conversation
            topic_a, topic_b = rng.sample(TOPICS, 2)
            user_indices = list(range(0, num_turns, 2))
            valid_drift_indices = user_indices[1:-1] if len(user_indices) >= 3 else user_indices[1:] if user_indices else [1]
            drift_turn_index = rng.choice(valid_drift_indices) if valid_drift_indices else 1
            
            turns = generate_drifted_conversation(topic_a, topic_b, num_turns, drift_turn_index, rng)
            
            record = {
                "id": f"conv_{i:04d}",
                "is_drifted": True,
                "topic_a": topic_a,
                "topic_b": topic_b,
                "drift_turn_index": drift_turn_index,
                "num_turns": num_turns,
                "turns": turns,
            }
        
        conversations.append(record)
        
        if (i + 1) % 100 == 0:
            print(f"  Generated {i + 1}/{num_total}...")
    
    return conversations


def save_conversations(conversations: List[Dict[str, Any]], output_dir: str):
    """Save conversations and labels to disk."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    conversations_file = output_path / "conversations.jsonl"
    labels_file = output_path / "labels.csv"
    
    # Write conversations
    with open(conversations_file, "w", encoding="utf-8") as f:
        for conv in conversations:
            f.write(json.dumps(conv, ensure_ascii=False) + "\n")
    
    # Write labels
    with open(labels_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "is_drifted", "drift_turn_index", "topic_a", "topic_b", "num_turns"])
        for conv in conversations:
            writer.writerow([
                conv["id"],
                int(conv["is_drifted"]),
                conv["drift_turn_index"],
                conv["topic_a"],
                conv["topic_b"],
                conv["num_turns"],
            ])
    
    print(f"\n✅ Saved {len(conversations)} conversations to {conversations_file}")
    print(f"✅ Saved labels to {labels_file}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--num-total", type=int, default=800, help="Total conversations to generate")
    parser.add_argument("--coherent-ratio", type=float, default=0.5, help="Fraction that stay on-topic")
    parser.add_argument("--min-turns", type=int, default=6, help="Minimum turns per conversation (even)")
    parser.add_argument("--max-turns", type=int, default=12, help="Maximum turns per conversation (even)")
    parser.add_argument("--output-dir", default="data", help="Output directory")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()
    
    conversations = generate_conversations(
        args.num_total,
        args.coherent_ratio,
        args.min_turns,
        args.max_turns,
        args.seed,
    )
    
    save_conversations(conversations, args.output_dir)
    print(f"\nDone! Generated {len(conversations)} conversations in {args.output_dir}/")


if __name__ == "__main__":
    main()
