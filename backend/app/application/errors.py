"""Errors raised by use cases, as opposed to by business rules.

The distinction is worth holding on to:

    DomainError       a business rule said no
                      ("a lead cannot move from WON back to NEW")

    ApplicationError  the use case could not be carried out
                      ("no lead exists with that id", "this key was already used")

Both are expected, both are the client's problem, and both are mapped to HTTP
status codes in exactly one place: app/api/errors.py.
"""


class ApplicationError(Exception):
    """Base class for use-case failures."""

    code: str = "application_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
