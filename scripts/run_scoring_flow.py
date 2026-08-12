"""One-shot entry point for src.flows.score_conversations_flow.

Unlike `python -m src.flows` (which calls `.serve()` and blocks forever
running its own scheduler), this runs the flow exactly once and exits -
intended to be invoked by an external scheduler (e.g. the GitHub Actions
cron workflow in .github/workflows/score-and-alert.yml) against a
Streamlit-Cloud-hosted app's database, since Streamlit Cloud itself has no
way to run background/scheduled jobs.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.flows import score_conversations_flow

if __name__ == "__main__":
    result = score_conversations_flow()
    print(result)
