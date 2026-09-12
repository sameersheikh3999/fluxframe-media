"""The audit trail for a lead.

Every meaningful thing that happens to a lead gets an activity row: it was
captured, it was scored, sales moved it to CONTACTED, HubSpot sync failed, an AI
brief was generated.

Why bother, when the `leads` table already holds the current state? Because
current state cannot answer "what happened to this lead, and who did it?" — and
that question is the whole job of the dashboard's timeline. It is also how a
future AI agent's actions stay auditable: an agent writes activities with
`actor="agent:LeadResearchAgent"`, and a human can see exactly what it did.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4


class ActivityType(StrEnum):
    """The kinds of things that happen to a lead."""

    CAPTURED = "captured"
    SCORED = "scored"
    STATUS_CHANGED = "status_changed"
    CRM_SYNCED = "crm_synced"
    CRM_SYNC_FAILED = "crm_sync_failed"
    CRM_SYNC_SKIPPED = "crm_sync_skipped"
    NOTE_ADDED = "note_added"
    AI_BRIEF_GENERATED = "ai_brief_generated"


#: Conventional actor strings. Free-form so future actors need no migration:
#: "system", "demo_generator", "user:sam", "agent:LeadResearchAgent".
ACTOR_SYSTEM = "system"
ACTOR_DEMO_GENERATOR = "demo_generator"


@dataclass(frozen=True, slots=True)
class LeadActivity:
    """One entry in a lead's timeline. Immutable: history is not edited."""

    lead_id: UUID
    activity_type: ActivityType
    description: str
    occurred_at: datetime
    actor: str = ACTOR_SYSTEM
    activity_metadata: dict[str, object] = field(default_factory=dict)
    id: UUID = field(default_factory=uuid4)

    @classmethod
    def captured(
        cls, lead_id: UUID, now: datetime, source: str, actor: str = ACTOR_SYSTEM
    ) -> "LeadActivity":
        return cls(
            lead_id=lead_id,
            activity_type=ActivityType.CAPTURED,
            description=f"Lead captured from {source}.",
            occurred_at=now,
            actor=actor,
            activity_metadata={"source": source},
        )

    @classmethod
    def scored(
        cls, lead_id: UUID, now: datetime, score: int, temperature: str, version: str
    ) -> "LeadActivity":
        return cls(
            lead_id=lead_id,
            activity_type=ActivityType.SCORED,
            description=f"Scored {score}/100 ({temperature.upper()}) by rules {version}.",
            occurred_at=now,
            activity_metadata={
                "score": score,
                "temperature": temperature,
                "score_version": version,
            },
        )

    @classmethod
    def status_changed(
        cls,
        lead_id: UUID,
        now: datetime,
        from_status: str,
        to_status: str,
        actor: str,
    ) -> "LeadActivity":
        return cls(
            lead_id=lead_id,
            activity_type=ActivityType.STATUS_CHANGED,
            description=f"Status moved from {from_status} to {to_status}.",
            occurred_at=now,
            actor=actor,
            activity_metadata={"from_status": from_status, "to_status": to_status},
        )
