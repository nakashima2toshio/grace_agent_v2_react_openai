#!/usr/bin/env python3
"""Streamlit Agent Chat と React API の代表問い合わせを同一条件で比較する。"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_support_example import PROFILES
from config import ModelConfig
from services.agent_service import ReActAgent
from services.agent_support_schemas import RunRequest
from services.agent_support_service import AgentSupportService

DEFAULT_QUERY = "住民票を取得したい。"
DEFAULT_TERMS = ("窓口", "コンビニ", "マイナンバーカード", "自治体")
URL_RE = re.compile(r"https?://[^\s)）>]+")


def _urls(text: str) -> list[str]:
    return list(dict.fromkeys(URL_RE.findall(text)))


def run_streamlit_path(query: str, model: str, collections: list[str]) -> dict[str, Any]:
    """Streamlit Agent Chat が利用する ReActAgent 経路を直接実行する。"""
    events = list(ReActAgent(
        selected_collections=collections,
        model_name=model,
        use_hybrid_search=True,
    ).execute_turn(query))
    answer = next(
        (str(event.get("content", "")) for event in reversed(events)
         if event.get("type") == "final_answer"),
        "",
    )
    return {
        "engine": "services.agent_service.ReActAgent (Streamlit Agent Chat)",
        "answer": answer,
        "answer_length": len(answer),
        "urls": _urls(answer),
        "tool_calls": [
            {"name": event.get("name"), "args": event.get("args")}
            for event in events if event.get("type") == "tool_call"
        ],
        "tool_result_count": sum(event.get("type") == "tool_result" for event in events),
        "event_count": len(events),
    }


def run_react_path(query: str) -> dict[str, Any]:
    """React が利用する AgentSupportService 経路を同期実行する。"""
    record = AgentSupportService().run_sync(RunRequest(
        query=query,
        vertical="gov",
        use_web=True,
        do_action=True,
        dry_run=True,
    ))
    result = record.result
    return {
        "engine": "services.agent_support_service.AgentSupportService (React API)",
        "state": record.state.value,
        "error": record.error,
        "decision": result.decision if result else None,
        "escalation_reason": result.escalation_reason if result else None,
        "answer": result.answer if result and result.decision == "answer" else "",
        "answer_length": len(result.answer or "") if result else 0,
        "citations": result.citations if result else [],
        "urls": _urls("\n".join(result.citations)) if result else [],
        "used_web": result.used_web if result else False,
        "retrieved_source_count": result.retrieved_source_count if result else 0,
        "verified_source_count": result.verified_source_count if result else 0,
        "action": result.action.model_dump(mode="json") if result and result.action else None,
        "pending_confirmation": record.pending_confirmation is not None,
    }


def build_report(
    query: str,
    model: str,
    reused_streamlit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    collections = list(PROFILES["gov"].collections)
    streamlit = reused_streamlit or run_streamlit_path(query, model, collections)
    react = run_react_path(query)
    term_presence = {
        term: {
            "streamlit": term in streamlit["answer"],
            "react": term in react["answer"],
        }
        for term in DEFAULT_TERMS
    }
    checks = {
        "streamlit_answer_nonempty": bool(streamlit["answer"].strip()),
        "react_terminal_without_error": react["state"] in {"completed", "escalated"}
        and not react["error"],
        "faq_did_not_create_action": react["action"] is None
        and not react["pending_confirmation"],
        "react_answer_or_safe_escalation": (
            react["decision"] == "answer" and bool(react["answer"].strip())
        ) or (
            react["decision"] == "escalate" and bool(react["escalation_reason"])
        ),
    }
    return {
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "conditions": {
            "query": query,
            "vertical": "gov",
            "model": model,
            "streamlit_collection_policy": "all searchable 3072D collections",
            "react_allowed_collections": collections,
            "collection_scope_equal": False,
            "hybrid_search": True,
            "web": True,
            "action": True,
            "dry_run": True,
        },
        "streamlit": streamlit,
        "react": react,
        "comparison": {
            "term_presence": term_presence,
            "shared_urls": sorted(set(streamlit["urls"]) & set(react["urls"])),
            "checks": checks,
            "passed": all(checks.values()),
            "note": (
                "両画面は異なるオーケストレーションを使用するため、回答文の完全一致は"
                "受入条件にしない。Streamlitは全検索可能コレクション、Reactはgovの"
                "許可コレクションを使う設計差も保持する。FAQでActionを生成せず、Reactが"
                "回答または理由付きの安全なエスカレーションで終端することを必須条件とする。"
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--model", default=ModelConfig.DEFAULT_MODEL)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--reuse-streamlit-from",
        type=Path,
        help="既存比較JSONのStreamlit結果を再利用し、React経路だけを再実行する",
    )
    args = parser.parse_args()

    reused_streamlit = None
    if args.reuse_streamlit_from:
        previous = json.loads(args.reuse_streamlit_from.read_text(encoding="utf-8"))
        previous_conditions = previous.get("conditions", {})
        if (
            previous_conditions.get("query") != args.query
            or previous_conditions.get("model") != args.model
        ):
            parser.error("再利用する比較JSONのquery/modelが今回の条件と一致しません")
        reused_streamlit = previous.get("streamlit")
    report = build_report(args.query, args.model, reused_streamlit)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["comparison"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
