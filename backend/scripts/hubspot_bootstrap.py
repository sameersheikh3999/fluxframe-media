"""Create Fluxframe's custom properties in a HubSpot portal.

Run this ONCE per HubSpot account, before enabling the integration:

    cd backend
    HUBSPOT_ACCESS_TOKEN=pat-xx-... uv run python scripts/hubspot_bootstrap.py

Why it exists: HubSpot custom properties do not create themselves. A portal that
has never had them defined rejects every sync with a 400 — which our error
classifier correctly calls PERMANENT, so those events dead-letter rather than
retrying forever. That is the right behaviour, and this script is the fix.

The script is idempotent: it checks for each property before creating it, so
running it twice is harmless. That matters because the realistic usage is
"run it, get a failure on one property, fix the token scope, run it again".

Required private-app scopes:
    crm.schemas.contacts.write    to create the properties
    crm.objects.contacts.write    for the sync itself
"""

import asyncio
import os
import sys

import httpx

# The script lives outside the app package, so make `app` importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.infrastructure.hubspot.mapper import (
    CUSTOM_PROPERTIES,
    PROPERTY_GROUP_LABEL,
    PROPERTY_GROUP_NAME,
)

BASE_URL = os.getenv("HUBSPOT_BASE_URL", "https://api.hubapi.com")
GROUPS_PATH = "/crm/v3/properties/contacts/groups"
PROPERTIES_PATH = "/crm/v3/properties/contacts"


async def ensure_group(client: httpx.AsyncClient) -> None:
    """Create the `fluxframe` property group if it is missing.

    The group is cosmetic but worth having: without it the custom properties
    scatter through HubSpot's "Other properties" section, where nobody finds
    them.
    """
    existing = await client.get(f"{BASE_URL}{GROUPS_PATH}/{PROPERTY_GROUP_NAME}")
    if existing.status_code == 200:
        print(f"  group '{PROPERTY_GROUP_NAME}' already exists")
        return

    response = await client.post(
        f"{BASE_URL}{GROUPS_PATH}",
        json={"name": PROPERTY_GROUP_NAME, "label": PROPERTY_GROUP_LABEL},
    )
    if response.is_success:
        print(f"  created group '{PROPERTY_GROUP_NAME}'")
    else:
        print(f"  ! group creation returned {response.status_code}: {response.text[:200]}")


async def ensure_property(
    client: httpx.AsyncClient, name: str, label: str, type_: str, field_type: str
) -> bool:
    """Create one property if it does not already exist. Returns True on success."""
    existing = await client.get(f"{BASE_URL}{PROPERTIES_PATH}/{name}")
    if existing.status_code == 200:
        print(f"  = {name} (already exists)")
        return True

    response = await client.post(
        f"{BASE_URL}{PROPERTIES_PATH}",
        json={
            "name": name,
            "label": label,
            "type": type_,
            "fieldType": field_type,
            "groupName": PROPERTY_GROUP_NAME,
        },
    )
    if response.is_success:
        print(f"  + {name}")
        return True

    print(f"  ! {name} failed ({response.status_code}): {response.text[:200]}")
    return False


async def main() -> int:
    token = os.getenv("HUBSPOT_ACCESS_TOKEN", "").strip()
    if not token:
        print("HUBSPOT_ACCESS_TOKEN is not set.\n")
        print("Create a Private App in HubSpot (Settings -> Integrations ->")
        print("Private Apps) with the crm.schemas.contacts.write and")
        print("crm.objects.contacts.write scopes, then run:\n")
        print("  HUBSPOT_ACCESS_TOKEN=pat-xx-... uv run python scripts/hubspot_bootstrap.py")
        return 1

    print(f"Bootstrapping HubSpot custom properties at {BASE_URL}\n")

    async with httpx.AsyncClient(
        timeout=20.0,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    ) as client:
        # Fail fast and clearly on a bad token, rather than producing eleven
        # identical 401s.
        probe = await client.get(f"{BASE_URL}{PROPERTIES_PATH}")
        if probe.status_code in (401, 403):
            print(f"HubSpot rejected the token ({probe.status_code}).")
            print("Check that it is a Private App token and that it has the")
            print("crm.schemas.contacts.write scope.")
            return 1

        await ensure_group(client)
        print()

        results = [
            await ensure_property(client, name, label, type_, field_type)
            for name, (label, type_, field_type) in CUSTOM_PROPERTIES.items()
        ]

    succeeded = sum(results)
    print(f"\n{succeeded}/{len(results)} properties ready.")

    if succeeded == len(results):
        print("\nHubSpot is ready. Set HUBSPOT_ACCESS_TOKEN on the backend service.")
        print("Any leads that dead-lettered while properties were missing can be")
        print("replayed from the dashboard, or via:")
        print("  POST /api/v1/admin/outbox/{event_id}/replay")
        return 0

    print("\nSome properties could not be created. Fix the errors above and re-run;")
    print("this script is idempotent, so running it again is safe.")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
