from pathlib import Path
import os
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
DB_PATH = ROOT_DIR / "axel_demo.sqlite3"
load_dotenv(ROOT_DIR / ".env")
LLM_API_KEY = (os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
LLM_MODEL = (os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "").strip()
LLM_BASE_URL = (os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").strip()
# Demo parameters only; confirm with school before operational use.
REPEAT_WINDOW_DAYS = 90
REPEAT_REVIEW_COUNT = 3
LOW_CONFIDENCE_THRESHOLD = 0.60
