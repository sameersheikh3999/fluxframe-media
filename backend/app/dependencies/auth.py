"""Access control for the internal endpoints.

The dashboard and the demo generator are not public. They are protected by a
shared secret sent in a header, held only by the Next.js server — the browser
never sees it, because those pages are rendered server-side and the demo
generator posts through a Next.js route handler that attaches the header.

This is deliberately NOT enterprise authentication. There are no users, no
sessions, no password hashing and no JWTs, because this application has exactly
one operator and building an identity system for one person is how portfolio
projects die before they ship. What it does do is make the boundary explicit and
fail closed in production.

Local development with no secret set leaves these endpoints open, which is
convenient. Production refuses to boot without one (see config/settings.py).
"""

import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.config.settings import Settings
from app.dependencies.services import get_app_settings

INTERNAL_SECRET_HEADER = "X-Internal-Secret"


def require_internal_access(
    settings: Annotated[Settings, Depends(get_app_settings)],
    x_internal_secret: Annotated[str | None, Header(alias=INTERNAL_SECRET_HEADER)] = None,
) -> None:
    """Reject requests that do not carry the internal shared secret."""
    expected = settings.internal_api_secret.strip()

    if not expected:
        if settings.is_production:
            # Unreachable in practice: settings validation refuses to boot a
            # production process without a secret. Kept as defence in depth,
            # because "unreachable" and "never reached" are different things.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Internal access is not configured.",
            )
        return

    # Constant-time comparison. A plain `==` leaks the secret one character at a
    # time to anyone who can measure response latency precisely enough.
    if not x_internal_secret or not hmac.compare_digest(x_internal_secret, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid internal access credentials.",
        )
