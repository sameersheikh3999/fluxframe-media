"""The base type for domain events.

A domain event is a statement of fact about something that already happened,
named in the past tense: LeadCaptured, LeadQualified, HubSpotContactSynced. It
is not a command and not a callback — it is a record, and the only thing it
does is get written to a row.

Why events at all, when a service could just call HubSpot directly? Because the
service must not depend on who cares. Today one consumer syncs to HubSpot;
tomorrow another sends a Slack notification and a third asks an AI agent to
research the company. Each is added by registering a handler, with no change to
`LeadService`.

The `payload` is deliberately a plain dict: it gets serialised into a JSONB
column, and it must stay readable years later when the entity class that
produced it has changed shape. Storing anything richer would couple the event
log to today's code.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Something that happened, worth telling other parts of the system about."""

    #: Stable wire name, e.g. "LeadCaptured". Subclasses override it. The outbox
    #: dispatcher routes on this string, so it must never change casually.
    event_type: ClassVar[str] = "DomainEvent"

    #: Schema version of `payload`. Bump it when the payload shape changes, so a
    #: consumer reading an old row knows what it is looking at.
    event_version: ClassVar[int] = 1

    aggregate_id: UUID
    occurred_at: datetime
    payload: dict[str, object]
    event_id: UUID = field(default_factory=uuid4)

    #: Which kind of thing this happened to: "lead", later "deal", "client".
    aggregate_type: ClassVar[str] = "unknown"
