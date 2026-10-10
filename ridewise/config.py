import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# LLM Configurations
NEOSTATS_OPENAI_BASE_URL = os.getenv(
    "NEOSTATS_OPENAI_BASE_URL",
    "https://neo-hackathon.services.ai.azure.com/openai/v1/"
)
NEOSTATS_OPENAI_API_KEY = os.getenv("NEOSTATS_OPENAI_API_KEY", "")
NEOSTATS_OPENAI_MODEL = os.getenv("NEOSTATS_OPENAI_MODEL", "Neo-Hackathon")

# Data & Document Paths
RIDEWISE_DB_PATH = Path(os.getenv("RIDEWISE_DB_PATH", BASE_DIR / "Requirements" / "ridewise.db"))
if not RIDEWISE_DB_PATH.is_absolute():
    RIDEWISE_DB_PATH = BASE_DIR / RIDEWISE_DB_PATH

DOCS_DIR = Path(os.getenv("DOCS_DIR", BASE_DIR / "Requirements"))
if not DOCS_DIR.is_absolute():
    DOCS_DIR = BASE_DIR / DOCS_DIR

# Request timeout and retries
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))

# Cutoff Timestamp for Cancellation Policy Version 2 (1 July 2026 00:00 IST == 2026-06-30 18:30:00 UTC)
POLICY_V2_CUTOFF_UTC = "2026-06-30 18:30:00"
