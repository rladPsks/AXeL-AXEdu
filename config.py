from pathlib import Path
import os

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
DB_PATH = ROOT_DIR / "axel_demo.sqlite3"
def llm_settings():
    # Read after create_app loads .env; never cache credentials at import time.
    return (
        (os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip(),
        (os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "").strip(),
        (os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").strip(),
    )
# Demo parameters only; confirm with school before operational use.
REPEAT_WINDOW_DAYS = 90
REPEAT_REVIEW_COUNT = 3
LOW_CONFIDENCE_THRESHOLD = 0.60
