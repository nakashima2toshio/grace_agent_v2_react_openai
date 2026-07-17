"""Identity, confirmation, and idempotent ActionBackend boundary."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from threading import RLock
from uuid import uuid4

from services.agent_support_run_store import (
    AgentSupportRunStore,
    RunConflictError,
)
from services.agent_support_schemas import (
    ActionOutcome,
    ActionRequest,
    ConfirmationRequest,
    ExecutionState,
    PendingConfirmation,
    RunEvent,
)
from support_actions import create_action_backend, create_identity_verifier


def action_digest(action: ActionRequest) -> str:
    payload = action.model_dump_json(exclude={"action_id"})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AgentSupportActionService:
    def __init__(self, store: AgentSupportRunStore, timeout_seconds: int = 900) -> None:
        self.store = store
        self.timeout_seconds = timeout_seconds
        self._executed: dict[str, ActionOutcome] = {}
        self._resolved_runs: dict[str, ActionOutcome] = {}
        self._lock = RLock()

    def propose(self, run_id: str, action: ActionRequest) -> PendingConfirmation:
        action = action.model_copy(update={"action_id": action.action_id or str(uuid4())})
        pending = PendingConfirmation(
            action=action,
            action_hash=action_digest(action),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.timeout_seconds),
        )
        self.store.set_pending(run_id, pending)
        self.store.update_state(run_id, ExecutionState.PENDING_CONFIRMATION)
        self._event(run_id, "confirmation_required", ExecutionState.PENDING_CONFIRMATION,
                    pending.model_dump(mode="json"))
        return pending

    def resolve(self, run_id: str, request: ConfirmationRequest) -> ActionOutcome | None:
        with self._lock:
            record = self.store.get(run_id)
            pending = record.pending_confirmation
            if pending is None:
                if run_id in self._resolved_runs:
                    return self._resolved_runs[run_id]
                if record.result and record.result.action_outcome:
                    return record.result.action_outcome
                raise RunConflictError("no confirmation is pending")
            if pending.expires_at <= datetime.now(timezone.utc):
                raise RunConflictError("confirmation has expired")
            if request.version != pending.version or request.action_hash != pending.action_hash:
                raise RunConflictError("stale or mismatched confirmation")
            if request.decision == "modify":
                if request.action is None:
                    raise RunConflictError("modified action is required")
                return self._replace_pending(run_id, pending, request.action)
            if request.decision == "reject":
                self.store.set_pending(run_id, None)
                self.store.update_state(run_id, ExecutionState.CANCELLED)
                self._event(run_id, "confirmation_resolved", ExecutionState.CANCELLED,
                            {"decision": "reject"})
                return None

            action_id = pending.action.action_id or ""
            if action_id in self._executed:
                return self._executed[action_id]
            self.store.update_state(run_id, ExecutionState.ACTION_EXECUTING)
            self._event(run_id, "action_started", ExecutionState.ACTION_EXECUTING,
                        {"action_id": action_id})
            verifier = create_identity_verifier(dry_run=record.request.dry_run)
            profile_requires_identity = record.request.vertical == "ec"
            if profile_requires_identity:
                identity = verifier.verify(record.request.identity)
                self._event(run_id, "identity_completed", ExecutionState.ACTION_EXECUTING,
                            {"verified": identity.verified, "method": identity.method,
                             "detail": identity.detail})
                if not identity.verified:
                    self.store.set_pending(run_id, None)
                    self.store.update_state(run_id, ExecutionState.ESCALATED)
                    raise RunConflictError("identity verification failed")
            backend = create_action_backend(dry_run=record.request.dry_run)
            raw = backend.execute(pending.action.action_type, pending.action.args)
            outcome = ActionOutcome(success=raw.success, message=raw.message,
                                    backend=raw.backend, action_id=action_id)
            self._executed[action_id] = outcome
            self._resolved_runs[run_id] = outcome
            self.store.set_pending(run_id, None)
            if record.result:
                result = record.result.model_copy(update={"action_outcome": outcome})
                self.store.set_result(run_id, result)
            state = ExecutionState.COMPLETED if raw.success else ExecutionState.ESCALATED
            self.store.update_state(run_id, state)
            self._event(run_id, "action_completed", state, outcome.model_dump())
            return outcome

    def _replace_pending(self, run_id: str, current: PendingConfirmation,
                         action: ActionRequest) -> None:
        action = action.model_copy(update={"action_id": str(uuid4())})
        replacement = PendingConfirmation(
            action=action,
            action_hash=action_digest(action),
            version=current.version + 1,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.timeout_seconds),
        )
        self.store.set_pending(run_id, replacement)
        self._event(run_id, "confirmation_required", ExecutionState.PENDING_CONFIRMATION,
                    replacement.model_dump(mode="json"))
        return None

    def _event(self, run_id: str, event_type: str, state: ExecutionState, data: dict) -> None:
        self.store.append_event(RunEvent(run_id=run_id, type=event_type, state=state, data=data))
