"""GRACE Support run, event, cancellation, and confirmation endpoints."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse

from api.dependencies import get_agent_support_service
from services.agent_support_run_store import RunConflictError, RunNotFoundError
from services.agent_support_schemas import (
    TERMINAL_STATES,
    ConfirmationRequest,
    RunRecord,
    RunRequest,
)
from services.agent_support_service import AgentSupportService

router = APIRouter(prefix="/api/agent-support", tags=["agent-support"])


@router.post("/runs", response_model=RunRecord, status_code=status.HTTP_202_ACCEPTED)
def create_run(
    request: RunRequest,
    service: AgentSupportService = Depends(get_agent_support_service),
) -> RunRecord:
    return service.start(request)


@router.get("/runs", response_model=list[RunRecord])
def list_runs(service: AgentSupportService = Depends(get_agent_support_service)) -> list[RunRecord]:
    return service.store.list()


@router.get("/runs/{run_id}", response_model=RunRecord)
def get_run(
    run_id: str,
    service: AgentSupportService = Depends(get_agent_support_service),
) -> RunRecord:
    try:
        return service.store.get(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "run_not_found"}) from exc


@router.post("/runs/{run_id}/cancel", response_model=RunRecord)
def cancel_run(
    run_id: str,
    service: AgentSupportService = Depends(get_agent_support_service),
) -> RunRecord:
    try:
        return service.cancel(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "run_not_found"}) from exc
    except RunConflictError as exc:
        raise HTTPException(status_code=409, detail={"code": "run_conflict", "message": str(exc)}) from exc


@router.post("/runs/{run_id}/confirmations")
def resolve_confirmation(
    run_id: str,
    request: ConfirmationRequest,
    service: AgentSupportService = Depends(get_agent_support_service),
):
    try:
        outcome = service.actions.resolve(run_id, request)
        return {"run": service.store.get(run_id), "outcome": outcome}
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "run_not_found"}) from exc
    except RunConflictError as exc:
        raise HTTPException(status_code=409, detail={"code": "confirmation_conflict", "message": str(exc)}) from exc


@router.get("/runs/{run_id}/events")
async def stream_events(
    run_id: str,
    last_event_id: int = Header(default=0, alias="Last-Event-ID"),
    service: AgentSupportService = Depends(get_agent_support_service),
) -> StreamingResponse:
    try:
        service.store.get(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "run_not_found"}) from exc

    async def generate():
        cursor = last_event_id
        while True:
            events = await asyncio.to_thread(service.store.wait_for_events, run_id, cursor, 15.0)
            if events:
                for event in events:
                    cursor = event.id
                    payload = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
                    yield f"id: {event.id}\nevent: {event.type}\ndata: {payload}\n\n"
                if service.store.get(run_id).state in TERMINAL_STATES:
                    break
            else:
                yield ": heartbeat\n\n"
            if service.store.get(run_id).state in TERMINAL_STATES and not events:
                break

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
