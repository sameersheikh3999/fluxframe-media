"""Assembles every v1 router into one object for app.main to mount.

New feature routers are registered here and nowhere else, which keeps the URL
surface of the API readable from a single file.
"""

from fastapi import APIRouter

from app.api.v1 import health

api_v1_router = APIRouter()
api_v1_router.include_router(health.router)

# Registered in later phases:
#   leads.router      POST /api/v1/leads                 (Phase 1)
#   dashboard.router  GET  /api/v1/dashboard/leads       (Phase 2)
#   demo.router       POST /api/v1/demo/leads            (Phase 4)
