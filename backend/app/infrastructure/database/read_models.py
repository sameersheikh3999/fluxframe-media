"""Read-side SQL: the queries behind the dashboard.

These return view DTOs, not domain entities. Rendering a table of fifty leads by
rehydrating fifty aggregates would load data nobody displays and run the
lifecycle rules fifty times for no reason.

Each method opens and closes its own short session. Reads need no transaction
boundary, so they are not on the Unit of Work.
"""

from datetime import timedelta
from uuid import UUID

from sqlalchemy import Integer, Select, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from app.application.dto.leads import (
    ActivityView,
    DashboardStats,
    LeadDetailView,
    LeadFilters,
    LeadPage,
    LeadSummaryView,
    SalesBriefView,
)
from app.domain.leads.activities import ActivityType
from app.domain.leads.enums import LeadStatus
from app.domain.leads.lifecycle import next_statuses
from app.infrastructure.database.models import (
    LeadActivityModel,
    LeadModel,
    OutboxEventModel,
)
from app.infrastructure.database.repositories import load_lead_with_activities

RECENT_WINDOW_DAYS = 7


class SqlAlchemyLeadReadModel:
    """Dashboard queries. Satisfies ports.read_models.LeadReadModel."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_leads(self, filters: LeadFilters, limit: int, offset: int) -> LeadPage:
        async with self._session_factory() as session:
            base = _apply_filters(select(LeadModel), filters)

            # COUNT over the same filters, before pagination, so the UI can show
            # "showing 25 of 312" rather than guessing whether more exist.
            total = int(
                (
                    await session.execute(select(func.count()).select_from(base.subquery()))
                ).scalar_one()
            )

            rows = (
                (
                    await session.execute(
                        base.order_by(LeadModel.created_at.desc()).limit(limit).offset(offset)
                    )
                )
                .scalars()
                .all()
            )

        return LeadPage(
            items=tuple(_to_summary(row) for row in rows),
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_detail(self, lead_id: UUID) -> LeadDetailView | None:
        async with self._session_factory() as session:
            row = await load_lead_with_activities(session, lead_id)
            if row is None:
                return None

        activities = sorted(row.activities, key=lambda item: item.occurred_at, reverse=True)
        status = LeadStatus(row.status)

        return LeadDetailView(
            id=row.id,
            first_name=row.first_name,
            last_name=row.last_name,
            email=row.email,
            phone=row.phone,
            company_name=row.company_name,
            website=row.website,
            industry=row.industry,
            monthly_revenue=row.monthly_revenue,
            monthly_marketing_budget=row.monthly_marketing_budget,
            content_volume=row.content_volume,
            primary_goal=row.primary_goal,
            start_timeline=row.start_timeline,
            message=row.message,
            score=row.lead_score,
            temperature=row.lead_temperature,
            score_version=row.score_version,
            score_breakdown=row.score_breakdown,
            status=row.status,
            # Ask the domain which buttons to render, so the UI cannot offer a
            # transition the entity would reject.
            allowed_next_statuses=tuple(sorted(s.value for s in next_statuses(status))),
            source=row.source,
            is_demo=row.is_demo,
            crm_sync_status=row.hubspot_sync_status,
            crm_contact_id=row.hubspot_contact_id,
            crm_synced_at=row.hubspot_synced_at,
            crm_sync_error=row.hubspot_sync_error,
            crm_sync_attempts=row.hubspot_sync_attempts,
            attribution={
                "utm_source": row.utm_source,
                "utm_medium": row.utm_medium,
                "utm_campaign": row.utm_campaign,
                "utm_content": row.utm_content,
                "utm_term": row.utm_term,
                "referrer": row.referrer,
                "landing_page": row.landing_page,
            },
            activities=tuple(_to_activity_view(a) for a in activities),
            sales_brief=_latest_brief(activities),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def stats(self) -> DashboardStats:
        """The counters across the top of the dashboard.

        One round trip using conditional aggregates rather than eight COUNT
        queries. `func.count(case(...))` would work too; summing a boolean cast
        reads more clearly and is portable across PostgreSQL and SQLite.
        """
        async with self._session_factory() as session:
            cutoff = func.now() - timedelta(days=RECENT_WINDOW_DAYS)
            stmt = select(
                func.count(LeadModel.id),
                func.sum(_flag(LeadModel.lead_temperature == "hot")),
                func.sum(_flag(LeadModel.lead_temperature == "warm")),
                func.sum(_flag(LeadModel.lead_temperature == "cold")),
                func.sum(_flag(LeadModel.hubspot_sync_status == "failed")),
                func.sum(_flag(LeadModel.hubspot_sync_status == "pending")),
                func.sum(_flag(LeadModel.is_demo.is_(True))),
                func.sum(_flag(LeadModel.created_at >= cutoff)),
            )
            result = (await session.execute(stmt)).one()

        return DashboardStats(
            total_leads=int(result[0] or 0),
            hot_leads=int(result[1] or 0),
            warm_leads=int(result[2] or 0),
            cold_leads=int(result[3] or 0),
            crm_sync_failures=int(result[4] or 0),
            crm_sync_pending=int(result[5] or 0),
            demo_leads=int(result[6] or 0),
            new_last_7_days=int(result[7] or 0),
        )


class SqlAlchemyOutboxReadModel:
    """Operational counters for the event queue."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def pending_count(self) -> int:
        return await self._count_status(("pending", "processing", "failed"))

    async def dead_letter_count(self) -> int:
        return await self._count_status(("dead",))

    async def _count_status(self, statuses: tuple[str, ...]) -> int:
        async with self._session_factory() as session:
            stmt = (
                select(func.count())
                .select_from(OutboxEventModel)
                .where(OutboxEventModel.status.in_(statuses))
            )
            return int((await session.execute(stmt)).scalar_one())


