"""The anti-corruption layer: Fluxframe vocabulary -> HubSpot property names.

This is the ONLY file in the codebase that contains the strings `firstname`,
`lastname` and `fluxframe_lead_score`. Everything above it speaks about first
names and lead scores.

Custom properties are prefixed `fluxframe_` so they are obvious in a HubSpot
portal that may also hold properties from other tools, and so a bulk cleanup is
a single prefix search.

Important operational note: these custom properties do not create themselves.
A HubSpot account that has never had them defined will reject every sync with a
400 — which our error classifier correctly calls PERMANENT, so it dead-letters
rather than retrying forever. Run `scripts/hubspot_bootstrap.py` once per portal
to create them. The README covers this.
"""

from app.application.ports.crm_client import CrmContactUpsert

#: The property group these all live in, so they appear together in the HubSpot
#: contact record UI rather than scattered through "Other properties".
PROPERTY_GROUP_NAME = "fluxframe"
PROPERTY_GROUP_LABEL = "Fluxframe"

#: internal name -> (label, type, fieldType)
CUSTOM_PROPERTIES: dict[str, tuple[str, str, str]] = {
    "fluxframe_industry": ("Fluxframe Industry", "string", "text"),
    "fluxframe_monthly_revenue": ("Fluxframe Monthly Revenue", "string", "text"),
    "fluxframe_marketing_budget": ("Fluxframe Marketing Budget", "string", "text"),
    "fluxframe_content_volume": ("Fluxframe Content Volume", "string", "text"),
    "fluxframe_primary_goal": ("Fluxframe Primary Goal", "string", "text"),
    "fluxframe_start_timeline": ("Fluxframe Start Timeline", "string", "text"),
    "fluxframe_lead_score": ("Fluxframe Lead Score", "number", "number"),
    "fluxframe_lead_temperature": ("Fluxframe Lead Temperature", "string", "text"),
    "fluxframe_lead_source": ("Fluxframe Lead Source", "string", "text"),
    "fluxframe_demo_lead": ("Fluxframe Demo Lead", "string", "text"),
}


def to_hubspot_properties(contact: CrmContactUpsert) -> dict[str, str]:
    """Translate our contact into HubSpot's property dictionary.

    Every value is a string because that is what the HubSpot v3 API accepts,
    including for number-typed properties.
    """
    properties: dict[str, str] = {
        # HubSpot's own standard contact properties.
        "email": contact.email,
        "firstname": contact.first_name,
        "lastname": contact.last_name,
        "company": contact.company_name,
        # Fluxframe's custom properties.
        "fluxframe_industry": contact.industry,
        "fluxframe_monthly_revenue": contact.monthly_revenue,
        "fluxframe_marketing_budget": contact.marketing_budget,
        "fluxframe_content_volume": contact.content_volume,
        "fluxframe_primary_goal": contact.primary_goal,
        "fluxframe_start_timeline": contact.start_timeline,
        "fluxframe_lead_score": str(contact.lead_score),
        "fluxframe_lead_temperature": contact.lead_temperature,
        "fluxframe_lead_source": contact.lead_source,
        # Always set, so synthetic contacts are filterable in HubSpot even if
        # someone enables demo syncing by accident.
        "fluxframe_demo_lead": "true" if contact.is_demo else "false",
    }

    # Omit empty optionals rather than sending "": HubSpot treats an empty
    # string as an instruction to clear the field, which would wipe a real
    # phone number the sales team added by hand.
    if contact.phone:
        properties["phone"] = contact.phone
    if contact.website:
        properties["website"] = contact.website

    return properties
