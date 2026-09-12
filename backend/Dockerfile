# Fluxframe Media — backend image.
#
# Built by Railway from this directory (set the service's Root Directory to
# `backend`). You do not need Docker installed locally: `uv run uvicorn ...` is
# the local workflow, and Railway builds this for you.
#
# A Dockerfile rather than Railway's automatic Nixpacks detection, because an
# explicit build you can read beats a build system inferring one — particularly
# for a uv project, where auto-detection has historically been inconsistent.

# ---------------------------------------------------------------------------
# Builder — resolve and install dependencies into a self-contained virtualenv.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# uv, copied from its official image: faster and more reproducible than
# pip-installing it at build time.
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Copy only the dependency manifests first. Docker caches this layer, so an
# application code change does NOT trigger a full dependency reinstall — which
# is the difference between a 20-second deploy and a two-minute one.
COPY pyproject.toml uv.lock ./

# --frozen: fail if uv.lock is out of date with pyproject.toml, rather than
# silently resolving something different from what was tested.
# --no-dev: production images do not need pytest, ruff or mypy.
RUN uv sync --frozen --no-install-project --no-dev

COPY . .
RUN uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
# Runtime — a clean image with only the virtualenv and the application.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Run as a non-root user. If the process is ever compromised, it should not own
# the filesystem it is running on.
RUN useradd --create-home --uid 10001 fluxframe

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder --chown=fluxframe:fluxframe /app /app

USER fluxframe

EXPOSE 8000

# Railway injects $PORT and expects the process to bind it on 0.0.0.0.
# Binding 127.0.0.1 is the single most common reason a container "starts fine"
# and then fails every health check.
#
# `sh -c` so $PORT is expanded at runtime; the exec form would pass it literally.
# `--proxy-headers` makes X-Forwarded-For visible, which the rate limiter needs
# to see the real client rather than Railway's proxy.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