def _flag(condition: ColumnElement[bool]) -> ColumnElement[int]:
    """1 when the condition holds, else 0 — portable across both dialects.

    Lets `stats()` count eight different things in one round trip with
    conditional aggregates, instead of issuing eight separate COUNT queries.
    """
    return case((condition, 1), else_=0).cast(Integer)


def _apply_filters(
    stmt: Select[tuple[LeadModel]], filters: LeadFilters
) -> Select[tuple[LeadModel]]:
    """Build the WHERE clause from dashboard filter state.

    `None` means "do not filter on this", which is why every clause is guarded
    rather than defaulted.
    """
    if filters.temperature:
        stmt = stmt.where(LeadModel.lead_temperature == filters.temperature)
    if filters.status:
        stmt = stmt.where(LeadModel.status == filters.status)
    if filters.crm_sync_status:
        stmt = stmt.where(LeadModel.hubspot_sync_status == filters.crm_sync_status)
    if not filters.include_demo:
        stmt = stmt.where(LeadModel.is_demo.is_(False))
    if filters.search:
        # Case-insensitive contains across the three fields a salesperson would
        # actually type into a search box.
        pattern = f"%{filters.search.strip()}%"
        stmt = stmt.where(
            or_(
                LeadModel.company_name.ilike(pattern),
                LeadModel.email.ilike(pattern),
                LeadModel.last_name.ilike(pattern),
                LeadModel.first_name.ilike(pattern),
            )
        )
    return stmt


def _to_summary(row: LeadModel) -> LeadSummaryView:
    return LeadSummaryView(
        id=row.id,
        full_name=f"{row.first_name} {row.last_name}",
        email=row.email,
        company_name=row.company_name,
        industry=row.industry,
        monthly_marketing_budget=row.monthly_marketing_budget,
        content_volume=row.content_volume,
        score=row.lead_score,
        temperature=row.lead_temperature,
        status=row.status,
        crm_sync_status=row.hubspot_sync_status,
        source=row.source,
        is_demo=row.is_demo,
        created_at=row.created_at,
    )


def _to_activity_view(row: LeadActivityModel) -> ActivityView:
    return ActivityView(
        id=row.id,
        activity_type=row.activity_type,
        description=row.description,
        actor=row.actor,
        occurred_at=row.occurred_at,
        activity_metadata=dict(row.activity_metadata or {}),
    )


def _latest_brief(activities: list[LeadActivityModel]) -> SalesBriefView | None:
    """The most recent AI brief, read out of the timeline.

    Briefs live in the activity log rather than a column on `leads`, because a
    brief IS an event in the lead's history — and storing it that way means
    regenerating keeps the previous one instead of overwriting it.
    """
    for row in activities:
        if row.activity_type != ActivityType.AI_BRIEF_GENERATED.value:
            continue
        data = row.activity_metadata or {}
        raw_points = data.get("pain_points", [])
        points = tuple(str(p) for p in raw_points) if isinstance(raw_points, list) else ()
        return SalesBriefView(
            summary=str(data.get("summary", "")),
            pain_points=points,
            urgency=str(data.get("urgency", "unknown")),
            suggested_service=str(data.get("suggested_service", "")),
            opening_line=str(data.get("opening_line", "")),
            confidence=str(data.get("confidence", "unknown")),
            model=str(data.get("model", "unknown")),
            generated_at=row.occurred_at,
        )
    return None
