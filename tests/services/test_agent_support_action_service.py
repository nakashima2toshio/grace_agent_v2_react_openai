from unittest.mock import MagicMock, patch

import pytest

from services.agent_support_action_service import AgentSupportActionService
from services.agent_support_run_store import (
    InMemoryAgentSupportRunStore,
    RunConflictError,
)
from services.agent_support_schemas import (
    ActionRequest,
    ConfirmationRequest,
    ExecutionState,
    RunRequest,
)
from support_actions import ActionOutcome as BackendOutcome


def _pending(dry_run=True, vertical="saas"):
    store = InMemoryAgentSupportRunStore()
    record = store.create(RunRequest(
        query="障害です", vertical=vertical, dry_run=dry_run,
    ))
    service = AgentSupportActionService(store)
    pending = service.propose(record.run_id, ActionRequest(
        action_type="create_ticket", args={"query": "障害です"},
    ))
    return store, service, record, pending


def test_action_is_not_executed_before_confirmation():
    store, _service, record, _pending_record = _pending()
    assert store.get(record.run_id).state == ExecutionState.PENDING_CONFIRMATION


def test_approve_executes_backend_once_even_when_retried():
    store, service, record, pending = _pending()
    backend = MagicMock()
    backend.execute.return_value = BackendOutcome(True, "ok", "fake")
    request = ConfirmationRequest(
        decision="approve", version=pending.version, action_hash=pending.action_hash,
    )
    with patch("services.agent_support_action_service.create_action_backend", return_value=backend):
        first = service.resolve(record.run_id, request)
        second = service.resolve(record.run_id, request)

    assert first == second
    backend.execute.assert_called_once()
    assert store.get(record.run_id).state == ExecutionState.COMPLETED


def test_reject_never_executes_backend():
    store, service, record, pending = _pending()
    with patch("services.agent_support_action_service.create_action_backend") as factory:
        outcome = service.resolve(record.run_id, ConfirmationRequest(
            decision="reject", version=pending.version, action_hash=pending.action_hash,
        ))
    assert outcome is None
    factory.assert_not_called()
    assert store.get(record.run_id).state == ExecutionState.CANCELLED


def test_stale_hash_is_rejected():
    _store, service, record, pending = _pending()
    with pytest.raises(RunConflictError, match="stale"):
        service.resolve(record.run_id, ConfirmationRequest(
            decision="approve", version=pending.version, action_hash="wrong",
        ))


def test_real_ec_action_requires_identity_before_backend():
    _store, service, record, pending = _pending(dry_run=False, vertical="ec")
    with patch("services.agent_support_action_service.create_action_backend") as factory:
        with pytest.raises(RunConflictError, match="identity"):
            service.resolve(record.run_id, ConfirmationRequest(
                decision="approve", version=pending.version, action_hash=pending.action_hash,
            ))
    factory.assert_not_called()
