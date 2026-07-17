from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

from agent_support_example import (
    PROFILES,
    create_run_config,
    execute_support_workflow,
)
from agent_support_example import (
    SupportResult as LegacySupportResult,
)
from eval.vertical.run import run_case
from grace.config import get_config
from services.agent_support_schemas import ExecutionState, RunRequest
from services.agent_support_service import AgentSupportService


def _runner(query, **kwargs):
    sink = kwargs["event_sink"]
    sink("plan_started", {"query": query})
    sink("execution_started", {"steps": 1})
    sink("groundedness_completed", {"support_rate": 1.0})
    sink("gate_completed", {"decision": "answer"})
    return LegacySupportResult(
        answer="回答", citations=["[社内] source"], groundedness=1.0,
        groundedness_decided=1, decision="answer", vertical=kwargs.get("vertical"),
    )


def test_service_publishes_events_and_completes_without_action():
    service = AgentSupportService(runner=_runner)
    record = service.run_sync(RunRequest(query="質問", do_action=False))

    assert record.state == ExecutionState.COMPLETED
    assert record.result.answer == "回答"
    assert [event.type for event in service.store.events_after(record.run_id)] == [
        "run_queued", "plan_started", "execution_started",
        "groundedness_completed", "gate_completed", "run_completed",
    ]


def test_escalation_is_terminal_without_action_confirmation():
    def escalated(query, **kwargs):
        return LegacySupportResult(answer=None, decision="escalate", vertical="saas")

    service = AgentSupportService(runner=escalated)
    record = service.run_sync(RunRequest(query="障害", vertical="saas", do_action=True))

    assert record.state == ExecutionState.ESCALATED
    assert record.pending_confirmation is None
    assert record.result.escalation_reason == "insufficient_grounding"


def test_explicit_request_can_propose_side_effecting_action():
    def request_result(query, **kwargs):
        return LegacySupportResult(
            answer="返品手続きを案内します",
            decision="answer",
            intent="request",
            vertical="ec",
        )

    service = AgentSupportService(runner=request_result)
    record = service.run_sync(RunRequest(query="返品したい", vertical="ec", do_action=True))

    assert record.state == ExecutionState.PENDING_CONFIRMATION
    assert record.pending_confirmation.action.action_type == "create_ticket"


def test_unknown_intent_never_proposes_action():
    def unknown_intent(query, **kwargs):
        return LegacySupportResult(answer="案内", decision="answer", intent=None, vertical="ec")

    service = AgentSupportService(runner=unknown_intent)
    record = service.run_sync(RunRequest(query="返品したい", vertical="ec", do_action=True))

    assert record.state == ExecutionState.COMPLETED
    assert record.pending_confirmation is None


def test_vertical_configs_are_isolated_across_parallel_runs():
    base = get_config()

    with ThreadPoolExecutor(max_workers=3) as pool:
        configs = list(pool.map(lambda vertical: create_run_config(vertical, base), PROFILES))

    for vertical, config in zip(PROFILES, configs):
        assert config is not base
        assert config.qdrant.allowed_collections == PROFILES[vertical].collections
        assert config.llm.prompt_addendum == PROFILES[vertical].prompt_addendum
    assert base.qdrant.allowed_collections != PROFILES["ec"].collections


def test_eval_vertical_runner_keeps_run_support_agent_contract():
    support = LegacySupportResult(
        answer="回答", citations=["[社内] source"], groundedness=0.9,
        groundedness_decided=1, decision="answer", vertical="gov",
    )
    case = {
        "query": "住民票の取り方は？", "vertical": "gov",
        "category": "in-scope", "expected_decision": "answer",
    }

    with patch("eval.vertical.run.run_support_agent", return_value=support) as runner:
        result = run_case(case, use_web=True, show_output=False)

    assert result.decision == "answer"
    assert result.citation_count == 1
    runner.assert_called_once_with(
        case["query"], use_web=True, do_action=True, dry_run=True, vertical="gov"
    )


def test_service_workflow_is_silent_by_default(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = execute_support_workflow("質問")

    assert result is None
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_service_preserves_web_verification_result_and_events():
    def web_runner(query, **kwargs):
        kwargs["event_sink"]("web_started", {"query": query})
        kwargs["event_sink"]("web_completed", {"agreement": 0.75, "reused": True})
        return LegacySupportResult(
            answer="Web検証済み回答",
            citations=["[Web] https://example.com/source"],
            groundedness=0.8,
            groundedness_decided=2,
            decision="answer",
            used_web=True,
            web_reused=True,
            source_agreement=0.75,
        )

    service = AgentSupportService(runner=web_runner)
    record = service.run_sync(RunRequest(query="Web確認", do_action=False))

    assert record.result.used_web is True
    assert record.result.web_reused is True
    assert record.result.source_agreement == 0.75
    assert [event.type for event in service.store.events_after(record.run_id)][1:3] == [
        "web_started",
        "web_completed",
    ]


def test_service_preserves_no_info_escalation_boundary():
    def no_info_runner(_query, **kwargs):
        kwargs["event_sink"]("no_info_completed", {"detected": True})
        return LegacySupportResult(
            answer=None,
            decision="escalate",
            no_info_detected=True,
            forced_escalate=False,
        )

    service = AgentSupportService(runner=no_info_runner)
    record = service.run_sync(RunRequest(query="架空機能", do_action=False))

    assert record.state == ExecutionState.ESCALATED
    assert record.result.no_info_detected is True
    assert record.result.forced_escalate is False
    assert service.store.events_after(record.run_id)[1].type == "no_info_completed"


def test_dependency_failure_becomes_failed_run_without_secret_leak():
    def unavailable(_query, **_kwargs):
        raise ConnectionError("Qdrant unavailable at localhost")

    service = AgentSupportService(runner=unavailable)
    record = service.run_sync(RunRequest(query="障害", do_action=False))

    assert record.state == ExecutionState.FAILED
    assert record.error == "ConnectionError: Qdrant unavailable at localhost"
    assert "api_key" not in record.error.lower()
    assert service.store.events_after(record.run_id)[-1].type == "run_failed"


def test_web_failure_can_escalate_without_losing_failure_event():
    def failed_web(_query, **kwargs):
        kwargs["event_sink"]("web_started", {})
        kwargs["event_sink"]("web_completed", {"error": "timeout", "agreement": None})
        return LegacySupportResult(answer=None, decision="escalate", used_web=False)

    service = AgentSupportService(runner=failed_web)
    record = service.run_sync(RunRequest(query="Web障害", do_action=False))

    assert record.state == ExecutionState.ESCALATED
    assert record.result.used_web is False
    web_event = service.store.events_after(record.run_id)[2]
    assert web_event.type == "web_completed"
    assert web_event.data["error"] == "timeout"


def test_cancelled_long_run_cannot_publish_more_events_or_propose_action():
    started = Event()
    release = Event()

    def slow_runner(_query, **kwargs):
        started.set()
        release.wait(timeout=2)
        kwargs["event_sink"]("execution_started", {})
        return LegacySupportResult(answer=None, decision="escalate", intent="incident")

    service = AgentSupportService(runner=slow_runner)
    record = service.start(RunRequest(query="長時間障害", vertical="saas", do_action=True))
    assert started.wait(timeout=1)

    service.cancel(record.run_id)
    release.set()

    final = service.store.get(record.run_id)
    assert final.state == ExecutionState.CANCELLED
    assert final.pending_confirmation is None
    assert [event.type for event in service.store.events_after(record.run_id)][-1] == (
        "run_cancelled"
    )
