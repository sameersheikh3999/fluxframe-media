"""ORM models — how the domain is stored, not what it means.

These are deliberately separate objects from the domain entities in
app/domain/leads/. A `LeadModel` is a row; a `Lead` is a business object with
rules. Keeping them apart is what lets the domain stay free of SQLAlchemy, and
the translation between them lives in one place: `mappers.py`.

Enum columns are stored as VARCHAR rather than PostgreSQL native ENUM. Native
enums need `ALTER TYPE ... ADD VALUE` to evolve and cannot drop values, and the
industry list and lifecycle states here will definitely change. The tradeoff
accepted: the database will not reject a hand-typed bad value — the domain will.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, JsonDict, TimestampTz


class LeadModel(Base):
    """A captured lead."""

    __tablename__ = "leads"

    id: Mapped[UUID] = mapped_column(primary_key=True)

    #: The duplicate-submission guard. UNIQUE is what actually enforces
    #: idempotency: the service's pre-check is only the fast path, and two
    #: concurrent requests are settled here by the database.
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)

    # --- contact -------------------------------------------------------------
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    #: Indexed but deliberately NOT unique. Someone enquiring again six months
    #: later is a new lead, not a constraint violation.
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(50))
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    website: Mapped[str | None] = mapped_column(String(512))

    # --- qualification answers ----------------------------------------------
    industry: Mapped[str] = mapped_column(String(64), nullable=False)
    monthly_revenue: Mapped[str] = mapped_column(String(64), nullable=False)
    monthly_marketing_budget: Mapped[str] = mapped_column(String(64), nullable=False)
    content_volume: Mapped[str] = mapped_column(String(64), nullable=False)
    primary_goal: Mapped[str] = mapped_column(String(64), nullable=False)
    start_timeline: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)

    # --- scoring -------------------------------------------------------------
    lead_score: Mapped[int | None] = mapped_column(Integer)
    lead_temperature: Mapped[str | None] = mapped_column(String(16))
    score_version: Mapped[str | None] = mapped_column(String(16))
    #: The full explanation. Persisted so "why did this lead score 87?" stays
    #: answerable even after the rules change.
    score_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JsonDict)

    # --- process -------------------------------------------------------------
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="new")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="website")
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- attribution ---------------------------------------------------------
    utm_source: Mapped[str | None] = mapped_column(String(255))
    utm_medium: Mapped[str | None] = mapped_column(String(255))
    utm_campaign: Mapped[str | None] = mapped_column(String(255))
    utm_content: Mapped[str | None] = mapped_column(String(255))
    utm_term: Mapped[str | None] = mapped_column(String(255))
    referrer: Mapped[str | None] = mapped_column(String(1024))
    landing_page: Mapped[str | None] = mapped_column(String(1024))

    # --- CRM synchronisation -------------------------------------------------
    hubspot_contact_id: Mapped[str | None] = mapped_column(String(64))
    hubspot_sync_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    hubspot_sync_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hubspot_synced_at: Mapped[datetime | None] = mapped_column(TimestampTz)
    hubspot_sync_error: Mapped[str | None] = mapped_column(Text)

    # --- timestamps ----------------------------------------------------------
    # Set by the application through the Clock port (so tests can freeze time),
    # with a server default as a safety net against a direct SQL insert.
    created_at: Mapped[datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )

    activities: Mapped[list["LeadActivityModel"]] = relationship(
        back_populates="lead",
        cascade="all, delete-orphan",
        lazy="selectin",  # never lazy-load in async SQLAlchemy
    )

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_leads_idempotency_key"),
        # The dashboard's default sort.
        Index("ix_leads_created_at_desc", created_at.desc()),
        # The dashboard's most common filter combination.
        Index("ix_leads_temperature_created", "lead_temperature", created_at.desc()),
        Index("ix_leads_status", "status"),
        # Partial index: we only ever query for leads that are NOT synced, so
        # indexing the synced ones would be wasted space on the hot path.
        Index(
            "ix_leads_sync_status_unsynced",
            "hubspot_sync_status",
            postgresql_where=(hubspot_sync_status != "synced"),
        ),
        Index("ix_leads_is_demo", "is_demo"),
    )


class LeadActivityModel(Base):
    """One entry in a lead's timeline. Append-only."""

    __tablename__ = "lead_activities"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    lead_id: Mapped[UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), nullable=False
    )
    activity_type: Mapped[str] = mapped_column(String(48), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    #: "system" | "demo_generator" | "user:sam" | "agent:SalesBriefAgent".
    #: Free-form so a new kind of actor needs no migration.
    actor: Mapped[str] = mapped_column(String(120), nullable=False, default="system")
    activity_metadata: Mapped[dict[str, Any]] = mapped_column(
        JsonDict, nullable=False, default=dict
    )
    occurred_at: Mapped[datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )

    lead: Mapped[LeadModel] = relationship(back_populates="activities")

    __table_args__ = (Index("ix_lead_activities_lead_occurred", "lead_id", occurred_at.desc()),)


class OutboxEventModel(Base):
    """A domain event awaiting delivery.

    This table IS the queue. Because it lives in the same database as `leads`,
    inserting a row here is atomic with inserting the lead — which is the entire
    reason the transactional outbox pattern works and a message broker cannot
    offer the same guarantee.
    """

    __tablename__ = "outbox_events"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    aggregate_type: Mapped[str] = mapped_column(String(32), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonDict, nullable=False)

    #: The HTTP request id that caused this event, carried through so a HubSpot
    #: call made ten seconds later traces back to the web request.
    correlation_id: Mapped[str | None] = mapped_column(String(64))

    #: pending | processing | processed | failed | dead
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )
    last_error: Mapped[str | None] = mapped_column(Text)

    occurred_at: Mapped[datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )
    #: When a worker claimed it. Used to detect rows abandoned by a dead worker.
    claimed_at: Mapped[datetime | None] = mapped_column(TimestampTz)
    processed_at: Mapped[datetime | None] = mapped_column(TimestampTz)

    __table_args__ = (
        # The dispatcher's claim query: "due work, oldest first".
        Index("ix_outbox_due", "status", "next_attempt_at"),
        Index("ix_outbox_aggregate", "aggregate_type", "aggregate_id"),
    )


class AiRunModel(Base):
    """One call to a language model, recorded for evaluation and cost tracking.

    Exists so that questions like "what is this feature costing?" and "did
    latency regress when we changed prompt version?" are answerable from data
    rather than from memory.
    """

    __tablename__ = "ai_runs"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    feature: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)

    #: succeeded | failed
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)

    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_usd: Mapped[float | None] = mapped_column()

    output: Mapped[dict[str, Any]] = mapped_column(JsonDict, nullable=False, default=dict)

    #: Deliberately unused for now: the hook for a thumbs up/down control, which
    #: is what turns a pile of runs into an evaluation set.
    human_rating: Mapped[int | None] = mapped_column(Integer)

    lead_id: Mapped[UUID | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"))
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_ai_runs_feature_created", "feature", created_at.desc()),)
