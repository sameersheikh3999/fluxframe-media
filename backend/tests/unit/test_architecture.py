"""Executable proof that the domain layer is pure.

`uv run lint-imports` checks this statically by reading import statements.
This test checks it dynamically, by actually importing app.domain in a clean
interpreter and asserting no framework was dragged in behind it.

The two catch different things. Static analysis misses an import hidden inside a
function body; a runtime check misses a branch that never executes. Both are
cheap, so we run both.
"""

import subprocess
import sys
import textwrap

import pytest

pytestmark = pytest.mark.unit

_FORBIDDEN_IN_DOMAIN = ("fastapi", "starlette", "pydantic", "sqlalchemy", "httpx", "structlog")


def test_importing_the_domain_pulls_in_no_frameworks() -> None:
    script = textwrap.dedent(
        f"""
        import sys
        import importlib
        import pkgutil

        import app.domain

        for module_info in pkgutil.walk_packages(app.domain.__path__, "app.domain."):
            importlib.import_module(module_info.name)

        leaked = sorted(
            name for name in sys.modules
            if name.split(".")[0] in {_FORBIDDEN_IN_DOMAIN!r}
        )
        print(",".join(leaked))
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
    )
    leaked = result.stdout.strip()

    assert leaked == "", (
        f"app.domain imported framework modules: {leaked}. "
        "Domain code must be runnable with no framework installed."
    )
