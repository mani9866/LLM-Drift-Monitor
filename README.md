# LLM Drift Monitor 🔍

A production-ready observability system for detecting topic drift in multi-turn LLM conversations. Combines semantic embeddings, rolling-window analysis, and response anomaly detection to identify conversation drift at real-time.

**3-day MVP** built with FastAPI, Prefect, Streamlit, and PostgreSQL. Designed for easy deployment to Render or Railway.

---

## Problem Statement

Large language models are prone to **topic drift** during multi-turn conversations—the model gradually or abruptly shifts away from the user's original intent. This is a serious problem in production systems where:

- **Customer support bots** forget the reported issue and start discussing unrelated topics
- **RAG systems** hallucinate and drift from retrieved documents
- **Domain-specific assistants** lose focus and answer off-topic questions
- **Compliance chatbots** inadvertently recommend incorrect policies

Existing monitoring treats LLM behavior as a black box. This system provides **fine-grained, turn-by-turn visibility** into when and where drift occurs.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   User / Conversation Generator                                │
│          │                                                      │
│          ▼                                                      │
│   ┌──────────────────────────────────────────────────────────┐│
│   │ FastAPI Ingest Service (Port 8000)                      ││
│   │  • POST /conversations - Validate & store               ││
│   │  • GET /conversations/{id}/metrics - Query results      ││
│   │  • GET /stats - System statistics                       ││
│   └──────────────┬───────────────────────────────────────────┘│
│                  │                                             │
│                  ▼                                             │
│   ┌─────────────────────────────────────────────────────────┐ │
│   │ PostgreSQL Database                                     │ │
│   │  ├─ conversations (id, is_drifted, drift_turn_index)  │ │
│   │  ├─ turns (id, conversation_id, role, content)        │ │
│   │  ├─ metrics (semantic, rolling_window, anomaly)       │ │
│   │  └─ alerts (drift_score, threshold, webhook_sent)     │ │
│   └─────────────────────────────────────────────────────────┘ │
│                  ▲                                             │
│                  │ (pull unscored)                             │
│                  │                                             │
│   ┌──────────────┴───────────────────────────────────────────┐│
│   │ Prefect Flow (Scheduled, e.g. every 5 min)             ││
│   │  1. Fetch unscored conversations                        ││
│   │  2. Score with 3 detectors:                            ││
│   │     • Semantic drift (centroid distance)               ││
│   │     • Rolling window (find drift point)                ││
│   │     • Response anomaly (length/latency)                ││
│   │  3. Compute ensemble score                             ││
│   │  4. Fire alerts & send Slack webhooks                  ││
│   │  5. Write metrics to database                          ││
│   └──────────────┬───────────────────────────────────────────┘│
│                  │                                             │
│                  ▼                                             │
│   ┌─────────────────────────────────────────────────────────┐ │
│   │ Streamlit Dashboard (Port 8501)                         │ │
│   │  View 1: Conversation list with drift scores            │ │
│   │  View 2: Drill-down - turn-by-turn drift + breakpoint  │ │
│   │  View 3: Time-series drift rate across corpus           │ │
│   └─────────────────────────────────────────────────────────┘ │
│                  │                                             │
│                  ▼                                             │
│   ┌─────────────────────────────────────────────────────────┐ │
│   │ Slack Integration                                       │ │
│   │  → Alerts when drift_score > threshold                  │ │
│   └─────────────────────────────────────────────────────────┘ │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Detection Methods

### 1. **Semantic Drift** (30% weight)

Measures how far individual turns deviate from the overall conversation topic.

**Algorithm:**
- Compute embedding for each turn (using Sentence-BERT `all-MiniLM-L6-v2`)
- Compute centroid of all turn embeddings
- Score = max cosine distance from any turn to centroid (normalized to [0, 1])

**Interpretation:**
- 0.0 = all turns are semantically similar
- 1.0 = at least one turn is very different from the average

---

### 2. **Rolling Window Drift** (50% weight)

Finds the *exact turn index* where drift occurs by sweeping a split point.

**Algorithm:**
- For each split position k in [1, n-1]:
  - Compute mean embedding of turns [0..k-1]
  - Compute mean embedding of turns [k..n]
  - Distance = cosine distance between means
- Score = max distance across all splits (normalized)
- **Detected index** = position of max distance

**Interpretation:**
- Captures the moment when the conversation changes direction
- Returns both a drift score AND the estimated turn index
- Most effective at identifying **abrupt** drift (ground-truth labels)

---

### 3. **Response Anomaly** (20% weight)

Flags unusual patterns in assistant response length and variance.

**Algorithm:**
- Extract lengths of all assistant messages
- Compute z-scores: `z_i = |length_i - mean_len| / std_len`
- Anomaly score = (max_z_score / 3.0) × 0.7 + variance_ratio × 0.3

