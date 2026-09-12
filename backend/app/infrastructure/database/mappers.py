"""Translation between ORM rows and domain entities.

This module is the price of keeping the domain free of SQLAlchemy, and it is
worth being explicit about that trade. The alternative — making `Lead` a
SQLAlchemy model — removes this file and, with it, the ability to unit-test the
domain without a database, plus the guarantee that a business rule cannot
accidentally trigger a query.

Everything here is a pure function. No session, no I/O.
"""

from typing import Any
from uuid import UUID

from app.domain.leads.activities import ActivityType, LeadActivity
from app.domain.leads.entities import (
    Attribution,
    ContactDetails,
    Lead,
    QualificationAnswers,
)
from app.domain.leads.enums import (
    ContentVolume,
    CrmSyncStatus,
    Industry,
    LeadSource,
    LeadStatus,
    LeadTemperature,
    MarketingBudget,
    MonthlyRevenue,
    PrimaryGoal,
    StartTimeline,
)
from app.infrastructure.database.models import LeadActivityModel, LeadModel


def lead_to_domain(row: LeadModel) -> Lead:
    """ORM row -> domain entity."""
    return Lead(
        id=row.id,
        idempotency_key=row.idempotency_key,
        contact=ContactDetails(
            first_name=row.first_name,
            last_name=row.last_name,
            email=row.email,
            company_name=row.company_name,
            website=row.website,
            phone=row.phone,
        ),
        answers=QualificationAnswers(
            industry=Industry(row.industry),
            monthly_revenue=MonthlyRevenue(row.monthly_revenue),
            monthly_marketing_budget=MarketingBudget(row.monthly_marketing_budget),
            content_volume=ContentVolume(row.content_volume),
            primary_goal=PrimaryGoal(row.primary_goal),
            start_timeline=StartTimeline(row.start_timeline),
            message=row.message,
        ),
        attribution=Attribution(
            utm_source=row.utm_source,
            utm_medium=row.utm_medium,
            utm_campaign=row.utm_campaign,
            utm_content=row.utm_content,
            utm_term=row.utm_term,
            referrer=row.referrer,
            landing_page=row.landing_page,
        ),
        source=LeadSource(row.source),
        is_demo=row.is_demo,
        created_at=row.created_at,
        updated_at=row.updated_at,
        status=LeadStatus(row.status),
        score=row.lead_score,
        temperature=(LeadTemperature(row.lead_temperature) if row.lead_temperature else None),
        score_version=row.score_version,
        score_breakdown=row.score_breakdown,
        crm_sync_status=CrmSyncStatus(row.hubspot_sync_status),
        crm_contact_id=row.hubspot_contact_id,
        crm_synced_at=row.hubspot_synced_at,
        crm_sync_error=row.hubspot_sync_error,
        crm_sync_attempts=row.hubspot_sync_attempts,
    )


def lead_to_row(lead: Lead) -> LeadModel:
    """Domain entity -> a new ORM row."""
    row = LeadModel(id=lead.id, idempotency_key=lead.idempotency_key)
    apply_lead_to_row(lead, row)
    return row


def apply_lead_to_row(lead: Lead, row: LeadModel) -> None:
    """Copy a domain entity's state onto an existing row.

    Used for updates. Writing every field rather than diffing keeps the mapping
    obvious: there is no question about which changes get persisted.
    """
    row.first_name = lead.contact.first_name
    row.last_name = lead.contact.last_name
    row.email = lead.contact.email
    row.phone = lead.contact.phone
    row.company_name = lead.contact.company_name
    row.website = lead.contact.website

    row.industry = lead.answers.industry.value
    row.monthly_revenue = lead.answers.monthly_revenue.value
    row.monthly_marketing_budget = lead.answers.monthly_marketing_budget.value
    row.content_volume = lead.answers.content_volume.value
    row.primary_goal = lead.answers.primary_goal.value
    row.start_timeline = lead.answers.start_timeline.value
    row.message = lead.answers.message

    row.lead_score = lead.score
    row.lead_temperature = lead.temperature.value if lead.temperature else None
    row.score_version = lead.score_version
    row.score_breakdown = _as_json_dict(lead.score_breakdown)

    row.status = lead.status.value
    row.source = lead.source.value
    row.is_demo = lead.is_demo

    row.utm_source = lead.attribution.utm_source
    row.utm_medium = lead.attribution.utm_medium
    row.utm_campaign = lead.attribution.utm_campaign
    row.utm_content = lead.attribution.utm_content
    row.utm_term = lead.attribution.utm_term
    row.referrer = lead.attribution.referrer
    row.landing_page = lead.attribution.landing_page

    row.hubspot_contact_id = lead.crm_contact_id
    row.hubspot_sync_status = lead.crm_sync_status.value
    row.hubspot_sync_attempts = lead.crm_sync_attempts
    row.hubspot_synced_at = lead.crm_synced_at
    row.hubspot_sync_error = lead.crm_sync_error

    row.created_at = lead.created_at
    row.updated_at = lead.updated_at


def activity_to_row(activity: LeadActivity) -> LeadActivityModel:
    return LeadActivityModel(
        id=activity.id,
        lead_id=activity.lead_id,
        activity_type=activity.activity_type.value,
        description=activity.description,
        actor=activity.actor,
        activity_metadata=dict(activity.activity_metadata),
        occurred_at=activity.occurred_at,
    )


def activity_to_domain(row: LeadActivityModel) -> LeadActivity:
    return LeadActivity(
        id=row.id,
        lead_id=row.lead_id,
        activity_type=ActivityType(row.activity_type),
        description=row.description,
        actor=row.actor,
        activity_metadata=dict(row.activity_metadata or {}),
        occurred_at=row.occurred_at,
    )


def _as_json_dict(value: dict[str, object] | None) -> dict[str, Any] | None:
    """Widen the domain's `dict[str, object]` to what the JSON column expects."""
    if value is None:
        return None
    return dict(value)


def parse_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(value)
