"""Main entry point for evaluation module."""
from . import evaluate
import sys
from pathlib import Path

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data", help="Directory with conversations.jsonl and labels.csv")
    parser.add_argument("--output-dir", default="evaluation_results", help="Output directory for results")
    args = parser.parse_args()

    evaluate(args.data_dir, args.output_dir)
