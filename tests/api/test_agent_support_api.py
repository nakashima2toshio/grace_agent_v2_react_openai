from unittest.mock import patch

from fastapi.testclient import TestClient

from api.app import app
from api.dependencies import get_agent_support_service
from services.agent_support_schemas import RunRequest
from services.agent_support_service import AgentSupportService


def _runner(query, **kwargs):
    from agent_support_example import SupportResult

    kwargs["event_sink"]("plan_started", {"query": query})
    return SupportResult(answer="ok", citations=["[社内] x"], decision="answer")


def test_health_and_run_contract():
    service = AgentSupportService(runner=_runner)
    app.dependency_overrides[get_agent_support_service] = lambda: service
    client = TestClient(app)
    try:
        assert client.get("/health").json() == {"status": "ok"}
        record = service.run_sync(RunRequest(query="API", do_action=False))
        response = client.get(f"/api/agent-support/runs/{record.run_id}")
        assert response.status_code == 200
        assert response.json()["result"]["answer"] == "ok"
    finally:
        app.dependency_overrides.clear()


def test_validation_and_not_found_error_contract():
    client = TestClient(app)
    assert client.post("/api/agent-support/runs", json={"query": ""}).status_code == 422
    response = client.get("/api/agent-support/runs/missing")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "run_not_found"


def test_sse_replays_ordered_events_for_completed_run():
    service = AgentSupportService(runner=_runner)
    app.dependency_overrides[get_agent_support_service] = lambda: service
    client = TestClient(app)
    try:
        record = service.run_sync(RunRequest(query="SSE", do_action=False))
        response = client.get(
            f"/api/agent-support/runs/{record.run_id}/events",
            headers={"Last-Event-ID": "0"},
        )

        assert response.status_code == 200
        assert "event: run_queued" in response.text
        assert "event: plan_started" in response.text
        assert "event: run_completed" in response.text
        event_ids = [
            int(line.removeprefix("id: "))
            for line in response.text.splitlines()
            if line.startswith("id: ")
        ]
        assert event_ids == sorted(event_ids)
    finally:
        app.dependency_overrides.clear()


def test_confirmation_endpoint_completes_pending_action():
    def action_runner(query, **kwargs):
        from agent_support_example import SupportResult

        kwargs["event_sink"]("plan_started", {"query": query})
        return SupportResult(answer="対応します", decision="answer", intent="request")

    service = AgentSupportService(runner=action_runner)
    app.dependency_overrides[get_agent_support_service] = lambda: service
    client = TestClient(app)
    try:
        record = service.run_sync(RunRequest(
            query="バグのチケットを作成してください",
            vertical="saas",
            do_action=True,
            dry_run=True,
        ))
        pending = record.pending_confirmation
        assert pending is not None

        response = client.post(
            f"/api/agent-support/runs/{record.run_id}/confirmations",
            json={
                "decision": "approve",
                "version": pending.version,
                "action_hash": pending.action_hash,
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["run"]["state"] == "completed"
        assert body["outcome"]["success"] is True
        assert body["run"]["pending_confirmation"] is None
    finally:
        app.dependency_overrides.clear()


def test_sse_reconnect_replays_only_events_after_last_event_id():
    service = AgentSupportService(runner=_runner)
    app.dependency_overrides[get_agent_support_service] = lambda: service
    client = TestClient(app)
    try:
        record = service.run_sync(RunRequest(query="再接続", do_action=False))
        events = service.store.events_after(record.run_id)
        cursor = events[1].id

        response = client.get(
            f"/api/agent-support/runs/{record.run_id}/events",
            headers={"Last-Event-ID": str(cursor)},
        )

        ids = [
            int(line.removeprefix("id: "))
            for line in response.text.splitlines()
            if line.startswith("id: ")
        ]
        assert ids
        assert all(event_id > cursor for event_id in ids)
        assert "event: run_queued" not in response.text
    finally:
        app.dependency_overrides.clear()


def test_readiness_reports_missing_keys_and_stopped_services_without_secrets(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = TestClient(app)

    with patch("api.app._port_open", return_value=False):
        body = client.get("/ready").json()

    assert body == {
        "ready": False,
        "services": {
            "openai": "missing",
            "qdrant": "unavailable",
            "redis": "unavailable",
        },
    }
    assert "key" not in str(body).lower()
