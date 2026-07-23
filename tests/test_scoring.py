import unittest

from src.flows.scoring import score_conversation_payload


class ScoringFlowTests(unittest.TestCase):
    def test_score_conversation_payload_returns_metrics(self):
        conversation = {
            "id": "conv_test_001",
            "turns": [
                {"role": "user", "content": "Can you help me plan a trip to Japan?"},
                {"role": "assistant", "content": "Absolutely, I can help you plan your itinerary."},
                {"role": "user", "content": "What are the best neighborhoods to stay in?"},
                {"role": "assistant", "content": "Tokyo and Kyoto are excellent starting points for first-time visitors."},
                {"role": "user", "content": "I also want to know about local food."},
                {"role": "assistant", "content": "You should try ramen, sushi, and tempura while you are there."},
            ],
        }

        result = score_conversation_payload(conversation)

        self.assertIn("semantic_drift", result)
        self.assertIn("rolling_window_drift", result)
        self.assertIn("ensemble_score", result)
        self.assertIn("drift_detected", result)
        self.assertGreaterEqual(result["ensemble_score"], 0.0)
        self.assertLessEqual(result["ensemble_score"], 1.0)

    def test_score_conversation_payload_handles_short_conversation(self):
        conversation = {
            "id": "conv_short_001",
            "turns": [
                {"role": "user", "content": "Hello there"},
                {"role": "assistant", "content": "Hi!"},
            ],
        }

        result = score_conversation_payload(conversation)

        self.assertEqual(result["rolling_window_drift_index"], -1)
        self.assertFalse(result["drift_detected"])


if __name__ == "__main__":
    unittest.main()
