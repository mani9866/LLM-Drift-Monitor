@echo off
REM LLM Drift Monitor Quick Start for Windows

echo 🔍 LLM Drift Monitor - Quick Start
echo ===================================
echo.

REM Check if .env exists
if not exist .env (
    echo ⚠️  .env file not found. Creating from template...
    copy .env.example .env
    echo ✅ Created .env - please edit with your settings
    echo.
)

REM Check for Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python not found. Please install Python 3.11+
    exit /b 1
)

REM Check for Docker
docker --version >nul 2>&1
if errorlevel 1 (
    echo ⚠️  Docker not found. Will run services manually instead.
    set DOCKER_AVAILABLE=false
) else (
    set DOCKER_AVAILABLE=true
)

REM Choose deployment method
echo Choose deployment method:
echo 1) Docker Compose (recommended)
echo 2) Manual (development)
set /p DEPLOY_METHOD="Enter 1 or 2: "

if "%DEPLOY_METHOD%"=="1" (
    if "%DOCKER_AVAILABLE%"=="false" (
        echo ❌ Docker not found but you selected Docker deployment.
        echo Please install Docker: https://docs.docker.com/get-docker/
        exit /b 1
    )

    echo.
    echo 🐳 Starting services with Docker Compose...
    docker-compose up -d

    echo.
    echo ✅ Services starting:
    echo    - API: http://localhost:8000 (docs at /docs)
    echo    - Dashboard: http://localhost:8501
    echo    - Database: localhost:5432
    echo.
    echo Run: docker-compose logs -f   # to see logs
    echo Run: docker-compose down      # to stop

) else (
    echo.
    echo 📦 Setting up Python environment...

    REM Create venv if needed
    if not exist .venv (
        python -m venv .venv
    )

    call .venv\Scripts\activate.bat

    REM Install dependencies
    pip install -q -r requirements.txt

    REM Initialize database
    echo 📊 Initializing database...
    python -c "from src.database import init_db; init_db()"

    echo.
    echo ✅ Environment ready. Start services in separate terminals:
    echo.
    echo    Terminal 1 (API):
    echo    uvicorn src.api.app:app --reload --port 8000
    echo.
    echo    Terminal 2 (Prefect flow):
    echo    python -m src.flows
    echo.
    echo    Terminal 3 (Streamlit dashboard):
    echo    streamlit run dashboard\app.py
    echo.
)

echo.
echo 📖 Next steps:
echo    1. Generate data: python scripts\generate_conversations.py --num-total 100
echo    2. Ingest data:  python scripts\ingest_conversations.py
echo    3. Run evaluation: python -m src.evaluation
echo    4. Open dashboard: http://localhost:8501
echo.
echo See README.md for full documentation.