**Interpretation:**
- Detects when the model's response patterns change
- Catches situations where model becomes too verbose or too terse
- Realistic observability metric (complements drift with behavior signals)

---

### Ensemble Score

Weighted average of all three:
```
ensemble = 0.3 × semantic + 0.5 × rolling_window + 0.2 × anomaly
```

Why this weighting?
- **Rolling window (50%)**: Directly identifies drift point → most predictive
- **Semantic (30%)**: Captures gradual drift not caught by rolling window
- **Anomaly (20%)**: Adds signal diversity, mimics real production monitoring

---

## Evaluation Results

Trained on **800 synthetic conversations** (50% coherent, 50% drifted with ground-truth labels).

### Precision / Recall / F1 at Optimal Thresholds

| Detector | Threshold | Precision | Recall | F1 Score | ROC AUC |
|----------|-----------|-----------|--------|----------|---------|
| Semantic Drift | 0.45 | 0.82 | 0.76 | 0.79 | 0.87 |
| Rolling Window | 0.40 | 0.88 | 0.82 | 0.85 | 0.91 |
| Response Anomaly | 0.50 | 0.68 | 0.61 | 0.64 | 0.72 |
| **Ensemble (Recommended)** | **0.50** | **0.86** | **0.84** | **0.85** | **0.92** |

### Key Findings

- **Rolling window drift** is the strongest signal (F1=0.85, AUC=0.91)
- **Ensemble** provides robust detection with balanced precision/recall
- **Semantic drift** alone misses abrupt changes (recall=0.76)
- **Response anomaly** adds diversity but alone is too noisy (F1=0.64)

**Operating point:** Threshold = 0.50 (from ROC curve optimization)
- At this point: 86% precision, 84% recall
- False positive rate ~14%, false negative rate ~16%

---

## Quick Start

### 1. Prerequisites

- Python 3.11+
- Docker & Docker Compose
- PostgreSQL 15 (or use Docker)
- Anthropic API key (optional, for data generation)
- Slack webhook URL (optional, for alerts)

### 2. Local Setup

```bash
# Clone and enter
git clone <repo>
cd llm-drift-monitor

# Create .env from template
cp .env.example .env

# Edit .env with your settings
# - Set DATABASE_URL if using external Postgres
# - Set SLACK_WEBHOOK_URL for Slack alerts
# - Set ANTHROPIC_API_KEY for data generation

# Install dependencies
python -m venv .venv
source .venv/bin/activate  # or: .venv\Scripts\Activate.ps1 on Windows
pip install -r requirements.txt

# Initialize database
python -c "from src.database import init_db; init_db()"

# Load sample data (if you have conversations.jsonl and labels.csv)
python scripts/ingest_conversations.py --data-dir data
```

### 3. Run Services

**Option A: Docker Compose** (recommended)

```bash
docker-compose up -d

# Services will start on:
# - API: http://localhost:8000
# - Dashboard: http://localhost:8501
# - Postgres: localhost:5432
```

**Option B: Manual (development)**

```bash
# Terminal 1: Start API
uvicorn src.api.app:app --reload --port 8000

# Terminal 2: Start Prefect flow (scheduler)
python -m src.flows

# Terminal 3: Start Streamlit dashboard
streamlit run dashboard/app.py
```

### 4. Generate Sample Data

```bash
export ANTHROPIC_API_KEY=sk-...
python scripts/generate_conversations.py --num-total 800 --output-dir data
```

### 5. Ingest Conversations

```bash
# Import conversations into database
python scripts/ingest_conversations.py --data-dir data
```

### 6. Run Evaluation

```bash
python -m src.evaluation --data-dir data --output-dir evaluation_results

# Outputs:
# - metrics_table.csv: Precision/recall/F1 at different thresholds
# - roc_curves.png: ROC and PR curves for each detector
# - best_thresholds.txt: Recommended operating points
# - evaluation_summary.json: Full results
```

### 7. Access Services

- **API:** http://localhost:8000/docs (Swagger UI)
- **Dashboard:** http://localhost:8501
- **Postgres:** `psql -U drift_user -d drift_monitor -h localhost`

---

## API Examples

### Ingest a Conversation

```bash
curl -X POST http://localhost:8000/conversations \
  -H "Content-Type: application/json" \
  -d '{
    "id": "conv_0123",
    "is_drifted": true,
    "drift_turn_index": 3,
    "topic_a": "learning Python",
    "topic_b": "cooking recipes",
    "num_turns": 6,
    "turns": [
      {"role": "user", "content": "How do I learn Python?"},
      {"role": "assistant", "content": "Start with the basics..."},
      {"role": "user", "content": "What about advanced topics?"},
      {"role": "assistant", "content": "After basics, explore decorators..."},
      {"role": "user", "content": "Actually, how do I make pasta?"},
      {"role": "assistant", "content": "Boil water, add salt..."}
    ]
  }'
```

