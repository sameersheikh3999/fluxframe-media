"""Cross-cutting observability: structured logging and per-request context.

This package sits outside the layer stack on purpose, and that is a deliberate
decision rather than an oversight.

Logging is genuinely cross-cutting: the HTTP adapter logs, background workers
log, the composition root logs. Filing it under app.infrastructure would mean
either pretending only the composition root may log, or punching a hole in the
"API must not import infrastructure" rule on day one. Rules with exceptions
stop being rules.

What is NOT relaxed: app.domain and app.application must not import this
package either (enforced by .importlinter). Domain code does not log — it
returns results and raises errors, and the adapter that called it decides what
is worth recording. That constraint is what keeps domain functions pure enough
to test with no setup at all.
"""
