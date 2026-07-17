"""Capture a deterministic fallback baseline when real APIs are unavailable."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from services.agent_support_schemas import RunRequest, SupportResult
from services.agent_support_service import AgentSupportService

OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "eval"
    / "vertical"
    / "baselines"
    / "agent_support_mock.json"
)

CASES = [
    RunRequest(query="住民票の取得方法は？", vertical="gov", do_action=False),
    RunRequest(query="架空機能 Quantum Sync Pro の設定手順は？", vertical="saas", do_action=False),
    RunRequest(query="バグのチケットを作成してください", vertical="saas", do_action=True),
    RunRequest(query="不正アクセスの疑いがあります", vertical="ec", do_action=True),
]


def mock_runner(query: str, **kwargs) -> SupportResult:
    sink = kwargs["event_sink"]
    sink("plan_started", {"query": query})
    sink("execution_started", {"steps": 1})
    if "架空機能" in query:
        sink("no_info_completed", {"detected": True})
        return SupportResult(decision="escalate", no_info_detected=True, vertical="saas")
    if "バグ" in query:
        return SupportResult(
            answer="チケット作成候補です。",
            decision="answer",
            intent="request",
            vertical="saas",
        )
    if "不正アクセス" in query:
        return SupportResult(decision="escalate", intent="incident", vertical="ec")
    return SupportResult(
        answer="住民票の取得方法を案内します。",
        citations=["[社内] gov_faq"],
        groundedness=1.0,
        groundedness_decided=1,
        decision="answer",
        intent="question",
        vertical="gov",
    )


def main() -> None:
    service = AgentSupportService(runner=mock_runner)
    results = []
    for request in CASES:
        started = perf_counter()
        record = service.run_sync(request)
        elapsed_ms = round((perf_counter() - started) * 1000, 3)
        results.append({
            "request": request.model_dump(mode="json"),
            "state": record.state.value,
            "result": record.result.model_dump(mode="json") if record.result else None,
            "pending_confirmation": (
                record.pending_confirmation.model_dump(mode="json")
                if record.pending_confirmation else None
            ),
            "elapsed_ms": elapsed_ms,
        })
    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "mode": "mock-fallback",
        "reason": "real API baseline unavailable",
        "availability": {
            "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
            "gemini": bool(os.getenv("GOOGLE_API_KEY")),
        },
        "cases": results,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
