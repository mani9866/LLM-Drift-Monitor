#!/bin/bash
# LLM Drift Monitor Quick Start Script

set -e

echo "🔍 LLM Drift Monitor - Quick Start"
echo "==================================="
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from template..."
    cp .env.example .env
    echo "✅ Created .env - please edit with your settings"
    echo ""
fi

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.11+"
    exit 1
fi

# Check for Docker
if ! command -v docker &> /dev/null; then
    echo "⚠️  Docker not found. Will run services manually instead."
    DOCKER_AVAILABLE=false
else
    DOCKER_AVAILABLE=true
fi

# Choose deployment method
echo "Choose deployment method:"
echo "1) Docker Compose (recommended)"
echo "2) Manual (development)"
read -p "Enter 1 or 2: " DEPLOY_METHOD

if [ "$DEPLOY_METHOD" == "1" ]; then
    if [ "$DOCKER_AVAILABLE" = false ]; then
        echo "❌ Docker not found but you selected Docker deployment."
        echo "Please install Docker: https://docs.docker.com/get-docker/"
        exit 1
    fi

    echo ""
    echo "🐳 Starting services with Docker Compose..."
    docker-compose up -d

    echo ""
    echo "✅ Services starting:"
    echo "   - API: http://localhost:8000 (docs at /docs)"
    echo "   - Dashboard: http://localhost:8501"
    echo "   - Database: localhost:5432"
    echo ""
    echo "Run: docker-compose logs -f   # to see logs"
    echo "Run: docker-compose down      # to stop"

else
    echo ""
    echo "📦 Setting up Python environment..."

    # Create venv if needed
    if [ ! -d .venv ]; then
        python3 -m venv .venv
    fi

    source .venv/bin/activate

    # Install dependencies
    pip install -q -r requirements.txt

    # Initialize database
    echo "📊 Initializing database..."
    python3 -c "from src.database import init_db; init_db()"

    echo ""
    echo "✅ Environment ready. Start services in separate terminals:"
    echo ""
    echo "   Terminal 1 (API):"
    echo "   uvicorn src.api.app:app --reload --port 8000"
    echo ""
    echo "   Terminal 2 (Prefect flow):"
    echo "   python -m src.flows"
    echo ""
    echo "   Terminal 3 (Streamlit dashboard):"
    echo "   streamlit run dashboard/app.py"
    echo ""
fi

echo ""
echo "📖 Next steps:"
echo "   1. Generate data: python scripts/generate_conversations.py --num-total 100"
echo "   2. Ingest data:  python scripts/ingest_conversations.py"
echo "   3. Run evaluation: python -m src.evaluation"
echo "   4. Open dashboard: http://localhost:8501"
echo ""
echo "See README.md for full documentation."
