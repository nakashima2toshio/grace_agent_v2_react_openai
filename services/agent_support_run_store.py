"""Thread-safe run state and ordered event storage."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import Condition, RLock
from time import monotonic, sleep
from typing import Protocol
from uuid import uuid4

from redis import Redis

from services.agent_support_schemas import (
    TERMINAL_STATES,
    ExecutionState,
    PendingConfirmation,
    RunEvent,
    RunRecord,
    RunRequest,
    SupportResult,
)


class RunNotFoundError(KeyError):
    pass


class RunConflictError(RuntimeError):
    pass


class AgentSupportRunStore(Protocol):
    def create(self, request: RunRequest) -> RunRecord: ...
    def get(self, run_id: str) -> RunRecord: ...
    def list(self) -> list[RunRecord]: ...
    def update_state(self, run_id: str, state: ExecutionState) -> RunRecord: ...
    def set_result(self, run_id: str, result: SupportResult) -> RunRecord: ...
    def set_pending(
        self, run_id: str, pending: PendingConfirmation | None,
    ) -> RunRecord: ...
    def set_error(self, run_id: str, message: str) -> RunRecord: ...
    def append_event(self, event: RunEvent) -> RunEvent: ...
    def events_after(self, run_id: str, event_id: int = 0) -> list[RunEvent]: ...
    def wait_for_events(
        self, run_id: str, event_id: int, timeout: float,
    ) -> list[RunEvent]: ...
    def cancel(self, run_id: str) -> RunRecord: ...


class InMemoryAgentSupportRunStore:
    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._events: dict[str, list[RunEvent]] = {}
        self._lock = RLock()
        self._changed = Condition(self._lock)

    def create(self, request: RunRequest) -> RunRecord:
        with self._changed:
            record = RunRecord(run_id=str(uuid4()), request=request)
            self._runs[record.run_id] = record
            self._events[record.run_id] = []
            return deepcopy(record)

    def get(self, run_id: str) -> RunRecord:
        with self._lock:
            if run_id not in self._runs:
                raise RunNotFoundError(run_id)
            return deepcopy(self._runs[run_id])

    def list(self) -> list[RunRecord]:
        with self._lock:
            return [deepcopy(item) for item in self._runs.values()]

    def update_state(self, run_id: str, state: ExecutionState) -> RunRecord:
        with self._changed:
            record = self._require(run_id)
            if record.state in TERMINAL_STATES and record.state != state:
                raise RunConflictError(f"run is already terminal: {record.state}")
            record.state = state
            record.updated_at = datetime.now(timezone.utc)
            self._changed.notify_all()
            return deepcopy(record)

    def set_result(self, run_id: str, result: SupportResult) -> RunRecord:
        with self._changed:
            record = self._require(run_id)
            record.result = result
            record.updated_at = datetime.now(timezone.utc)
            self._changed.notify_all()
            return deepcopy(record)

    def set_pending(self, run_id: str, pending: PendingConfirmation | None) -> RunRecord:
        with self._changed:
            record = self._require(run_id)
            record.pending_confirmation = pending
            record.updated_at = datetime.now(timezone.utc)
            self._changed.notify_all()
            return deepcopy(record)

    def set_error(self, run_id: str, message: str) -> RunRecord:
        with self._changed:
            record = self._require(run_id)
            record.error = message
            record.updated_at = datetime.now(timezone.utc)
            self._changed.notify_all()
            return deepcopy(record)

    def append_event(self, event: RunEvent) -> RunEvent:
        with self._changed:
            self._require(event.run_id)
            stored = event.model_copy(update={"id": len(self._events[event.run_id]) + 1})
            self._events[event.run_id].append(stored)
            self._changed.notify_all()
            return deepcopy(stored)

    def events_after(self, run_id: str, event_id: int = 0) -> list[RunEvent]:
        with self._lock:
            self._require(run_id)
            return [deepcopy(e) for e in self._events[run_id] if e.id > event_id]

    def wait_for_events(self, run_id: str, event_id: int, timeout: float) -> list[RunEvent]:
        with self._changed:
            events = self.events_after(run_id, event_id)
            if not events and self._runs[run_id].state not in TERMINAL_STATES:
                self._changed.wait(timeout)
                events = self.events_after(run_id, event_id)
            return events

    def cancel(self, run_id: str) -> RunRecord:
        return self.update_state(run_id, ExecutionState.CANCELLED)

    def _require(self, run_id: str) -> RunRecord:
        if run_id not in self._runs:
            raise RunNotFoundError(run_id)
        return self._runs[run_id]


class RedisAgentSupportRunStore:
    """Persistent RunStore using a Redis namespace separate from Celery."""

    def __init__(
        self,
        client: Redis,
        namespace: str = "grace:agent_support:v1",
        poll_interval: float = 0.05,
    ) -> None:
        self.client = client
        self.namespace = namespace.rstrip(":")
        self.poll_interval = poll_interval
        self._lock = RLock()

    @classmethod
    def from_url(
        cls,
        url: str = "redis://localhost:6379/2",
        namespace: str = "grace:agent_support:v1",
    ) -> RedisAgentSupportRunStore:
        return cls(Redis.from_url(url, decode_responses=True), namespace)

    def create(self, request: RunRequest) -> RunRecord:
        record = RunRecord(run_id=str(uuid4()), request=request)
        self.client.set(self._run_key(record.run_id), record.model_dump_json())
        self.client.delete(self._event_key(record.run_id), self._seq_key(record.run_id))
        return record.model_copy(deep=True)

    def get(self, run_id: str) -> RunRecord:
        raw = self.client.get(self._run_key(run_id))
        if raw is None:
            raise RunNotFoundError(run_id)
        return RunRecord.model_validate_json(raw)

    def list(self) -> list[RunRecord]:
        records = [
            RunRecord.model_validate_json(raw)
            for key in self.client.scan_iter(match=f"{self.namespace}:run:*")
            if (raw := self.client.get(key)) is not None
        ]
        return sorted(records, key=lambda item: item.created_at, reverse=True)

    def update_state(self, run_id: str, state: ExecutionState) -> RunRecord:
        def apply(record: RunRecord) -> RunRecord:
            if record.state in TERMINAL_STATES and record.state != state:
                raise RunConflictError(f"run is already terminal: {record.state}")
            return record.model_copy(update={"state": state})

        return self._mutate(run_id, apply)

    def set_result(self, run_id: str, result: SupportResult) -> RunRecord:
        return self._mutate(run_id, lambda record: record.model_copy(
            update={"result": result},
        ))

    def set_pending(
        self, run_id: str, pending: PendingConfirmation | None,
    ) -> RunRecord:
        return self._mutate(run_id, lambda record: record.model_copy(
            update={"pending_confirmation": pending},
        ))

    def set_error(self, run_id: str, message: str) -> RunRecord:
        return self._mutate(run_id, lambda record: record.model_copy(
            update={"error": message},
        ))

    def append_event(self, event: RunEvent) -> RunEvent:
        self.get(event.run_id)
        event_id = int(self.client.incr(self._seq_key(event.run_id)))
        stored = event.model_copy(update={"id": event_id})
        self.client.rpush(self._event_key(event.run_id), stored.model_dump_json())
        return stored.model_copy(deep=True)

    def events_after(self, run_id: str, event_id: int = 0) -> list[RunEvent]:
        self.get(run_id)
        return [
            event
            for raw in self.client.lrange(self._event_key(run_id), 0, -1)
            if (event := RunEvent.model_validate_json(raw)).id > event_id
        ]

    def wait_for_events(
        self, run_id: str, event_id: int, timeout: float,
    ) -> list[RunEvent]:
        deadline = monotonic() + timeout
        while True:
            events = self.events_after(run_id, event_id)
            if events or self.get(run_id).state in TERMINAL_STATES:
                return events
            remaining = deadline - monotonic()
            if remaining <= 0:
                return []
            sleep(min(self.poll_interval, remaining))

    def cancel(self, run_id: str) -> RunRecord:
        return self.update_state(run_id, ExecutionState.CANCELLED)

    def _mutate(self, run_id: str, operation) -> RunRecord:
        with self._lock:
            record = operation(self.get(run_id)).model_copy(
                update={"updated_at": datetime.now(timezone.utc)},
            )
            self.client.set(self._run_key(run_id), record.model_dump_json())
            return record.model_copy(deep=True)

    def _run_key(self, run_id: str) -> str:
        return f"{self.namespace}:run:{run_id}"

    def _event_key(self, run_id: str) -> str:
        return f"{self.namespace}:events:{run_id}"

    def _seq_key(self, run_id: str) -> str:
        return f"{self.namespace}:event_seq:{run_id}"
