"""Events published by the leads domain."""

from dataclasses import dataclass
from typing import ClassVar

from app.domain.shared.events import DomainEvent


@dataclass(frozen=True, slots=True)
class LeadCaptured(DomainEvent):
    """A new lead was stored.

    Written to the outbox in the same transaction as the lead itself. Its
    consumer (Phase 3) is the HubSpot sync.
    """

    event_type: ClassVar[str] = "LeadCaptured"
    aggregate_type: ClassVar[str] = "lead"


@dataclass(frozen=True, slots=True)
class LeadMarkedHot(DomainEvent):
    """A lead scored into the HOT band.

    Separate from LeadCaptured because the interesting consumers differ: this is
    what a "notify sales immediately" handler subscribes to, and later what
    triggers an AI research brief.
    """

    event_type: ClassVar[str] = "LeadMarkedHot"
    aggregate_type: ClassVar[str] = "lead"


@dataclass(frozen=True, slots=True)
class LeadStatusChanged(DomainEvent):
    """A lead moved through the sales lifecycle."""

    event_type: ClassVar[str] = "LeadStatusChanged"
    aggregate_type: ClassVar[str] = "lead"
