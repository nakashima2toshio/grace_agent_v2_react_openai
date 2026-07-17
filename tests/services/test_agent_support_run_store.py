from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from services.agent_support_run_store import (
    InMemoryAgentSupportRunStore,
    RedisAgentSupportRunStore,
    RunConflictError,
)
from services.agent_support_schemas import (
    ActionRequest,
    ExecutionState,
    PendingConfirmation,
    RunEvent,
    RunRequest,
)


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.lists = {}

    def set(self, key, value):
        self.values[key] = value

    def get(self, key):
        return self.values.get(key)

    def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)
            self.lists.pop(key, None)

    def incr(self, key):
        value = int(self.values.get(key, 0)) + 1
        self.values[key] = value
        return value

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    def lrange(self, key, start, end):
        values = self.lists.get(key, [])
        return values[start:] if end == -1 else values[start:end + 1]

    def scan_iter(self, match):
        prefix = match.removesuffix("*")
        return iter(key for key in self.values if key.startswith(prefix))


def test_parallel_runs_and_events_do_not_mix():
    store = InMemoryAgentSupportRunStore()
    records = [store.create(RunRequest(query=f"q{i}")) for i in range(8)]

    def append(record):
        for index in range(10):
            store.append_event(RunEvent(
                run_id=record.run_id,
                type="step_completed",
                state=ExecutionState.EXECUTING,
                data={"index": index},
            ))

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(append, records))

    for record in records:
        events = store.events_after(record.run_id)
        assert [event.id for event in events] == list(range(1, 11))
        assert [event.data["index"] for event in events] == list(range(10))


def test_terminal_state_cannot_be_reopened():
    store = InMemoryAgentSupportRunStore()
    record = store.create(RunRequest(query="q"))
    store.update_state(record.run_id, ExecutionState.COMPLETED)

    with pytest.raises(RunConflictError):
        store.update_state(record.run_id, ExecutionState.EXECUTING)


def test_redis_store_restores_run_events_and_pending_after_new_instance():
    from datetime import datetime, timedelta, timezone

    redis = FakeRedis()
    first = RedisAgentSupportRunStore(redis, namespace="test:agent", poll_interval=0)
    record = first.create(RunRequest(query="永続化", vertical="saas"))
    first.update_state(record.run_id, ExecutionState.EXECUTING)
    first.append_event(RunEvent(
        run_id=record.run_id,
        type="execution_started",
        state=ExecutionState.EXECUTING,
    ))
    first.set_pending(record.run_id, PendingConfirmation(
        action=ActionRequest("create_ticket", {"query": "永続化"}),
        action_hash="hash",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    ))

    restored = RedisAgentSupportRunStore(redis, namespace="test:agent", poll_interval=0)

    assert restored.get(record.run_id).pending_confirmation.action.action_type == "create_ticket"
    assert restored.events_after(record.run_id)[0].id == 1
    assert restored.list()[0].run_id == record.run_id


def test_redis_store_namespace_isolated_from_other_redis_users():
    redis = FakeRedis()
    redis.set("celery-task-meta-1", "untouched")
    store = RedisAgentSupportRunStore(redis, namespace="grace:agent_support:v1")

    store.create(RunRequest(query="分離"))

    assert redis.get("celery-task-meta-1") == "untouched"
    assert all(
        key.startswith("grace:agent_support:v1:")
        for key in redis.values
        if key != "celery-task-meta-1"
    )


def test_wait_for_events_wakes_on_new_event_without_event_loss():
    store = InMemoryAgentSupportRunStore()
    record = store.create(RunRequest(query="long polling"))
    waiting = Event()

    def wait():
        waiting.set()
        return store.wait_for_events(record.run_id, 0, timeout=1)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(wait)
        assert waiting.wait(timeout=0.5)
        store.append_event(RunEvent(
            run_id=record.run_id,
            type="step_completed",
            state=ExecutionState.EXECUTING,
        ))
        events = future.result(timeout=1)

    assert [event.id for event in events] == [1]
