"""DTOs for the lead use cases.

Commands go in, views come out. Both are plain dataclasses — see the note in
`app/application/dto/__init__.py` for why they are not Pydantic models.

Note the asymmetry: a command carries domain enums (the API layer has already
parsed and validated the strings), while a view carries primitives (the API
layer is about to serialise it, and it should not have to reach into an enum to
do so). That keeps each boundary doing one conversion, in one direction.
"""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.domain.leads.enums import (
    ContentVolume,
    Industry,
    LeadSource,
    MarketingBudget,
    MonthlyRevenue,
    PrimaryGoal,
    StartTimeline,
)


@dataclass(frozen=True, slots=True)
class AttributionCommand:
    """Marketing attribution captured alongside the form submission."""

    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    utm_content: str | None = None
    utm_term: str | None = None
    referrer: str | None = None
    landing_page: str | None = None


@dataclass(frozen=True, slots=True)
class CaptureLeadCommand:
    """Everything needed to capture one lead.

    Used identically by the public form and by the demo generator — which is the
    architectural rule that makes synthetic data exercise the real application
    rather than a shortcut around it.
    """

    idempotency_key: str
    first_name: str
    last_name: str
    email: str
    company_name: str
    industry: Industry
    monthly_revenue: MonthlyRevenue
    monthly_marketing_budget: MarketingBudget
    content_volume: ContentVolume
    primary_goal: PrimaryGoal
    start_timeline: StartTimeline

    website: str | None = None
    phone: str | None = None
    message: str | None = None

    source: LeadSource = LeadSource.WEBSITE
    is_demo: bool = False
    attribution: AttributionCommand = field(default_factory=AttributionCommand)


@dataclass(frozen=True, slots=True)
class ScoreComponentView:
    dimension: str
    input_value: str
    points: int
    reason: str


@dataclass(frozen=True, slots=True)
class LeadCaptureResult:
    """What the public endpoint returns.

    Deliberately thin. A visitor does not need — and must not receive — the
    score breakdown or the CRM sync state. The dashboard gets the full view.
    """

    id: UUID
    created_at: datetime
    #: True when this request replayed an idempotency key we had already seen,
    #: so the router can answer 200 instead of 201 without re-deriving it.
    was_duplicate: bool


@dataclass(frozen=True, slots=True)
class LeadSummaryView:
    """One row of the dashboard table.

    A read model, not a rehydrated aggregate. Building full Lead entities to
    render a table would mean loading data nobody displays.
    """

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


@dataclass(frozen=True, slots=True)
class ActivityView:
    id: UUID
    activity_type: str
    description: str
    actor: str
    occurred_at: datetime
    activity_metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class SalesBriefView:
    """An AI-generated sales brief attached to a lead."""

    summary: str
    pain_points: tuple[str, ...]
    urgency: str
    suggested_service: str
    opening_line: str
    confidence: str
    model: str
    generated_at: datetime


@dataclass(frozen=True, slots=True)
class LeadDetailView:
    """Everything the dashboard detail page shows about one lead."""

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
    score_breakdown: dict[str, object] | None

    status: str
    allowed_next_statuses: tuple[str, ...]
    source: str
    is_demo: bool

    crm_sync_status: str
    crm_contact_id: str | None
    crm_synced_at: datetime | None
    crm_sync_error: str | None
    crm_sync_attempts: int

    attribution: dict[str, str | None]
    activities: tuple[ActivityView, ...]
    sales_brief: SalesBriefView | None

    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class DashboardStats:
    """The counters across the top of the dashboard."""

    total_leads: int
    hot_leads: int
    warm_leads: int
    cold_leads: int
    crm_sync_failures: int
    crm_sync_pending: int
    demo_leads: int
    new_last_7_days: int


@dataclass(frozen=True, slots=True)
class LeadPage:
    """A page of dashboard rows, plus what the UI needs to paginate."""

    items: tuple[LeadSummaryView, ...]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


@dataclass(frozen=True, slots=True)
class LeadFilters:
    """Dashboard filter state.

    `None` means "do not filter on this", which is different from filtering on
    an empty value — hence optional fields rather than sentinel strings.
    """

    temperature: str | None = None
    status: str | None = None
    crm_sync_status: str | None = None
    search: str | None = None
    include_demo: bool = True
