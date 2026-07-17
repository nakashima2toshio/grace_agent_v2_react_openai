"""Display-independent orchestration and event publication for GRACE Support."""

from __future__ import annotations

import logging
from threading import Thread
from typing import Callable

from agent_support_example import PROFILES, execute_support_workflow
from services.agent_support_action_service import AgentSupportActionService
from services.agent_support_run_store import (
    AgentSupportRunStore,
    InMemoryAgentSupportRunStore,
)
from services.agent_support_schemas import (
    TERMINAL_STATES,
    ActionRequest,
    ExecutionState,
    RunEvent,
    RunRecord,
    RunRequest,
    SupportResult,
)

EVENT_STATES = {
    "plan_started": ExecutionState.PLANNING,
    "plan_completed": ExecutionState.PLANNING,
    "execution_started": ExecutionState.EXECUTING,
    "executor_state": ExecutionState.EXECUTING,
    "tool_event": ExecutionState.EXECUTING,
    "step_completed": ExecutionState.EXECUTING,
    "groundedness_started": ExecutionState.VERIFYING,
    "groundedness_completed": ExecutionState.VERIFYING,
    "gate_completed": ExecutionState.GATING,
    "web_started": ExecutionState.WEB_VERIFYING,
    "web_completed": ExecutionState.WEB_VERIFYING,
    "no_info_started": ExecutionState.NO_INFO_CHECK,
    "no_info_completed": ExecutionState.NO_INFO_CHECK,
}
logger = logging.getLogger(__name__)


class RunCancelled(RuntimeError):
    pass


class AgentSupportService:
    def __init__(
        self,
        store: AgentSupportRunStore | None = None,
        runner: Callable = execute_support_workflow,
    ) -> None:
        self.store = store or InMemoryAgentSupportRunStore()
        self.runner = runner
        self.actions = AgentSupportActionService(self.store)

    def start(self, request: RunRequest) -> RunRecord:
        record = self.store.create(request)
        self._event(record.run_id, "run_queued", ExecutionState.QUEUED,
                    {"query": request.query, "vertical": request.vertical})
        Thread(target=self._execute, args=(record.run_id,), daemon=True,
               name=f"agent-support-{record.run_id[:8]}").start()
        return record

    def run_sync(self, request: RunRequest) -> RunRecord:
        record = self.store.create(request)
        self._event(record.run_id, "run_queued", ExecutionState.QUEUED,
                    {"query": request.query, "vertical": request.vertical})
        self._execute(record.run_id)
        return self.store.get(record.run_id)

    def cancel(self, run_id: str) -> RunRecord:
        record = self.store.cancel(run_id)
        self._event(run_id, "run_cancelled", ExecutionState.CANCELLED, {})
        return record

    def _execute(self, run_id: str) -> None:
        record = self.store.get(run_id)
        request = record.request

        def sink(event_type: str, data: dict) -> None:
            current = self.store.get(run_id)
            if current.state == ExecutionState.CANCELLED:
                raise RunCancelled()
            state = EVENT_STATES.get(event_type, current.state)
            if state != current.state:
                self.store.update_state(run_id, state)
            self._event(run_id, event_type, state, self._jsonable(data))

        try:
            raw = self.runner(
                request.query,
                use_web=request.use_web,
                do_action=False,
                dry_run=request.dry_run,
                vertical=request.vertical,
                identity=request.identity,
                event_sink=sink,
                render_output=False,
            )
            if raw is None:
                raise RuntimeError("OPENAI_API_KEY is not set")
            result = SupportResult.model_validate(raw)
            if result.decision == "escalate" and result.escalation_reason is None:
                result = result.model_copy(update={
                    "escalation_reason": self._escalation_reason(result),
                })
            action = self._proposed_action(request, result)
            if action is not None:
                result = result.model_copy(update={"action": action})
            self.store.set_result(run_id, result)
            logger.info(
                "agent_support_completed run_id=%s decision=%s replan_count=%d "
                "grounding_undecidable=%s action_proposed=%s",
                run_id,
                result.decision,
                result.replan_count,
                result.groundedness_decided == 0,
                action is not None,
            )
            if action is not None:
                self.actions.propose(run_id, action)
                return
            state = (ExecutionState.COMPLETED if result.decision == "answer"
                     else ExecutionState.ESCALATED)
            self.store.update_state(run_id, state)
            self._event(run_id, "run_completed", state,
                        {"result": result.model_dump(mode="json")})
        except RunCancelled:
            return
        except Exception as exc:
            current = self.store.get(run_id)
            if current.state not in TERMINAL_STATES:
                self.store.set_error(run_id, f"{type(exc).__name__}: {exc}")
                self.store.update_state(run_id, ExecutionState.FAILED)
                self._event(run_id, "run_failed", ExecutionState.FAILED,
                            {"error": f"{type(exc).__name__}: {exc}"})

    @staticmethod
    def _proposed_action(request: RunRequest, result: SupportResult) -> ActionRequest | None:
        # Escalation is a terminal support decision, not a side-effecting Action.
        # HITL is reserved for explicit request/incident Actions such as ticket creation.
        if (
            not request.do_action
            or result.decision == "escalate"
            or result.intent not in {"request", "incident"}
        ):
            return None
        profile = PROFILES.get(request.vertical) if request.vertical else None
        if profile is None:
            return None
        for keyword, action_type in profile.action_map.items():
            if keyword in request.query:
                return ActionRequest(action_type=action_type, args={"query": request.query})
        return None

    @staticmethod
    def _escalation_reason(result: SupportResult) -> str:
        if result.forced_escalate:
            return "forced_policy"
        if result.no_info_detected:
            return "no_information"
        if result.contradiction:
            return "contradiction"
        return "insufficient_grounding"

    def _event(self, run_id: str, event_type: str, state: ExecutionState, data: dict) -> None:
        self.store.append_event(RunEvent(run_id=run_id, type=event_type, state=state, data=data))

    @classmethod
    def _jsonable(cls, value):
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, dict):
            return {key: cls._jsonable(item) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._jsonable(item) for item in value]
        return value
