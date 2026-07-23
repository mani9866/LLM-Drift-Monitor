"""Diagnostic page for debugging Streamlit Cloud deployment/DB resolution.

Run with: streamlit run scripts/test.py
"""
import os

import streamlit as st

st.write("Current working directory:", os.getcwd())
st.write("DB exists:", os.path.exists("drift_monitor.db"))
st.write("DATABASE_URL env var set:", "DATABASE_URL" in os.environ)
st.write(
    "Resolved DB backend:",
    "postgresql" if "postgresql" in os.environ.get("DATABASE_URL", "") else "sqlite (local fallback)",
)
