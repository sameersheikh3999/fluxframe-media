"""The public lead capture endpoint.

This is the most important route in the system and the one most exposed to the
internet, so it is worth reading closely for what it does NOT do:

* no scoring          that is a domain rule (domain/leads/scoring.py)
* no SQL              that is a repository (infrastructure/database/)
* no HubSpot call     that happens later, driven by an outbox event
* no business `if`s   the entity validates itself

It translates HTTP into a command, calls one service method, and maps the result
back. If you deleted this file you could drive the same use case from a CLI in
twenty minutes — which is the test of whether the layering is honest.
"""

from typing import Annotated

from fastapi import APIRouter, Header, Request, Response, status

from app.api.rate_limit import enforce_rate_limit
from app.application.dto.leads import AttributionCommand, CaptureLeadCommand
from app.dependencies.services import LeadServiceDep, SettingsDep
from app.domain.leads.enums import LeadSource
from app.observability.context import get_request_id
from app.schemas.errors import ErrorResponse
from app.schemas.leads import LeadCreateRequest, LeadCreateResponse

router = APIRouter(prefix="/leads", tags=["leads"])


@router.post(
    "",
    response_model=LeadCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Capture a lead from the strategy-call form",
    responses={
        200: {
            "model": LeadCreateResponse,
            "description": (
                "The same idempotency key was already used. The original lead "
                "is returned and nothing new was written."
            ),
        },
        422: {"model": ErrorResponse, "description": "Validation failed."},
        429: {"model": ErrorResponse, "description": "Too many submissions."},
        503: {"model": ErrorResponse, "description": "No database configured."},
    },
)
async def create_lead(
    payload: LeadCreateRequest,
    request: Request,
    response: Response,
    service: LeadServiceDep,
    settings: SettingsDep,
    idempotency_key_header: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> LeadCreateResponse:
    """Capture, score and store one lead."""
    enforce_rate_limit(request, settings)

    # The HTTP-native spelling wins when both are present. The body field exists
    # because it survives proxies that strip unknown headers, and because it
    # keeps the contract visible in the OpenAPI schema.
    idempotency_key = idempotency_key_header or payload.idempotency_key

    command = CaptureLeadCommand(
        idempotency_key=idempotency_key,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=str(payload.email),
        company_name=payload.company_name,
        industry=payload.industry,
        monthly_revenue=payload.monthly_revenue,
        monthly_marketing_budget=payload.monthly_marketing_budget,
        content_volume=payload.content_volume,
        primary_goal=payload.primary_goal,
        start_timeline=payload.start_timeline,
        website=payload.website,
        phone=payload.phone,
        message=payload.message,
        source=LeadSource.WEBSITE,
        is_demo=False,
        attribution=AttributionCommand(
            utm_source=payload.attribution.utm_source,
            utm_medium=payload.attribution.utm_medium,
            utm_campaign=payload.attribution.utm_campaign,
            utm_content=payload.attribution.utm_content,
            utm_term=payload.attribution.utm_term,
            referrer=payload.attribution.referrer,
            landing_page=payload.attribution.landing_page,
        ),
    )

    result = await service.capture_lead(command, correlation_id=get_request_id())

    # 201 the first time, 200 on a replay. Both succeed from the visitor's point
    # of view — a double-click must never show an error — but the status code
    # tells an API consumer whether anything was actually created.
    if result.was_duplicate:
        response.status_code = status.HTTP_200_OK

    return LeadCreateResponse(id=result.id, created_at=result.created_at)
