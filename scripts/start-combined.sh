#!/usr/bin/env bash
#
# Start FastAPI and Next.js in one container.
#
# The job of this script is not just "run two things" — it is to make two
# processes behave like one, so that Railway's restart policy still means
# something:
#
#   * FastAPI comes up FIRST, on a private port, and we wait until it actually
#     answers before starting Next.js. Otherwise the first requests after a
#     deploy hit a proxy whose upstream does not exist yet, and the health check
#     can fail a deploy that was about to be fine.
#
#   * If EITHER process exits, the container exits. Without that, a dead backend
#     leaves a live frontend 502-ing every API call while Railway reports the
#     service as healthy — the worst possible failure mode, because nothing
#     alerts and nothing restarts.
#
#   * Signals are forwarded, so `docker stop` and Railway redeploys shut down
#     cleanly instead of being killed after the grace period.

set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-8000}"
# Absolute path to the venv interpreter, so nothing depends on PATH order.
VENV_PYTHON="${VENV_PYTHON:-/app/backend/.venv/bin/python}"
# Railway injects $PORT. 3000 is the local default.
FRONTEND_PORT="${PORT:-3000}"

log() { echo "[start] $*"; }

# --- shutdown ---------------------------------------------------------------

backend_pid=""
frontend_pid=""

shutdown() {
  log "shutting down"
  # Ignore failures: by the time we get here one of them is usually gone.
  [ -n "$backend_pid" ] && kill -TERM "$backend_pid" 2>/dev/null || true
  [ -n "$frontend_pid" ] && kill -TERM "$frontend_pid" 2>/dev/null || true
  wait 2>/dev/null || true
  exit 0
}
trap shutdown TERM INT

# --- backend ----------------------------------------------------------------

log "starting FastAPI on 127.0.0.1:${BACKEND_PORT}"
cd /app/backend

# Bound to 127.0.0.1 on purpose: the backend must NOT be reachable from outside
# the container. Everything public goes through Next.js, which is what makes
# the API same-origin with the site.
#
# --proxy-headers so X-Forwarded-For survives, which the rate limiter needs to
# see the real client rather than the proxy in front of it.
# `python -m uvicorn` rather than the `uvicorn` console script: invoking the
# module ignores the script's baked-in shebang entirely, so this keeps working
# even if the virtualenv is ever moved again.
"${VENV_PYTHON}" -m uvicorn app.main:app \
  --host 127.0.0.1 \
  --port "${BACKEND_PORT}" \
  --proxy-headers \
  --forwarded-allow-ips='*' &
backend_pid=$!

# --- wait for the backend to actually answer --------------------------------

log "waiting for the backend to become ready"
for attempt in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null 2>&1; then
    log "backend ready after ${attempt}s"
    break
  fi
  # If it died during startup, stop now and let the platform report a failed
  # deploy — rather than starting a frontend that proxies into nothing.
  if ! kill -0 "$backend_pid" 2>/dev/null; then
    log "ERROR: backend exited during startup"
    wait "$backend_pid" || true
    exit 1
  fi
  if [ "$attempt" -eq 60 ]; then
    log "ERROR: backend did not become ready within 60s"
    kill -TERM "$backend_pid" 2>/dev/null || true
    exit 1
  fi
  sleep 1
done

# --- frontend ---------------------------------------------------------------

log "starting Next.js on 0.0.0.0:${FRONTEND_PORT}"
cd /app/frontend

# HOSTNAME=0.0.0.0 is set in the Dockerfile. The standalone server defaults to
# localhost, and a container bound to localhost fails every health check while
# looking perfectly healthy in its own logs.
PORT="${FRONTEND_PORT}" node server.js &
frontend_pid=$!

log "both processes running (backend=${backend_pid} frontend=${frontend_pid})"

# --- supervise --------------------------------------------------------------

# `wait -n` returns as soon as EITHER child exits. That is what turns two
# processes into one unit of health: whichever one falls over, the container
# goes down and Railway restarts it.
wait -n "$backend_pid" "$frontend_pid"
exit_code=$?

log "a process exited (code ${exit_code}); stopping the container"
kill -TERM "$backend_pid" "$frontend_pid" 2>/dev/null || true
wait 2>/dev/null || true

# Exit non-zero so the platform treats this as a crash worth restarting, not a
# clean shutdown.
exit "${exit_code:-1}"
