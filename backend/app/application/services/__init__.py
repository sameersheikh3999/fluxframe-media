"""Services — one class per cluster of related use cases.

A service method is a use case: ``capture_lead``, ``generate_demo_leads``,
``transition_lead_status``. It coordinates, it does not compute business rules
itself — those live in app.domain — and it does not perform I/O itself — that
happens through ports.

Every dependency is injected through ``__init__``. A service never imports
settings, never constructs an adapter, and never knows which adapter it got.
"""
