# Streamlit Cloud Deployment Guide

## Quick Start: Deploy to Streamlit Cloud (5 minutes)

### Step 1: Set Up Free PostgreSQL Database

Choose one (all are free):

#### Option A: Supabase (Recommended - Easiest)
1. Go to https://supabase.com
2. Sign up (free tier includes 500MB)
3. Create a new project
4. Go to Settings → Database
5. Copy the connection string:
   ```
   postgresql://postgres:[password]@[host]:[port]/postgres
   ```

#### Option B: Railway
1. Go to https://railway.app
2. Sign up with GitHub
3. Create new project → PostgreSQL
4. Copy the database URL from the dashboard

#### Option C: Render
1. Go to https://render.com
2. Sign up with GitHub
3. Create new PostgreSQL database (free tier)
4. Copy the external connection string

---

### Step 2: Deploy to Streamlit Cloud

1. Go to https://share.streamlit.io
2. Click **"New app"**
3. Connect your GitHub account (authorize once)
4. Select:
   - **Repository:** mani9866/LLM-Drift-Monitor
   - **Branch:** main
   - **Main file path:** `dashboard/app.py`
5. Click **"Deploy"**

---

### Step 3: Add Secrets to Streamlit Cloud

1. Your app will deploy (may show errors initially - that's OK)
2. Click the **☰ menu** (hamburger) in top-right of your Streamlit app
3. Select **Settings**
4. Click **Secrets**
5. Paste your database credentials:
   ```toml
   database_url = "postgresql://user:password@host:5432/dbname"
   slack_webhook_url = ""  # optional
   anthropic_api_key = ""  # optional
   drift_threshold = 0.5
   ```
6. Click **Save**
7. Your app will auto-refresh

---

### Step 4: Initialize Database

The first time, you need to create the database schema:

```bash
# Locally (with DATABASE_URL set to your Streamlit cloud DB):
export DATABASE_URL="your_postgresql_url"
python -c "from src.database import init_db; init_db()"
```

Or add sample data:

```bash
python scripts/ingest_conversations.py --data-dir data
```

---

## Your Deployed Dashboard URL

Once deployed, your dashboard will be live at:
```
https://[your-streamlit-cloud-username]-llm-drift-monitor.streamlit.app
```

---

## Troubleshooting

### "No module named 'src'"
- Streamlit Cloud runs from repo root ✓
- The path insert in `dashboard/app.py` handles this

### "Connection refused - PostgreSQL"
- Check DATABASE_URL in Secrets
- Ensure your PostgreSQL allows external connections
- For Supabase/Railway/Render: this is enabled by default

### "ImportError: sentence_transformers"
- This will auto-install from `requirements.txt`
- First deploy may take 2-3 minutes

### "No data showing"
- You need to populate the database with conversations
- Run `scripts/ingest_conversations.py` locally
- Or generate data: `python scripts/generate_conversations.py --num-total 100`

---

## Environment Variables

All config loads from:
1. `.streamlit/secrets.toml` (local dev)
2. Streamlit Cloud Secrets dashboard (production)

Key variables:
- `database_url`: PostgreSQL connection (required)
- `slack_webhook_url`: Slack alerts (optional)
- `anthropic_api_key`: Data generation (optional)
- `drift_threshold`: Default detection threshold (0.5)

---

## Free Tier Limits

| Service | Limit | Cost After |
|---------|-------|------------|
| Streamlit Cloud | Unlimited usage | Free tier only |
| Supabase PostgreSQL | 500 MB storage | $25/mo after |
| Railway PostgreSQL | $5/mo credits | $5/mo |
| Render PostgreSQL | 90 days free | $15/mo |

**Total cost: $0 forever** (if using Supabase free tier)

---

## Next Steps

1. Deploy dashboard ✓
2. Add PostgreSQL database ✓
3. Configure Secrets in Streamlit Cloud ✓
4. Populate with sample data (optional)
5. Share your dashboard URL!

Your app is now live and accessible anywhere! 🚀
