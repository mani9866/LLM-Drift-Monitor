import argparse
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Quick-start helper for the LLM drift monitor")
    parser.add_argument("--skip-install", action="store_true", help="Skip dependency installation")
    parser.add_argument("--skip-db", action="store_true", help="Skip database initialization")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    python = sys.executable

    if not args.skip_install:
        subprocess.check_call([python, "-m", "pip", "install", "-r", str(root / "requirements.txt")])

    if not args.skip_db:
        subprocess.check_call([python, "-c", "from src.database import init_db; init_db()"], cwd=root)

    print("Quickstart complete. Use one of the following:")
    print("  python -m uvicorn src.api.app:app --reload --port 8000")
    print("  streamlit run dashboard/app.py")


if __name__ == "__main__":
    main()
