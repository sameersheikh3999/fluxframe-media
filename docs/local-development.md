# Local development

Windows + PowerShell. No Docker required, and none is used.

## Prerequisites

| Tool | Version here | Notes |
|---|---|---|
| Python | 3.12 | pinned in `backend/.python-version`; 3.14 is also on this machine, so the pin matters |
| uv | 0.12+ | manages the backend virtualenv and lockfile |
| Node | 24 | |
| npm | 11 | |

Phase 0 needs **no database**, no Neon account and no HubSpot token. Everything
below runs offline after the first install.

## One-time setup

```powershell
cd backend
uv sync
copy .env.example .env

cd ..\frontend
npm install
copy .env.local.example .env.local
```

## Running

Two terminals.

```powershell
# Terminal 1 — backend
cd backend
uv run uvicorn app.main:app --reload --port 8000
```

```powershell
# Terminal 2 — frontend
cd frontend
npm run dev
```

| What | Where |
|---|---|
| Marketing site | http://localhost:3000 |
| Liveness | http://localhost:8000/api/v1/health |
| Readiness | http://localhost:8000/api/v1/health/ready |
| OpenAPI docs | http://localhost:8000/docs |
| OpenAPI schema | http://localhost:8000/openapi.json |

## Quality gates

These are exactly what CI runs. Run them before you commit.

```powershell
# Backend
cd backend
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run lint-imports
uv run pytest
```

```powershell
# Frontend
cd frontend
npm run lint
npm run typecheck
npm run build
```

### `lint-imports` is the interesting one

It enforces the architecture. To see it work, add this line to
`backend/app/api/v1/health.py`:

```python
from app.infrastructure.clock import SystemClock
```

then run `uv run lint-imports`. It fails and names the file and line number.
Remove the line and it passes again.

## Gotchas

**Run the frontend build before `tsc --noEmit` on a fresh clone.**
Next.js generates route type definitions into `.next/types/`. On a clean
checkout those do not exist yet, and `tsc` reports missing modules for routes
that are perfectly fine. `npm run build` (or one `npm run dev`) generates them.

**Line endings.** `.gitattributes` normalises everything to LF. You are on
Windows; CI and Railway are Linux. Without this every file gains a spurious diff
the first time CI touches it.

**The Python pin.** `py -3` on this machine resolves to 3.14. `uv run` respects
`backend/.python-version` and uses 3.12. Always go through `uv run`.

**Database inspection.** There is no `psql` installed, by choice — Phase 1 uses
the Neon web SQL editor for ad-hoc queries. Add a client later if the web editor
starts to chafe.

## Useful, not required

```powershell
uv run ruff check . --fix     # auto-fix lint
uv run ruff format .          # format
uv run pytest -v              # verbose test names
uv run pytest -m unit         # only the no-I/O tests
uv run pytest --lf            # re-run last failures
```
