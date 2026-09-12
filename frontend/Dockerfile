# Fluxframe Media — frontend image.
#
# Built by Railway from this directory (set the service's Root Directory to
# `frontend`).
#
# Uses Next.js `output: "standalone"`, which traces exactly which node_modules
# files the app actually imports and copies only those. The result is a runtime
# image of tens of megabytes instead of hundreds.

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
FROM node:24-alpine AS deps
WORKDIR /app

# Manifests only, so this layer caches across application code changes.
COPY package.json package-lock.json ./
# `npm ci` installs exactly the lockfile, and fails if it disagrees with
# package.json — the reproducibility `npm install` does not give you.
RUN npm ci

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
FROM node:24-alpine AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* variables are inlined into the browser bundle at BUILD time, not
# read at runtime. They must therefore be present here, which is why Railway
# needs them set as build-time variables on this service — a common and
# confusing first-deploy failure, where the app builds fine and then calls
# http://localhost:8000 from production.
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_SITE_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL \
    NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
FROM node:24-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

# Non-root, for the same reason as the backend image.
RUN addgroup --system --gid 10001 nodejs \
 && adduser --system --uid 10001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0

# HOSTNAME=0.0.0.0 matters as much as the port: the standalone server defaults
# to localhost, and a container bound to localhost fails every health check
# while looking perfectly healthy in its own logs.
CMD ["node", "server.js"]
