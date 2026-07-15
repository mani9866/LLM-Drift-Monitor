.PHONY: help install dev docker docker-down setup ingest-data eval test clean

help:
	@echo "LLM Drift Monitor - Common Commands"
	@echo "===================================="
	@echo ""
	@echo "Setup & Installation:"
	@echo "  make install          - Install dependencies in .venv"
	@echo "  make setup            - Initialize database"
	@echo "  make docker           - Start all services with Docker Compose"
	@echo "  make docker-down      - Stop Docker Compose services"
	@echo ""
	@echo "Development:"
	@echo "  make dev              - Run API in development mode"
	@echo "  make dashboard        - Run Streamlit dashboard"
	@echo "  make flow             - Run Prefect flow scheduler"
	@echo ""
	@echo "Data:"
	@echo "  make gen-data         - Generate synthetic conversations (800)"
	@echo "  make ingest-data      - Ingest conversations into database"
	@echo "  make eval             - Run evaluation and generate metrics"
	@echo ""
	@echo "Testing:"
	@echo "  make test             - Run pytest (if configured)"
	@echo "  make clean            - Remove cache and temp files"
	@echo ""

install:
	python -m venv .venv
	. .venv/bin/activate && pip install -r requirements.txt

dev:
	. .venv/bin/activate && uvicorn src.api.app:app --reload --port 8000

setup:
	. .venv/bin/activate && python -c "from src.database import init_db; init_db()"

dashboard:
	. .venv/bin/activate && streamlit run dashboard/app.py

flow:
	. .venv/bin/activate && python -m src.flows

docker:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

gen-data:
	. .venv/bin/activate && python scripts/generate_conversations.py --num-total 800

ingest-data:
	. .venv/bin/activate && python scripts/ingest_conversations.py --data-dir data

eval:
	. .venv/bin/activate && python -m src.evaluation --data-dir data --output-dir evaluation_results

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	find . -type f -name '.DS_Store' -delete
	rm -rf .pytest_cache .venv/

.env:
	cp .env.example .env
	@echo "✅ Created .env file - please edit with your settings"

init: install .env setup
	@echo "✅ Initialization complete!"
	@echo "Run 'make docker' to start services"
