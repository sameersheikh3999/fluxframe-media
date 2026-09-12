"""Transport contracts for the lead endpoints.

These describe the wire format and nothing else. They are what FastAPI turns
into `/openapi.json`, which in turn generates the frontend's TypeScript types —
so a backend enum change becomes a frontend compile error rather than a runtime
422.

Schemas import domain enums deliberately (see .importlinter, contract 6). That
gives enum values exactly one source of truth: the same literal is validated
here, stored in PostgreSQL, sent to HubSpot and rendered in the React dropdown.
"""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)

from app.domain.leads.enums import (
    ContentVolume,
    Industry,
    LeadStatus,
    MarketingBudget,
    MonthlyRevenue,
    PrimaryGoal,
    StartTimeline,
)

#: Trimmed, bounded free text. Length caps are the cheapest input validation
#: there is and they close off the "megabyte in a text field" class of abuse.
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=120, strip_whitespace=True)]
MediumText = Annotated[str, StringConstraints(min_length=1, max_length=255, strip_whitespace=True)]


class AttributionRequest(BaseModel):
    """Marketing attribution, all optional — most visitors arrive with none."""

    model_config = ConfigDict(extra="ignore")

    utm_source: str | None = Field(default=None, max_length=255)
    utm_medium: str | None = Field(default=None, max_length=255)
    utm_campaign: str | None = Field(default=None, max_length=255)
    utm_content: str | None = Field(default=None, max_length=255)
    utm_term: str | None = Field(default=None, max_length=255)
    referrer: str | None = Field(default=None, max_length=1024)
    landing_page: str | None = Field(default=None, max_length=1024)


class LeadCreateRequest(BaseModel):
    """The body of POST /api/v1/leads.

    Validation here is strictly transport-level: is this a well-formed email,
    is this string one of the permitted enum values, is it within length limits.
    It does NOT check business rules — "a sub-2k budget with 30 videos a month
    is incoherent" is a domain concern and lives in the scoring rules.
    """

    model_config = ConfigDict(extra="forbid")

    #: Generated once per form mount by the browser (crypto.randomUUID()). Two
    #: submissions of the same form carry the same key, which is what makes a
    #: double-click produce one lead instead of two.
    idempotency_key: str = Field(min_length=8, max_length=128)

    first_name: ShortText
    last_name: ShortText
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    company_name: MediumText
    website: str | None = Field(default=None, max_length=512)

    industry: Industry
    monthly_revenue: MonthlyRevenue
    monthly_marketing_budget: MarketingBudget
    content_volume: ContentVolume
    primary_goal: PrimaryGoal
    start_timeline: StartTimeline
    message: str | None = Field(default=None, max_length=5000)

    attribution: AttributionRequest = Field(default_factory=AttributionRequest)

    @field_validator("website")
    @classmethod
    def _normalise_website(cls, value: str | None) -> str | None:
        """Accept 'acme.com' and store 'https://acme.com'.

        People do not type schemes. Rejecting them for it would lose real leads,
        and asking the domain to cope with both forms would push a transport
        concern inward.
        """
        if not value:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        if not trimmed.startswith(("http://", "https://")):
            return f"https://{trimmed}"
        return trimmed

    @field_validator("phone", "message")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        """An empty optional field means "not provided", not "provided as ''"."""
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class LeadCreateResponse(BaseModel):
    """What a visitor gets back.

    Deliberately thin. No score, no breakdown, no CRM state: a prospect must not
    learn that our system rated them COLD, and exposing scoring internals to the
    public would let anyone reverse-engineer the rules.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID
    created_at: datetime
    message: str = "Thanks — we will be in touch within one business day."


class ScoreComponentResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    dimension: str
    input_value: str
    points: int
    reason: str


class ActivityResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    activity_type: str
    description: str
    actor: str
    occurred_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class SalesBriefResponse(BaseModel):
    """An AI-generated brief, shown alongside the deterministic score."""

    model_config = ConfigDict(frozen=True)

    summary: str
    pain_points: list[str]
    urgency: str
    suggested_service: str
    opening_line: str
    confidence: str
    model: str
    generated_at: datetime


class LeadSummaryResponse(BaseModel):
    """One row of the dashboard table."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    full_name: str
    email: str
    company_name: str
    industry: str
    monthly_marketing_budget: str
    content_volume: str
    score: int | None
    temperature: str | None
    status: str
    crm_sync_status: str
    source: str
    is_demo: bool
    created_at: datetime


class LeadDetailResponse(BaseModel):
    """Everything the dashboard detail page shows."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    first_name: str
    last_name: str
    email: str
    phone: str | None
    company_name: str
    website: str | None

    industry: str
    monthly_revenue: str
    monthly_marketing_budget: str
    content_volume: str
    primary_goal: str
    start_timeline: str
    message: str | None

    score: int | None
    temperature: str | None
    score_version: str | None
    score_breakdown: dict[str, Any] | None

    status: str
    allowed_next_statuses: list[str]
    source: str
    is_demo: bool

    crm_sync_status: str
    crm_contact_id: str | None
    crm_synced_at: datetime | None
    crm_sync_error: str | None
    crm_sync_attempts: int

    attribution: dict[str, str | None]
    activities: list[ActivityResponse]
    sales_brief: SalesBriefResponse | None

    created_at: datetime
    updated_at: datetime


class LeadListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[LeadSummaryResponse]
    total: int
    limit: int
    offset: int
    has_more: bool


class DashboardStatsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_leads: int
    hot_leads: int
    warm_leads: int
    cold_leads: int
    crm_sync_failures: int
    crm_sync_pending: int
    demo_leads: int
    new_last_7_days: int
    outbox_pending: int
    outbox_dead_lettered: int


class LeadStatusUpdateRequest(BaseModel):
    """Move a lead through the sales lifecycle.

    An illegal transition is rejected by the domain entity, not by this schema —
    which is why the dashboard, a worker and a future agent are all constrained
    identically.
    """

    model_config = ConfigDict(extra="forbid")

    status: LeadStatus
    actor: str = Field(default="user:dashboard", max_length=120)
