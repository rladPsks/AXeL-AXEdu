"""Isolated fictional browser-test server. Never exposes session credentials over HTTP."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.seed import seed
from backend.main import create_app
import uvicorn

# Caller supplies a new directory so no existing database is erased.
directory = Path(sys.argv[1])
directory.mkdir(parents=True, exist_ok=False)
path = directory / 'test.sqlite3'
credentials = seed(path)
(directory / 'credentials.json').write_text(json.dumps(credentials), encoding='utf-8')
uvicorn.run(create_app(path), host='127.0.0.1', port=8000, log_level='warning')
