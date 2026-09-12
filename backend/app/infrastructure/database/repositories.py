"""SQLAlchemy implementations of the write-side repository ports.

Each of these takes an `AsyncSession` it does not own. The Unit of Work owns the
session and hands the same one to all three, which is what makes their writes
share a transaction. None of them commits — committing is the Unit of Work's
job, and a repository that committed on its own would silently break the outbox
invariant.

Async SQLAlchemy note: there is no lazy loading here. Relationships are loaded
eagerly (`lazy="selectin"` on the model, or `selectinload()` on the query),
because touching an unloaded attribute in async SQLAlchemy raises
`MissingGreenlet` instead of quietly issuing a query.
"""

from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.leads.activities import LeadActivity
from app.domain.leads.entities import Lead
from app.domain.shared.events import DomainEvent
from app.infrastructure.database.mappers import (
    activity_to_domain,
    activity_to_row,
    apply_lead_to_row,
    lead_to_domain,
    lead_to_row,
)
from app.infrastructure.database.models import (
    LeadActivityModel,
    LeadModel,
    OutboxEventModel,
)


class SqlAlchemyLeadRepository:
    """Stores and retrieves Lead aggregates. Satisfies ports.LeadRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        # Rows loaded during this unit of work, so `update()` can mutate the
        # instance the session is already tracking rather than creating a
        # second one that would conflict on flush.
        self._identity_map: dict[UUID, LeadModel] = {}

    async def add(self, lead: Lead) -> None:
        row = lead_to_row(lead)
        self._session.add(row)
        self._identity_map[lead.id] = row

    async def update(self, lead: Lead) -> None:
        row = self._identity_map.get(lead.id)
        if row is None:
            row = await self._session.get(LeadModel, lead.id)
            if row is None:
                return
            self._identity_map[lead.id] = row
        apply_lead_to_row(lead, row)

    async def get(self, lead_id: UUID) -> Lead | None:
        row = await self._session.get(LeadModel, lead_id)
        if row is None:
            return None
        self._identity_map[lead_id] = row
        return lead_to_domain(row)

    async def find_by_idempotency_key(self, key: str) -> Lead | None:
        stmt = select(LeadModel).where(LeadModel.idempotency_key == key)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        self._identity_map[row.id] = row
        return lead_to_domain(row)

    async def count_recent_by_email(self, email: str, since_hours: int) -> int:
        cutoff = func.now() - timedelta(hours=since_hours)
        stmt = (
            select(func.count())
            .select_from(LeadModel)
            .where(LeadModel.email == email, LeadModel.created_at >= cutoff)
        )
        return int((await self._session.execute(stmt)).scalar_one())


class SqlAlchemyActivityRepository:
    """Append-only lead timeline. Satisfies ports.ActivityRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, activity: LeadActivity) -> None:
        self._session.add(activity_to_row(activity))

    async def list_for_lead(self, lead_id: UUID) -> list[LeadActivity]:
        stmt = (
            select(LeadActivityModel)
            .where(LeadActivityModel.lead_id == lead_id)
            .order_by(LeadActivityModel.occurred_at.desc())
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [activity_to_domain(row) for row in rows]


class SqlAlchemyOutboxRepository:
    """Appends domain events. Satisfies ports.OutboxRepository.

    The critical property: `add` only stages the row. It becomes durable when
    the Unit of Work commits, alongside the lead — which is the whole point of
    the transactional outbox.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: DomainEvent, correlation_id: str | None = None) -> None:
        self._session.add(
            OutboxEventModel(
                id=event.event_id,
                event_type=type(event).event_type,
                event_version=type(event).event_version,
                aggregate_type=type(event).aggregate_type,
                aggregate_id=event.aggregate_id,
                payload=dict(event.payload),
                correlation_id=correlation_id,
                status="pending",
                attempts=0,
                next_attempt_at=event.occurred_at,
                occurred_at=event.occurred_at,
            )
        )


async def load_lead_with_activities(session: AsyncSession, lead_id: UUID) -> LeadModel | None:
    """Eager-load a lead and its timeline in one round trip.

    `selectinload` issues a second SELECT rather than a JOIN, which avoids
    multiplying the lead's columns across every activity row.
    """
    stmt = (
        select(LeadModel).options(selectinload(LeadModel.activities)).where(LeadModel.id == lead_id)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def new_id() -> UUID:
    return uuid4()
