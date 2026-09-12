"""Generating synthetic leads for demonstration.

The single most important line in this file is the one that calls
`self._lead_service.capture_lead(...)`.

The tempting shortcut would be a bulk INSERT straight into the leads table. It
would be faster and simpler, and it would be worthless — synthetic leads would
exercise none of the real application. They would not be scored by the real
scorer, would not write activity rows, would not produce outbox events, and
would not surface a bug in any of them.

Routing demo leads through the same service as the public form means:

    Website form  ──┐
                    ├──► LeadService.capture_lead ──► domain ──► database
    Demo generator ─┘

so a demo batch is a genuine end-to-end exercise of the production path. The
only differences are `is_demo=True`, `source=demo_generator` and an @example.com
address.
"""

import random
import uuid
from dataclasses import dataclass

from app.application.demo.personas import build_persona
from app.application.dto.demo import DemoQuality, DemoScenario
from app.application.dto.leads import AttributionCommand, CaptureLeadCommand
from app.application.errors import (
    DemoBatchTooLargeError,
    DemoGeneratorDisabledError,
)
from app.application.services.lead_service import LeadService
from app.domain.leads.enums import Industry, LeadSource


@dataclass(frozen=True, slots=True)
class GenerateDemoLeadsCommand:
    count: int
    quality: DemoQuality = DemoQuality.RANDOM
    scenario: DemoScenario = DemoScenario.NORMAL_WEEK
    industry: Industry | None = None
    #: Set for reproducible batches (the distribution test relies on this).
    seed: int | None = None


@dataclass(frozen=True, slots=True)
class GeneratedLeadSummary:
    lead_id: str
    full_name: str
    company_name: str
    email: str
    industry: str
    intended_temperature: str


@dataclass(frozen=True, slots=True)
class GenerateDemoLeadsResult:
    generated: tuple[GeneratedLeadSummary, ...]
    requested: int


class DemoLeadService:
    """Creates synthetic leads through the real capture path."""

    def __init__(
        self,
        *,
        lead_service: LeadService,
        enabled: bool,
        max_batch_size: int,
    ) -> None:
        self._lead_service = lead_service
        self._enabled = enabled
        self._max_batch_size = max_batch_size

    async def generate(
        self,
        command: GenerateDemoLeadsCommand,
        correlation_id: str | None = None,
    ) -> GenerateDemoLeadsResult:
        """Generate and capture a batch of synthetic leads."""
        if not self._enabled:
            raise DemoGeneratorDisabledError(
                "The demo generator is disabled. Set ENABLE_DEMO_GENERATOR=true."
            )
        if command.count < 1:
            raise DemoBatchTooLargeError("Count must be at least 1.")
        if command.count > self._max_batch_size:
            raise DemoBatchTooLargeError(
                f"A demo batch may contain at most {self._max_batch_size} leads."
            )

        rng = random.Random(command.seed)
        # A batch-unique suffix keeps emails distinct across repeated runs while
        # staying readable: sarah.morgan.demo001@example.com
        batch_tag = uuid.uuid4().hex[:6]

        summaries: list[GeneratedLeadSummary] = []
        for index in range(command.count):
            persona = build_persona(
                rng,
                quality=command.quality,
                scenario=command.scenario,
                industry=command.industry,
                sequence=index + 1,
            )
            email = persona.email.replace("@example.com", f".{batch_tag}@example.com")

            # Exactly the same command object the public API builds.
            capture = CaptureLeadCommand(
                # A fresh key per synthetic lead: these are genuinely new
                # submissions, not retries, so they must not deduplicate.
                idempotency_key=f"demo-{batch_tag}-{index + 1}",
                first_name=persona.first_name,
                last_name=persona.last_name,
                email=email,
                company_name=persona.company_name,
                industry=persona.industry,
                monthly_revenue=persona.monthly_revenue,
                monthly_marketing_budget=persona.monthly_marketing_budget,
                content_volume=persona.content_volume,
                primary_goal=persona.primary_goal,
                start_timeline=persona.start_timeline,
                website=persona.website,
                phone=persona.phone,
                message=persona.message,
                source=LeadSource.DEMO_GENERATOR,
                is_demo=True,
                attribution=AttributionCommand(
                    utm_source=persona.utm_source,
                    utm_medium=persona.utm_medium,
                    utm_campaign=persona.utm_campaign,
                    landing_page="/book-call",
                    referrer="https://demo.fluxframe.example.com",
                ),
            )

            # One transaction per lead, deliberately. Lead seven failing must
            # not roll back leads one to six — which is exactly the case a
            # single request-scoped session would handle badly.
            result = await self._lead_service.capture_lead(capture, correlation_id)

            summaries.append(
                GeneratedLeadSummary(
                    lead_id=str(result.id),
                    full_name=f"{persona.first_name} {persona.last_name}",
                    company_name=persona.company_name,
                    email=email,
                    industry=persona.industry.value,
                    intended_temperature=persona.intended_temperature.value,
                )
            )

        return GenerateDemoLeadsResult(generated=tuple(summaries), requested=command.count)
