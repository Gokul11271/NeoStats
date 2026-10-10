import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

def get_config_var(key: str, default: str = "") -> str:
    """Helper to fetch config from environment or st.secrets (for Streamlit Cloud deployment)."""
    val = os.getenv(key)
    if val:
        return val
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return default

# LLM Configurations
NEOSTATS_OPENAI_BASE_URL = get_config_var(
    "NEOSTATS_OPENAI_BASE_URL",
    "https://neo-hackathon.services.ai.azure.com/openai/v1/"
)
NEOSTATS_OPENAI_API_KEY = get_config_var("NEOSTATS_OPENAI_API_KEY", "")
NEOSTATS_OPENAI_MODEL = get_config_var("NEOSTATS_OPENAI_MODEL", "Neo-Hackathon")

# Data & Document Paths
RIDEWISE_DB_PATH = Path(get_config_var("RIDEWISE_DB_PATH", str(BASE_DIR / "Requirements" / "ridewise.db")))
if not RIDEWISE_DB_PATH.is_absolute():
    RIDEWISE_DB_PATH = BASE_DIR / RIDEWISE_DB_PATH

DOCS_DIR = Path(get_config_var("DOCS_DIR", str(BASE_DIR / "Requirements")))
if not DOCS_DIR.is_absolute():
    DOCS_DIR = BASE_DIR / DOCS_DIR

# Request timeout and retries
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))

# Cutoff Timestamp for Cancellation Policy Version 2 (1 July 2026 00:00 IST == 2026-06-30 18:30:00 UTC)
POLICY_V2_CUTOFF_UTC = "2026-06-30 18:30:00"
