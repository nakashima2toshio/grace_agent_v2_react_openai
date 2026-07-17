"""Export the deterministic FastAPI contract consumed by the React client."""

import json
from pathlib import Path

from api.app import app

OUTPUT = Path(__file__).resolve().parents[1] / "frontend" / "openapi.json"


def main() -> None:
    OUTPUT.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
