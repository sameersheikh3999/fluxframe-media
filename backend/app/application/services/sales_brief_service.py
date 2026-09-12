"""Generating an AI sales brief for a lead.

Where the AI sits in the architecture:

    API route -> SalesBriefService -> SalesBriefGenerator (port)
                                          |
                                          +-> AnthropicSalesBriefGenerator
                                              (infrastructure adapter)

The service orchestrates; it does not prompt. There is no prompt text in this
file, no JSON parsing, no model name, no retry logic against an HTTP API. All of
that lives in the adapter, behind the port, which is why swapping Claude for
another provider — or for a fine-tuned model later — touches one folder.

What the AI is allowed to do, and what it is not:

    ALLOWED     interpret the prospect's free-text message: what hurts, how
                urgent it sounds, which service to lead with, how to open the
                call.

    NOT ALLOWED change the score. Scoring is deterministic, versioned and
                explainable (app/domain/leads/scoring.py). An LLM that could
                move a lead from WARM to HOT would make the score unauditable
                and non-reproducible, which is the opposite of what a sales team
                needs. The brief is shown ALONGSIDE the score, never instead.

Every call is recorded in `ai_runs` with latency, token counts, cost estimate
and the prompt version — because an AI feature you cannot measure is an AI
feature you cannot improve.
"""

from datetime import datetime
from uuid import UUID

from app.application.dto.leads import SalesBriefView
from app.application.errors import (
    AiResponseError,
    AiUnavailableError,
    LeadNotFoundError,
)
from app.application.ports.ai_run_recorder import AiRunRecord, AiRunRecorder
from app.application.ports.clock import Clock
from app.application.ports.sales_brief_generator import (
    SalesBriefGenerator,
    SalesBriefRequest,
)
from app.application.ports.unit_of_work import UnitOfWork
from app.domain.leads.activities import ActivityType, LeadActivity

AI_FEATURE_SALES_BRIEF = "sales_brief"


class SalesBriefService:
    """Produces and stores an AI sales brief for one lead."""

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        generator: SalesBriefGenerator,
        recorder: AiRunRecorder,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._generator = generator
        self._recorder = recorder
        self._clock = clock

    @property
    def is_available(self) -> bool:
        """Whether AI briefs can be generated at all.

        The dashboard asks this so it can explain *why* the button is disabled
        rather than showing a control that fails when clicked.
        """
        return self._generator.is_configured

    async def generate_for_lead(
        self, lead_id: UUID, correlation_id: str | None = None
    ) -> SalesBriefView:
        """Generate a brief, store it on the lead, and record the AI run."""
        if not self._generator.is_configured:
            raise AiUnavailableError(
                "No AI provider is configured. Set ANTHROPIC_API_KEY to enable sales briefs."
            )

        async with self._uow:
            lead = await self._uow.leads.get(lead_id)
            if lead is None:
                raise LeadNotFoundError(f"No lead with id {lead_id}.")

            request = SalesBriefRequest(
                company_name=lead.contact.company_name,
                industry=lead.answers.industry.value,
                monthly_revenue=lead.answers.monthly_revenue.value,
                marketing_budget=lead.answers.monthly_marketing_budget.value,
                content_volume=lead.answers.content_volume.value,
                primary_goal=lead.answers.primary_goal.value,
                start_timeline=lead.answers.start_timeline.value,
                message=lead.answers.message,
                deterministic_score=lead.score or 0,
                deterministic_temperature=(
                    lead.temperature.value if lead.temperature else "unknown"
                ),
            )

        # The model call happens outside the transaction. An LLM request can
        # take ten seconds; holding a database connection open for that would
        # exhaust a small pool under any real load.
        started = self._clock.now()
        try:
            brief = await self._generator.generate(request)
        except (AiUnavailableError, AiResponseError) as exc:
            await self._recorder.record(
                AiRunRecord(
                    feature=AI_FEATURE_SALES_BRIEF,
                    lead_id=lead_id,
                    provider="anthropic",
                    model="unknown",
                    prompt_version="unknown",
                    status="failed",
                    error=str(exc),
                    latency_ms=int((self._clock.now() - started).total_seconds() * 1000),
                    correlation_id=correlation_id,
                    created_at=self._clock.now(),
                )
            )
            raise

        now = self._clock.now()
        view = SalesBriefView(
            summary=brief.summary,
            pain_points=brief.pain_points,
            urgency=brief.urgency,
            suggested_service=brief.suggested_service,
            opening_line=brief.opening_line,
            confidence=brief.confidence,
            model=brief.model,
            generated_at=now,
        )

        async with self._uow:
            stored = await self._uow.leads.get(lead_id)
            if stored is None:
                raise LeadNotFoundError(f"No lead with id {lead_id}.")
            await self._uow.activities.add(
                LeadActivity(
                    lead_id=lead_id,
                    activity_type=ActivityType.AI_BRIEF_GENERATED,
                    description=f"AI sales brief generated by {brief.model}.",
                    occurred_at=now,
                    actor="agent:SalesBriefAgent",
                    activity_metadata=_brief_metadata(view),
                )
            )
            await self._uow.commit()

        await self._recorder.record(
            AiRunRecord(
                feature=AI_FEATURE_SALES_BRIEF,
                lead_id=lead_id,
                provider="anthropic",
                model=brief.model,
                prompt_version=brief.prompt_version,
                status="succeeded",
                latency_ms=brief.latency_ms,
                input_tokens=brief.input_tokens,
                output_tokens=brief.output_tokens,
                correlation_id=correlation_id,
                created_at=now,
                output=_brief_metadata(view),
            )
        )

        return view

    async def get_existing(self, lead_id: UUID) -> SalesBriefView | None:
        """The most recent stored brief for a lead, if one exists.

        Briefs are read back from the activity timeline rather than a dedicated
        column: a brief IS an event in the lead's history, and storing it that
        way means regenerating keeps the old one instead of overwriting it.
        """
        async with self._uow:
            activities = await self._uow.activities.list_for_lead(lead_id)

        for activity in sorted(activities, key=lambda item: item.occurred_at, reverse=True):
            if activity.activity_type is ActivityType.AI_BRIEF_GENERATED:
                return _brief_from_metadata(activity.activity_metadata, activity.occurred_at)
        return None


def _brief_metadata(view: SalesBriefView) -> dict[str, object]:
    return {
        "summary": view.summary,
        "pain_points": list(view.pain_points),
        "urgency": view.urgency,
        "suggested_service": view.suggested_service,
        "opening_line": view.opening_line,
        "confidence": view.confidence,
        "model": view.model,
    }


def _brief_from_metadata(metadata: dict[str, object], occurred_at: datetime) -> SalesBriefView:
    raw_points = metadata.get("pain_points", [])
    points = tuple(str(p) for p in raw_points) if isinstance(raw_points, list) else ()
    return SalesBriefView(
        summary=str(metadata.get("summary", "")),
        pain_points=points,
        urgency=str(metadata.get("urgency", "unknown")),
        suggested_service=str(metadata.get("suggested_service", "")),
        opening_line=str(metadata.get("opening_line", "")),
        confidence=str(metadata.get("confidence", "unknown")),
        model=str(metadata.get("model", "unknown")),
        generated_at=occurred_at,
    )
