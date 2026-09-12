"""Business-rule violations specific to leads."""

from app.domain.leads.enums import LeadStatus
from app.domain.shared.errors import DomainError


class IllegalLeadTransitionError(DomainError):
    """An attempt was made to move a lead to a status it cannot reach.

    Raised by the entity itself, which means it is enforced identically whether
    the request came from the public API, the dashboard, a background worker or
    a future AI agent. There is no path around it.
    """

    code = "illegal_lead_transition"

    def __init__(self, current: LeadStatus, requested: LeadStatus) -> None:
        super().__init__(f"A lead cannot move from '{current.value}' to '{requested.value}'.")
        self.current = current
        self.requested = requested


class InvalidLeadDataError(DomainError):
    """A lead was constructed with values the business considers meaningless."""

    code = "invalid_lead_data"
