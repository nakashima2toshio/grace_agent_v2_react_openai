"""Shared schemas for the GRACE Support service, API, and clients."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

Decision = Literal["answer", "escalate"]
ActionType = Literal["create_ticket", "send_reply", "escalate_to_human"]
Intent = Literal["question", "request", "incident"]


class ExecutionState(str, Enum):
    QUEUED = "queued"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    GATING = "gating"
    WEB_VERIFYING = "web_verifying"
    NO_INFO_CHECK = "no_info_check"
    PENDING_CONFIRMATION = "pending_confirmation"
    ACTION_EXECUTING = "action_executing"
    COMPLETED = "completed"
    ESCALATED = "escalated"
    CANCELLED = "cancelled"
    FAILED = "failed"


TERMINAL_STATES = {
    ExecutionState.COMPLETED,
    ExecutionState.ESCALATED,
    ExecutionState.CANCELLED,
    ExecutionState.FAILED,
}


class ActionRequest(BaseModel):
    action_type: ActionType
    args: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = True
    action_id: str | None = None

    def __init__(
        self,
        action_type: ActionType | None = None,
        args: dict[str, Any] | None = None,
        **data: Any,
    ) -> None:
        """Keep the existing CLI positional constructor while using one API schema."""
        if action_type is not None:
            data["action_type"] = action_type
        if args is not None:
            data["args"] = args
        super().__init__(**data)


class ActionOutcome(BaseModel):
    success: bool
    message: str
    backend: str
    action_id: str


class VerticalProfile(BaseModel):
    name: str
    collections: list[str] = Field(default_factory=list)
    escalate_keywords: list[str] = Field(default_factory=list)
    action_map: dict[str, ActionType] = Field(default_factory=dict)
    require_identity: bool = False
    notify_th: float | None = None
    confirm_th: float | None = None
    prompt_addendum: str = ""


class SupportResult(BaseModel):
    answer: str | None = None
    citations: list[str] = Field(default_factory=list)
    groundedness: float = 0.0
    groundedness_decided: int = 0
    decision: Decision = "escalate"
    warning: bool = False
    used_web: bool = False
    source_agreement: float | None = None
    contradiction: bool = False
    action: ActionRequest | None = None
    action_result: str | None = None
    action_outcome: ActionOutcome | None = None
    vertical: str | None = None
    overall_confidence: float = 0.0
    intent: Intent | None = None
    forced_escalate: bool = False
    identity_checked: bool = False
    no_info_detected: bool = False
    web_reused: bool = False


class RunEvent(BaseModel):
    id: int = 0
    run_id: str
    type: str
    state: ExecutionState
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RunRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10_000)
    vertical: Literal["gov", "saas", "ec"] | None = None
    use_web: bool = True
    do_action: bool = True
    dry_run: bool = True
    identity: dict[str, str] | None = None


class PendingConfirmation(BaseModel):
    action: ActionRequest
    action_hash: str
    version: int = 1
    expires_at: datetime


class RunRecord(BaseModel):
    run_id: str
    request: RunRequest
    state: ExecutionState = ExecutionState.QUEUED
    result: SupportResult | None = None
    pending_confirmation: PendingConfirmation | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConfirmationRequest(BaseModel):
    decision: Literal["approve", "reject", "modify"]
    version: int
    action_hash: str
    action: ActionRequest | None = None
