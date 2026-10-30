"""Optional local `.env` loader (stdlib only).

Values already present in the real environment always win, so Render/Vercel
settings and PowerShell `$env:` overrides are never replaced by a stray file.
Set SCHOOL_AGENT_LOAD_DOTENV=0 to disable (the test suite does this).
"""
import os
from pathlib import Path


def load_env_file(path='.env', environ=None):
    environ = os.environ if environ is None else environ
    if environ.get('SCHOOL_AGENT_LOAD_DOTENV', '1') == '0':
        return []
    file = Path(path)
    if not file.is_file():
        return []
    loaded = []
    for raw in file.read_text(encoding='utf-8-sig').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        key, value = key.strip(), value.strip()
        if not key.replace('_', '').isalnum() or key[0].isdigit():
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
            value = value[1:-1]
        if key in environ or value == '':
            continue  # real environment wins; empty placeholders stay unset
        environ[key] = value
        loaded.append(key)
    return loaded
