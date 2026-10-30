"""Load local development settings without replacing server environment values."""
import os
import re
from pathlib import Path


def load_env_file(path=None, environ=None):
    environ = os.environ if environ is None else environ
    if environ.get('SCHOOL_AGENT_LOAD_DOTENV', '1') == '0':
        return []
    source = Path(path) if path is not None else Path(__file__).resolve().parents[1] / '.env'
    if not source.is_file():
        return []
    loaded = []
    for raw in source.read_text(encoding='utf-8-sig').splitlines():
        line = raw.strip()
        if line.startswith('export '):
            line = line[7:].lstrip()
        key, separator, value = line.partition('=')
        key, value = key.strip(), value.strip()
        if not separator or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        else:
            value = re.split(r'\s+#', value, maxsplit=1)[0].rstrip()
        if key not in environ and value:
            environ[key] = value
            loaded.append(key)
    return loaded
