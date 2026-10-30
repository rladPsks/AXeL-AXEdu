"""Export the API contract without creating a persistent application database."""
import json
import tempfile
from pathlib import Path

from .main import create_app


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        schema = create_app(Path(directory) / "contract.sqlite3").openapi()
    output = Path("contracts/openapi.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
