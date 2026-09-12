"""The HubSpot adapter. Satisfies app.application.ports.crm_client.CrmClient.

The single most important design choice in this file is the endpoint:

    POST /crm/v3/objects/contacts/batch/upsert   with idProperty="email"

HubSpot's batch upsert is *natively idempotent* — create-or-update keyed on
email, in one call. The obvious alternative (POST to create, catch 409, then
PATCH) has a race between the two calls and two separate failure modes, and it
is how duplicate contacts appear in a CRM.

Since the outbox guarantees at-least-once delivery, this method WILL be called
twice for the same lead eventually. Choosing an endpoint that is idempotent by
construction means the second call is simply an update. At-least-once delivery
plus an idempotent consumer is effectively-once, with none of the machinery.

The client is stateless apart from a shared `httpx.AsyncClient`, which is
created once in the application lifespan. Creating one per request would throw
away every TLS handshake and connection.
"""

import httpx

from app.application.errors import CrmNotConfiguredError
from app.application.ports.crm_client import CrmContactRef, CrmContactUpsert
from app.infrastructure.hubspot.errors import classify_exception, classify_response
from app.infrastructure.hubspot.mapper import to_hubspot_properties
from app.observability.logging import get_logger

_logger = get_logger(__name__)

DEFAULT_BASE_URL = "https://api.hubapi.com"
UPSERT_PATH = "/crm/v3/objects/contacts/batch/upsert"


class HubSpotClient:
    """Upserts contacts into HubSpot."""

    def __init__(
        self,
        *,
        access_token: str | None,
        http_client: httpx.AsyncClient,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self._token = access_token
        self._http = http_client
        self._base_url = base_url.rstrip("/")

    @property
    def is_configured(self) -> bool:
        """No token is a normal state, not a fault.

        Lead capture must never depend on the CRM, so an unconfigured client
        means syncs are marked `skipped` and the website keeps working. This is
        what lets the whole application run on Railway before you have wired up
        HubSpot at all.
        """
        return bool(self._token)

    async def upsert_contact(self, contact: CrmContactUpsert) -> CrmContactRef:
        """Create or update one contact, keyed on email."""
        if not self._token:
            raise CrmNotConfiguredError("HUBSPOT_ACCESS_TOKEN is not set.")

        payload = {
            "inputs": [
                {
                    # Upsert on email rather than on HubSpot's internal id: we
                    # do not know the id on a first sync, and email is the
                    # natural key a CRM already deduplicates on.
                    "idProperty": "email",
                    "id": contact.email,
                    "properties": to_hubspot_properties(contact),
                }
            ]
        }

        try:
            response = await self._http.post(
                f"{self._base_url}{UPSERT_PATH}",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
            )
        except Exception as exc:
            raise classify_exception(exc) from exc

        error = classify_response(response)
        if error is not None:
            _logger.warning(
                "hubspot_upsert_failed",
                status_code=response.status_code,
                permanent=type(error).__name__ == "CrmPermanentError",
            )
            raise error

        contact_id = _extract_contact_id(response)
        _logger.info("hubspot_upsert_succeeded", contact_id=contact_id)
        return CrmContactRef(contact_id=contact_id)


def _extract_contact_id(response: httpx.Response) -> str:
    """Pull the contact id out of a batch-upsert response.

    Defensive on purpose: a shape change in HubSpot's response should surface
    as a clear error here rather than as a `KeyError` deep in a retry loop.
    """
    try:
        body = response.json()
        results = body.get("results") or []
        if results and isinstance(results, list):
            first = results[0]
            identifier = first.get("id")
            if identifier:
                return str(identifier)
    except Exception:  # pragma: no cover - defensive
        pass
    return "unknown"


class NullCrmClient:
    """A CRM client for when no CRM is configured.

    Used when HUBSPOT_ACCESS_TOKEN is absent. It is not a mock and not a
    placeholder: reporting `is_configured = False` is the documented, supported
    way to run Fluxframe without a CRM, and CrmSyncService reads that property
    and marks syncs `skipped`. The application is fully functional in this mode
    — which is exactly what a first Railway deploy looks like.
    """

    @property
    def is_configured(self) -> bool:
        return False

    async def upsert_contact(self, contact: CrmContactUpsert) -> CrmContactRef:
        raise CrmNotConfiguredError("No CRM is configured.")
