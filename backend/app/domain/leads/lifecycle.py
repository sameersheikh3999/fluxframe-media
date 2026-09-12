"""The lead lifecycle state machine.

```
                 ┌──────────────► DISQUALIFIED
                 │                (from anywhere non-terminal)
  NEW ──► QUALIFIED ──► CONTACTED ──► BOOKED ──► WON
   │          │             │            │
   └──────────┴─────────────┴────────────┴─────► LOST
```

Why a table rather than `if` statements scattered through services: because the
question "can this lead go from CONTACTED to WON?" then has exactly one answer,
in one place, testable in isolation — and every caller gets the same answer.
"""

from types import MappingProxyType

from app.domain.leads.enums import LeadStatus

#: Terminal states. Nothing leaves them. Reopening a lost lead is a new lead —
#: which keeps the history of what actually happened intact.
TERMINAL_STATUSES: frozenset[LeadStatus] = frozenset(
    {LeadStatus.WON, LeadStatus.LOST, LeadStatus.DISQUALIFIED}
)

_TRANSITIONS: dict[LeadStatus, frozenset[LeadStatus]] = {
    LeadStatus.NEW: frozenset(
        {
            LeadStatus.QUALIFIED,
            # Sales sometimes reaches out before formally qualifying.
            LeadStatus.CONTACTED,
            LeadStatus.LOST,
            LeadStatus.DISQUALIFIED,
        }
    ),
    LeadStatus.QUALIFIED: frozenset(
        {
            LeadStatus.CONTACTED,
            LeadStatus.BOOKED,
            LeadStatus.LOST,
            LeadStatus.DISQUALIFIED,
        }
    ),
    LeadStatus.CONTACTED: frozenset({LeadStatus.BOOKED, LeadStatus.LOST, LeadStatus.DISQUALIFIED}),
    LeadStatus.BOOKED: frozenset({LeadStatus.WON, LeadStatus.LOST, LeadStatus.DISQUALIFIED}),
    LeadStatus.WON: frozenset(),
    LeadStatus.LOST: frozenset(),
    LeadStatus.DISQUALIFIED: frozenset(),
}

#: Read-only at runtime: a caller cannot widen the rules by mutating the map.
ALLOWED_TRANSITIONS = MappingProxyType(_TRANSITIONS)


def can_transition(current: LeadStatus, requested: LeadStatus) -> bool:
    """Is moving from `current` to `requested` permitted?"""
    return requested in ALLOWED_TRANSITIONS[current]


def next_statuses(current: LeadStatus) -> frozenset[LeadStatus]:
    """Every status reachable from `current`. Drives the dashboard's controls."""
    return ALLOWED_TRANSITIONS[current]
