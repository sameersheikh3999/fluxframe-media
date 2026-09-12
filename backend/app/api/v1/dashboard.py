"""The internal sales dashboard API.

Every route here is behind `require_internal_access` — a shared secret held only
by the Next.js server. The browser never sees it, because dashboard pages are
rendered server-side.

Note what this dashboard deliberately is NOT: a CRM. HubSpot remains the CRM.
This is the operational layer — it shows what our system did, why it scored a
lead the way it did, and whether the integrations are healthy. Rebuilding
HubSpot would be a large amount of work to produce something worse.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.application.dto.leads import LeadDetailView, LeadFilters
from app.dependencies.auth import require_internal_access
from app.dependencies.services import (
    LeadQueryServiceDep,
    LeadServiceDep,
    SalesBriefServiceDep,
)
from app.observability.context import get_request_id
from app.schemas.errors import ErrorResponse
from app.schemas.leads import (
    ActivityResponse,
    DashboardStatsResponse,
    LeadDetailResponse,
    LeadListResponse,
    LeadStatusUpdateRequest,
    LeadSummaryResponse,
    SalesBriefResponse,
)

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_internal_access)],
    responses={401: {"model": ErrorResponse, "description": "Not authorised."}},
)


@router.get("/stats", response_model=DashboardStatsResponse, summary="Headline counters")
async def get_stats(service: LeadQueryServiceDep) -> DashboardStatsResponse:
    stats = await service.stats()
    pending, dead = await service.outbox_health()
    return DashboardStatsResponse(
        total_leads=stats.total_leads,
        hot_leads=stats.hot_leads,
        warm_leads=stats.warm_leads,
        cold_leads=stats.cold_leads,
        crm_sync_failures=stats.crm_sync_failures,
        crm_sync_pending=stats.crm_sync_pending,
        demo_leads=stats.demo_leads,
        new_last_7_days=stats.new_last_7_days,
        outbox_pending=pending,
        outbox_dead_lettered=dead,
    )


@router.get("/leads", response_model=LeadListResponse, summary="List leads")
async def list_leads(
    service: LeadQueryServiceDep,
    temperature: Annotated[str | None, Query(max_length=16)] = None,
    lead_status: Annotated[str | None, Query(alias="status", max_length=32)] = None,
    crm_sync_status: Annotated[str | None, Query(max_length=16)] = None,
    search: Annotated[str | None, Query(max_length=120)] = None,
    include_demo: bool = True,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LeadListResponse:
    """A filtered, paginated page of leads.

    `limit` is capped in the schema AND clamped again in the query service:
    two layers, because `?limit=100000` is a denial-of-service vector that costs
    the caller one keystroke.
    """
    page = await service.list_leads(
        LeadFilters(
            temperature=temperature,
            status=lead_status,
            crm_sync_status=crm_sync_status,
            search=search,
            include_demo=include_demo,
        ),
        limit=limit,
        offset=offset,
    )
    return LeadListResponse(
        items=[
            LeadSummaryResponse(
                id=item.id,
                full_name=item.full_name,
                email=item.email,
                company_name=item.company_name,
                industry=item.industry,
                monthly_marketing_budget=item.monthly_marketing_budget,
                content_volume=item.content_volume,
                score=item.score,
                temperature=item.temperature,
                status=item.status,
                crm_sync_status=item.crm_sync_status,
                source=item.source,
                is_demo=item.is_demo,
                created_at=item.created_at,
            )
            for item in page.items
        ],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
        has_more=page.has_more,
    )


@router.get(
    "/leads/{lead_id}",
    response_model=LeadDetailResponse,
    summary="One lead, with score breakdown and timeline",
    responses={404: {"model": ErrorResponse}},
)
async def get_lead(lead_id: UUID, service: LeadQueryServiceDep) -> LeadDetailResponse:
    detail = await service.get_lead(lead_id)
    return _to_detail_response(detail)


@router.patch(
    "/leads/{lead_id}/status",
    response_model=LeadDetailResponse,
    summary="Move a lead through the sales lifecycle",
    responses={
        404: {"model": ErrorResponse},
        422: {
            "model": ErrorResponse,
            "description": (
                "The requested transition is not legal for this lead's current "
                "status. Enforced by the domain entity, not by this route."
            ),
        },
    },
)
async def update_status(
    lead_id: UUID,
    payload: LeadStatusUpdateRequest,
    lead_service: LeadServiceDep,
    query_service: LeadQueryServiceDep,
) -> LeadDetailResponse:
    await lead_service.transition_status(
        lead_id,
        payload.status,
        actor=payload.actor,
        correlation_id=get_request_id(),
    )
    return _to_detail_response(await query_service.get_lead(lead_id))


@router.post(
    "/leads/{lead_id}/rescore",
    response_model=LeadDetailResponse,
    summary="Recompute this lead's score under the current rules",
    responses={404: {"model": ErrorResponse}},
)
async def rescore(
    lead_id: UUID,
    lead_service: LeadServiceDep,
    query_service: LeadQueryServiceDep,
) -> LeadDetailResponse:
    """Explicit and manual on purpose.

    Re-scoring automatically when the rules change would rewrite the
    explanation attached to a lead a salesperson has already acted on.
    """
    await lead_service.rescore_lead(lead_id)
    return _to_detail_response(await query_service.get_lead(lead_id))


@router.post(
    "/leads/{lead_id}/sales-brief",
    response_model=SalesBriefResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate an AI sales brief for this lead",
    responses={
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse, "description": "The model returned unusable output."},
        503: {
            "model": ErrorResponse,
            "description": "No AI provider configured (set ANTHROPIC_API_KEY).",
        },
    },
)
async def generate_sales_brief(lead_id: UUID, service: SalesBriefServiceDep) -> SalesBriefResponse:
    """Interpret the prospect's own words into a structured brief.

    The AI never touches the score — that stays deterministic, versioned and
    explainable. This runs alongside it.
    """
    brief = await service.generate_for_lead(lead_id, correlation_id=get_request_id())
    return SalesBriefResponse(
        summary=brief.summary,
        pain_points=list(brief.pain_points),
        urgency=brief.urgency,
        suggested_service=brief.suggested_service,
        opening_line=brief.opening_line,
        confidence=brief.confidence,
        model=brief.model,
        generated_at=brief.generated_at,
    )


def _to_detail_response(detail: LeadDetailView) -> LeadDetailResponse:
    """Map the application's LeadDetailView onto the wire schema.

    Six lines of boilerplate that could be avoided by returning the DTO
    directly — and that is exactly the shortcut that couples the public API to
    an internal type. The next field the dashboard needs but the API must not
    expose (a raw CRM error, an internal note) is where that bill comes due.
    """
    return LeadDetailResponse(
        id=detail.id,
        first_name=detail.first_name,
        last_name=detail.last_name,
        email=detail.email,
        phone=detail.phone,
        company_name=detail.company_name,
        website=detail.website,
        industry=detail.industry,
        monthly_revenue=detail.monthly_revenue,
        monthly_marketing_budget=detail.monthly_marketing_budget,
        content_volume=detail.content_volume,
        primary_goal=detail.primary_goal,
        start_timeline=detail.start_timeline,
        message=detail.message,
        score=detail.score,
        temperature=detail.temperature,
        score_version=detail.score_version,
        score_breakdown=detail.score_breakdown,
        status=detail.status,
        allowed_next_statuses=list(detail.allowed_next_statuses),
        source=detail.source,
        is_demo=detail.is_demo,
        crm_sync_status=detail.crm_sync_status,
        crm_contact_id=detail.crm_contact_id,
        crm_synced_at=detail.crm_synced_at,
        crm_sync_error=detail.crm_sync_error,
        crm_sync_attempts=detail.crm_sync_attempts,
        attribution=detail.attribution,
        activities=[
            ActivityResponse(
                id=activity.id,
                activity_type=activity.activity_type,
                description=activity.description,
                actor=activity.actor,
                occurred_at=activity.occurred_at,
                metadata=dict(activity.activity_metadata),
            )
            for activity in detail.activities
        ],
        sales_brief=(
            SalesBriefResponse(
                summary=detail.sales_brief.summary,
                pain_points=list(detail.sales_brief.pain_points),
                urgency=detail.sales_brief.urgency,
                suggested_service=detail.sales_brief.suggested_service,
                opening_line=detail.sales_brief.opening_line,
                confidence=detail.sales_brief.confidence,
                model=detail.sales_brief.model,
                generated_at=detail.sales_brief.generated_at,
            )
            if detail.sales_brief
            else None
        ),
        created_at=detail.created_at,
        updated_at=detail.updated_at,
    )
