"""The root of Fluxframe's business-rule error hierarchy.

A DomainError means a business rule was violated: "a lead cannot move from WON
back to NEW", "a score must be between 0 and 100". It does NOT mean a database
was unreachable or JSON was malformed — those are infrastructure and transport
failures respectively, and they are represented elsewhere.

The domain deliberately knows nothing about HTTP status codes. The translation
from DomainError to an HTTP response happens once, in app/api/errors.py.
"""


class DomainError(Exception):
    """Base class for every violated business rule."""

    #: Stable, machine-readable identifier returned to API clients.
    #: Subclasses override it. Clients may branch on this; never on the message.
    code: str = "domain_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
