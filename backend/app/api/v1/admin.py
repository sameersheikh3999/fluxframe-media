"""Operational endpoints for the outbox queue.

These exist because a background worker you cannot inspect or nudge is a
background worker you cannot debug. In production the dispatcher runs on a
timer; these let an operator force a pass, and replay something that
dead-lettered after the underlying problem is fixed.

Behind the internal secret: they are write endpoints.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from app.dependencies.auth import require_internal_access
from app.dependencies.services import OutboxDispatcherDep
from app.schemas.errors import ErrorResponse

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_internal_access)],
    responses={401: {"model": ErrorResponse, "description": "Not authorised."}},
)


class DispatchResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    claimed: int
    processed: int
    failed: int
    dead_lettered: int
    skipped: int


@router.post(
    "/outbox/dispatch",
    response_model=DispatchResponse,
    summary="Run one outbox dispatch pass now",
)
async def dispatch_outbox(dispatcher: OutboxDispatcherDep) -> DispatchResponse:
    """Force a pass without waiting for the poll interval.

    Safe to call at any time, including while the background worker is running:
    `claim_batch` uses FOR UPDATE SKIP LOCKED, so the two never collide over the
    same event.
    """
    report = await dispatcher.dispatch_once()
    return DispatchResponse(
        claimed=report.claimed,
        processed=report.processed,
        failed=report.failed,
        dead_lettered=report.dead_lettered,
        skipped=report.skipped,
    )


@router.post(
    "/outbox/{event_id}/replay",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Return a dead-lettered event to the queue",
    responses={404: {"model": ErrorResponse}},
)
async def replay_event(event_id: UUID, dispatcher: OutboxDispatcherDep) -> None:
    """Reset one event to pending with its attempt counter cleared.

    The intended workflow: a sync dead-lettered because a HubSpot custom
    property was missing, you run the bootstrap script, then you replay.
    """
    if not await dispatcher.replay(event_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No outbox event with that id.",
        )
