"""The synthetic lead generator endpoint.

Behind the internal secret and behind a config flag, because it is a write
endpoint that creates real database rows. Two independent switches: forgetting
one still leaves the other.

The architectural rule this endpoint exists to honour: synthetic leads go
through the SAME LeadService as the public form. There is no bulk-insert
shortcut. A demo batch is therefore a genuine end-to-end exercise of the
production path — it scores with the real scorer, writes real activity rows and
emits real outbox events.
"""

from fastapi import APIRouter, Depends, status

from app.application.services.demo_lead_service import GenerateDemoLeadsCommand
from app.dependencies.auth import require_internal_access
from app.dependencies.services import DemoLeadServiceDep
from app.observability.context import get_request_id
from app.schemas.demo import (
    GenerateDemoLeadsRequest,
    GenerateDemoLeadsResponse,
    GeneratedLeadResponse,
)
from app.schemas.errors import ErrorResponse

router = APIRouter(
    prefix="/demo",
    tags=["demo"],
    dependencies=[Depends(require_internal_access)],
    responses={401: {"model": ErrorResponse, "description": "Not authorised."}},
)


@router.post(
    "/leads",
    response_model=GenerateDemoLeadsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate synthetic demo leads",
    responses={
        403: {
            "model": ErrorResponse,
            "description": "The demo generator is disabled (ENABLE_DEMO_GENERATOR).",
        },
        422: {"model": ErrorResponse, "description": "Batch too large."},
    },
)
async def generate_demo_leads(
    payload: GenerateDemoLeadsRequest, service: DemoLeadServiceDep
) -> GenerateDemoLeadsResponse:
    """Create a batch of coherent synthetic leads.

    Every generated lead has `is_demo = true`, `source = demo_generator` and an
    @example.com address (RFC 2606, permanently reserved), so synthetic data can
    never reach a real person's inbox or be mistaken for a real prospect.
    """
    result = await service.generate(
        GenerateDemoLeadsCommand(
            count=payload.count,
            quality=payload.quality,
            scenario=payload.scenario,
            industry=payload.industry,
            seed=payload.seed,
        ),
        correlation_id=get_request_id(),
    )
    return GenerateDemoLeadsResponse(
        generated=[
            GeneratedLeadResponse(
                lead_id=item.lead_id,
                full_name=item.full_name,
                company_name=item.company_name,
                email=item.email,
                industry=item.industry,
                intended_temperature=item.intended_temperature,
            )
            for item in result.generated
        ],
        requested=result.requested,
        message=f"Generated {len(result.generated)} demo leads.",
    )