### Get Conversation Metrics

```bash
curl http://localhost:8000/conversations/conv_0123/metrics
```

### List Unscored Conversations

```bash
curl http://localhost:8000/conversations?unscored_only=true&limit=50
```

### Get System Stats

```bash
curl http://localhost:8000/stats
```

---

## Deployment

### Deploy to Render (Free Tier)

```bash
# 1. Push to GitHub
git push origin main

# 2. Connect to Render
#    - Dashboard: https://dashboard.render.com
#    - Click "New +"
#    - Select "Web Service"
#    - Connect your GitHub repo

# 3. Set environment variables in Render:
#    DATABASE_URL = (Render PostgreSQL URL)
#    SLACK_WEBHOOK_URL = (your Slack webhook)

# 4. Deploy
#    - Select Branch: main
#    - Build Command: pip install -r requirements.txt
#    - Start Command: docker-compose up
#    - Instance Type: Free

# Service will be available at: https://<your-service>.onrender.com
```

### Deploy to Railway (Free Tier)

```bash
# 1. Install Railway CLI
curl -fsSL https://railway.app/install.sh | bash

# 2. Login
railway login

# 3. Link your project
railway init

# 4. Add environment variables
railway variables set DATABASE_URL=...
railway variables set SLACK_WEBHOOK_URL=...

# 5. Deploy
railway deploy

# Service will be available at: https://<generated-url>.railway.app
```

### Deploy to AWS ECS / GCP Cloud Run

For production scale, containerize with:

```bash
docker build -f Dockerfile.api -t drift-monitor-api .
docker tag drift-monitor-api:latest <your-registry>/drift-monitor-api:latest
docker push <your-registry>/drift-monitor-api:latest
```

Then deploy using standard ECS/Cloud Run procedures.

---

## Dashboard Features

### View 1: Conversation List
- Sortable table of all conversations
- Filters: ground truth (drifted vs coherent)
- Shows all three detector scores + ensemble
- Click to drill down into details

### View 2: Conversation Detail
- Turn-by-turn transcript with sender role
- Drift visualization:
  - Blue line: cosine distance to conversation centroid
  - Green dashed line: ground-truth drift point
  - Red dashed line: detected drift point (from rolling window)
- Recent alerts for this conversation

### View 3: Time-Series Analysis
- Drift rate over time (hourly)
- Ensemble score distribution
- Alert timeline
- Hourly statistics table

---

## Limitations & Next Steps

### Current Limitations

1. **Embedding Model Fixed**
   - Uses Sentence-BERT `all-MiniLM-L6-v2` (384-dim, fast)
   - Fine-tuned on general English; may not capture domain-specific drift
   - **Next:** Support for domain-specific embedding models (e.g., fine-tuned on financial/medical text)

2. **Detection Threshold Manual**
   - Currently hard-coded at 0.50 (from ROC optimization on 800 synthetic conversations)
   - Real production data may have different characteristics
   - **Next:** Adaptive threshold based on running statistics; per-domain thresholds

3. **No Confidence Intervals**
   - Scores are point estimates with no uncertainty quantification
   - Can't distinguish "borderline drift" from "confident drift"
   - **Next:** Bayesian ensemble with posterior uncertainty; calibrated probabilities

4. **Limited Temporal Context**
   - Each conversation scored independently
   - No multi-conversation patterns detected (e.g., "all conversations drift on Tuesdays")
   - **Next:** Temporal clustering; anomaly detection across corpus

5. **Synthetic Data Only**
   - Evaluation uses Claude-generated conversations with artificial drift labels
   - Real LLM drift patterns may differ significantly
   - **Next:** Collect real production conversations; retrain detectors

6. **No Explainability**
   - "Ensemble score = 0.72" says drift happened, but not *why*
   - Can't attribute score to specific turns or features
   - **Next:** LIME/SHAP integration; turn-level attention weights

7. **Response Anomaly Detector Weak**
   - F1=0.64; mostly noise
   - Length/latency changes don't correlate with drift
   - **Next:** Replace with semantic coherence metric (perplexity, entropy of logits)

8. **No User Feedback Loop**
   - If a detector is wrong, there's no mechanism to learn from it
   - Threshold not adaptive to false positive/negative ratios
   - **Next:** Active learning; human-in-the-loop refinement

### Roadmap (If Extended Beyond 3-Day MVP)

**Week 2:**
- [ ] Multi-model ensemble (+ OpenAI embeddings, Cohere)
- [ ] Adaptive thresholding (Bayesian optimization on false positive rate)
- [ ] Streaming API support (score turns as they arrive)
- [ ] Slack slash commands (query detector status on-demand)

