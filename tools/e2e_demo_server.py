"""Disposable Render-like demo server: auto seed, public fictional login, no model calls."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.agents import Registry
from backend.main import create_app
import uvicorn

directory = Path(sys.argv[1])
directory.mkdir(parents=True, exist_ok=False)
os.environ['SCHOOL_AGENT_AUTO_SEED'] = '1'
os.environ['SCHOOL_AGENT_DEMO'] = '1'
os.environ['SCHOOL_AGENT_RUN_WORKER'] = '1'
uvicorn.run(create_app(directory / 'demo.sqlite3', agent_registry=Registry()), host='127.0.0.1', port=8000, log_level='warning')
