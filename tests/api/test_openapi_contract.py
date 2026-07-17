import json
from copy import deepcopy
from pathlib import Path

from api.app import app

OPENAPI_SNAPSHOT = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"


def test_committed_openapi_snapshot_matches_fastapi_contract():
    committed = json.loads(OPENAPI_SNAPSHOT.read_text(encoding="utf-8"))

    assert _stable_contract(committed) == _stable_contract(app.openapi()), (
        "FastAPI contract changed. Run: "
        "uv run python scripts/export_agent_support_openapi.py && "
        "cd frontend && npm run types:generate"
    )


def _stable_contract(schema: dict) -> dict:
    """Ignore FastAPI/Pydantic validation metadata changed by pytest plugins."""
    stable = deepcopy(schema)
    properties = stable["components"]["schemas"]["ValidationError"]["properties"]
    properties.pop("ctx", None)
    properties.pop("input", None)
    return stable
