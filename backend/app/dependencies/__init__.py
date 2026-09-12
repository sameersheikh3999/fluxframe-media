"""The composition root — where ports are bound to concrete adapters.

This is the ONLY package permitted to import both app.application and
app.infrastructure. Every other module names a port and receives whatever this
package decided to hand it.

Concentrating the wiring in one place is what makes the rest of the codebase
swappable. When Phase 1 replaces NotConfiguredProbe with a real database probe,
the change is three lines here, and nothing else in the application moves.
"""
