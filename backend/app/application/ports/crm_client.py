"""Port: synchronising a lead into an external CRM.

Notice the vocabulary. This port talks about *contacts* and *leads*, never about
`firstname`, `hs_object_id` or `properties`. Those words belong to HubSpot, and
they live in exactly one folder: app/infrastructure/hubspot/.

That is an anti-corruption layer. It is what makes "swap HubSpot for Pipedrive"
a one-folder job instead of a search-and-replace across the codebase, and it is
why `LeadService` has no opinion about which CRM the agency uses.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CrmContactUpsert:
    """A contact to create-or-update, in Fluxframe's own language."""

    email: str
    first_name: str
    last_name: str
    company_name: str
    phone: str | None
    website: str | None
    industry: str
    monthly_revenue: str
    marketing_budget: str
    content_volume: str
    primary_goal: str
    start_timeline: str
    lead_score: int
    lead_temperature: str
    lead_source: str
    is_demo: bool


@dataclass(frozen=True, slots=True)
class CrmContactRef:
    """The CRM's identifier for a contact we synced."""

    contact_id: str


class CrmClient(Protocol):
    """Create or update a contact in the CRM.

    Implementations MUST be idempotent: the outbox delivers at least once, so
    this will be called twice for the same lead sooner or later. The HubSpot
    adapter achieves that by upserting on email rather than blind-creating.
    """

    async def upsert_contact(self, contact: CrmContactUpsert) -> CrmContactRef:
        """Upsert and return the CRM id.

        Raises CrmTransientError when a retry might succeed (429, 5xx, timeout)
        and CrmPermanentError when it never will (400, 401, 403). That
        distinction is what the dispatcher's retry policy is built on.
        """
        ...

    @property
    def is_configured(self) -> bool:
        """False when no credential is present.

        Lead capture must never depend on the CRM, so an unconfigured client is
        a normal state, not an error: the sync is marked `skipped` and the site
        keeps working.
        """
        ...