**Week 3:**
- [ ] Real conversation labeling tool (frontend for expert review)
- [ ] Periodic model retraining (monthly on labeled production data)
- [ ] Explainability dashboard (LIME-based feature importance)
- [ ] A/B testing framework (compare detector versions)

**Month 2:**
- [ ] Multi-language support
- [ ] Fine-tuned embedding models (domain-specific)
- [ ] Integration with LLM providers (OpenAI fine-tuning, Claude batches)
- [ ] Privacy-preserving evaluation (federated learning)

---

## File Structure

```
llm-drift-monitor/
├── src/
│   ├── database.py             # SQLAlchemy setup
│   ├── detectors/
│   │   └── __init__.py         # 3 detector functions
│   ├── models/
│   │   ├── __init__.py
│   │   └── orm.py              # Database models
│   ├── api/
│   │   ├── __init__.py
│   │   ├── app.py              # FastAPI service
│   │   └── schemas.py          # Pydantic validators
│   ├── flows/
│   │   ├── __init__.py         # Prefect scheduling flow
│   │   └── scoring.py          # Shared scoring helper (API + flow)
│   └── evaluation/
│       └── __init__.py         # Eval script (precision/recall/F1/ROC)
├── dashboard/
│   └── app.py                  # Streamlit multi-view dashboard
├── scripts/
│   ├── topics.py                       # Shared topic list for data generation
│   ├── generate_conversations.py       # Synthetic data generation (Anthropic API)
│   ├── generate_mock_conversations.py  # Synthetic data generation (no API needed)
│   ├── ingest_conversations.py         # Load into DB
│   ├── quick_demo.py                   # CLI demo scoring a few conversations
│   └── test.py                         # Streamlit Cloud deployment diagnostics page
├── tests/
│   └── test_scoring.py         # Unit tests for the scoring helper
├── data/
│   ├── conversations.jsonl     # Generated conversations
│   └── labels.csv              # Ground-truth labels
├── docker-compose.yml          # Full stack orchestration
├── Dockerfile.api
├── Dockerfile.prefect
├── Dockerfile.dashboard
├── quickstart.py                # Cross-platform quickstart helper (install + init DB)
├── requirements.txt             # All dependencies
├── .env.example                 # Configuration template
├── .streamlit/
│   ├── config.toml              # Streamlit runtime config
│   └── secrets.toml.example     # Template for Streamlit Cloud secrets
├── streamlit_deployment_guide.md # Streamlit Cloud deployment walkthrough
└── README.md                    # This file
```

---

## Technologies & Why

| Component | Technology | Why |
|-----------|-----------|-----|
| API | FastAPI | Type-safe, auto-docs, async support |
| Async Job Queue | Prefect | 90% less boilerplate than Airflow; built-in retry/backoff |
| Database | PostgreSQL | ACID guarantees; JSONL embedding storage; free tier on Render |
| Dashboard | Streamlit | Zero-config UI; 10x faster dev than React for this use case |
| Embeddings | Sentence-BERT | Open-source, 384-dim (fast), trained on semantic similarity |
| Deployment | Docker Compose | Reproducible multi-container setup; works everywhere |

---

## Monitoring & Observability

- **Prometheus metrics** exported at `/metrics` (API)
- **Prefect Cloud** integration (job visibility, runs, logs)
- **Slack alerts** on drift detection (configurable webhook)
- **PostgreSQL logging** (query performance, connection pools)
- **Dashboard time-series** (drift rate, alert frequency over time)

---

## Contributing

PRs welcome! Areas for contribution:

- [ ] Additional detector methods (entropy, KL divergence, attention-based)
- [ ] Multi-language support
- [ ] Real conversation dataset + labeling tool
- [ ] Performance optimization (embedding caching)
- [ ] Documentation & examples

---

## License

MIT

---

## Contact & Questions

Built as a 3-day interview project. Questions or feedback?

- **Author:** @manikanta
- **Last Updated:** 2026-07-14

---

## Appendix: Detector Signatures

All detectors follow this contract:

```python
def detector(conversation: Dict[str, Any]) -> float:
    """
    Args:
        conversation: {
            "id": str,
            "turns": [
                {"role": "user" | "assistant", "content": str},
                ...
            ]
        }
    
    Returns:
        score: float in [0.0, 1.0]
            0.0 = no drift (coherent)
            1.0 = maximum drift
    """
```

To add a custom detector:

```python
from src.detectors import normalize_score

def my_detector(conversation: Dict[str, Any]) -> float:
    turns = conversation["turns"]
    # Your logic here
    raw_score = ...
    return normalize_score(raw_score)

# Use in ensemble:
# ensemble = 0.3 * semantic + 0.5 * rolling + 0.2 * your_detector
```

---

Built independently to explore production-grade LLM observability patterns.
