"""Quick demo of drift detection without full evaluation."""
import json
import sys
from pathlib import Path

# Windows terminals default to a non-UTF-8 codepage (e.g. cp1252), which
# raises UnicodeEncodeError on the emoji in this script's print() calls.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.detectors import compute_all_scores

def demo():
    """Run a quick demo on a few sample conversations."""
    
    # Load a few conversations
    conversations_file = Path("data/conversations.jsonl")
    with open(conversations_file) as f:
        conversations = [json.loads(line) for line in f][:5]  # First 5 only
    
    print("=" * 70)
    print("🔍 LLM Drift Monitor - Quick Demo")
    print("=" * 70)
    print()
    
    for conv in conversations:
        print(f"Conversation: {conv['id']}")
        print(f"  Ground truth: {'DRIFTED' if conv['is_drifted'] else 'COHERENT'}")
        print(f"  Turns: {conv['num_turns']}")
        
        if conv['is_drifted']:
            print(f"  Drift at turn: {conv['drift_turn_index']}")
            print(f"  Topic A: {conv['topic_a']}")
            print(f"  Topic B: {conv['topic_b']}")
        else:
            print(f"  Topic: {conv['topic_a']}")
        
        # Compute scores
        try:
            scores = compute_all_scores(conv)
            
            print(f"\n  📊 Detector Scores:")
            print(f"    • Semantic drift:        {scores['semantic_drift']:.3f}")
            print(f"    • Rolling window drift:  {scores['rolling_window_drift']:.3f}")
            print(f"      → Detected at turn:    {scores['rolling_window_drift_index']}")
            print(f"    • Response anomaly:      {scores['response_anomaly']:.3f}")
            print(f"    • Ensemble (weighted):   {scores['ensemble_score']:.3f}")
            
            # Prediction
            threshold = 0.50
            predicted = "DRIFTED" if scores['ensemble_score'] >= threshold else "COHERENT"
            actual = "DRIFTED" if conv['is_drifted'] else "COHERENT"
            match = "✅" if predicted == actual else "❌"
            
            print(f"\n  Prediction (threshold={threshold}): {predicted} {match}")
        
        except Exception as e:
            print(f"  ❌ Error: {e}")
        
        print()

if __name__ == "__main__":
    demo()
