"""Ports — what the application needs from the outside world, as Protocols.

A port is an interface expressed as a ``typing.Protocol``. Concrete adapters in
app.infrastructure satisfy it *structurally*: they do not subclass it and they
do not import it. mypy verifies conformance where the two are wired together,
in app.dependencies.

Why Protocol rather than ABC:
    An ABC forces the adapter to import the application layer in order to
    inherit from it. That edge is legal under our dependency rule, but it is an
    edge we do not need — and it makes writing a fake in a test heavier, because
    the fake must inherit too. With Protocol, a fake is any class with the right
    methods.

The cost of this choice: a signature mismatch is caught by mypy, not at import
time. That is why `uv run mypy app` is a required gate, not an optional one.
"""
