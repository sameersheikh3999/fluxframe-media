# =============================================================================
# Fluxframe Media — SINGLE-SERVICE image.
#
# Runs the Next.js frontend and the FastAPI backend in one container, on one
# Railway service, behind one domain.
#
#   Internet ──► Next.js (binds $PORT)
#                  ├── serves the marketing site and the dashboard
#                  └── rewrites /api/v1/*, /docs, /health
#                         │
#                         ▼
#                      FastAPI (127.0.0.1:8000, never exposed publicly)
#                         │
#                         ▼
#                      PostgreSQL
#
# WHY THIS SHAPE
#   Next.js is the front door rather than FastAPI, because it is already an
#   HTTP server that does static asset serving, streaming SSR and rewrites
#   well. Putting FastAPI in front would mean it proxying every .js and .woff2
#   file, which it has no business doing.
#
#   The payoff: the browser and the API share an origin, so CORS disappears
#   completely and NEXT_PUBLIC_API_URL — a build-time value that is easy to get
#   wrong — is not needed at all.
#
# WHAT THIS COSTS, STATED PLAINLY
#   * Two processes in one container. They cannot be scaled independently, and
#     the whole thing restarts if either dies.
#   * A larger image than either half alone (~Python + Node).
#   * `docs/decisions/0009-single-service-deployment.md` records the trade.
#
#   The two-service Dockerfiles in backend/ and frontend/ are still present and
#   still work. Switching back is a Railway settings change, not a code change.
# =============================================================================


# -----------------------------------------------------------------------------
# Stage 1 — build the Next.js frontend
# -----------------------------------------------------------------------------
FROM node:24-bookworm-slim AS frontend-builder

WORKDIR /build

# Manifests first, so this layer caches across application code changes.
COPY frontend/package.json frontend/package-lock.json ./
# `npm ci` installs exactly the lockfile and fails if it disagrees with
# package.json — the reproducibility `npm install` does not give you.
RUN npm ci

COPY frontend/ ./

# No NEXT_PUBLIC_API_URL build argument, deliberately.
#
# Leaving it unset makes `env.apiUrl` an empty string, which makes the browser
# post to "/api/v1/leads" on its own origin. That is the entire point of this
# deployment shape, and it removes the single most common Railway mistake:
# setting a NEXT_PUBLIC_* variable after the build and wondering why production
# still calls localhost.
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build


# -----------------------------------------------------------------------------
# Stage 2 — install the Python backend
# -----------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS backend-builder

# uv from its official image: faster and more reproducible than pip-installing
# it at build time.
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /build

COPY backend/pyproject.toml backend/uv.lock ./
# --frozen: fail if uv.lock disagrees with pyproject.toml, rather than quietly
# resolving something different from what was tested.
# --no-dev: production does not need pytest, ruff or mypy.
RUN uv sync --frozen --no-install-project --no-dev

COPY backend/ ./
RUN uv sync --frozen --no-dev


# -----------------------------------------------------------------------------
# Stage 3 — runtime: Python base, with the Node binary copied in
# -----------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# Node's standalone output ships its own node_modules, so the only thing needed
# from the Node image is the interpreter itself. Both images are bookworm-based,
# so the shared libraries it links against are present.
COPY --from=node:24-bookworm-slim /usr/local/bin/node /usr/local/bin/node

# curl            the startup script uses it to wait for the backend to be ready.
# libstdc++6      the Node binary links against these. python:slim does not
# libgcc-s1       guarantee them, and the failure mode is a container that builds
#                 perfectly and then dies on first start with a linker error.
# ca-certificates outbound TLS to HubSpot and Anthropic.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      curl \
      ca-certificates \
      libstdc++6 \
      libgcc-s1 \
 && rm -rf /var/lib/apt/lists/*

# Run as a non-root user. If the process is ever compromised, it should not own
# the filesystem it is running on.
RUN useradd --create-home --uid 10001 fluxframe

WORKDIR /app

# --- backend ---
COPY --from=backend-builder --chown=fluxframe:fluxframe /build /app/backend

# --- frontend (standalone output) ---
# The standalone server expects this exact layout: server.js at the root of the
# traced output, with .next/static and public/ beside it.
COPY --from=frontend-builder --chown=fluxframe:fluxframe /build/.next/standalone /app/frontend
COPY --from=frontend-builder --chown=fluxframe:fluxframe /build/.next/static /app/frontend/.next/static
COPY --from=frontend-builder --chown=fluxframe:fluxframe /build/public /app/frontend/public

COPY --chown=fluxframe:fluxframe scripts/start-combined.sh /app/start.sh
RUN chmod +x /app/start.sh

USER fluxframe

ENV PATH="/app/backend/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# The port FastAPI listens on inside the container. Never published.
ENV BACKEND_PORT=8000
ENV BACKEND_INTERNAL_URL=http://127.0.0.1:8000

# Next.js must bind the container's external interface. Binding localhost is
# the single most common reason a container "starts fine" and then fails every
# health check.
ENV HOSTNAME=0.0.0.0

EXPOSE 3000

CMD ["/app/start.sh"]
