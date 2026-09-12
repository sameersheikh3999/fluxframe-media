"""Assembles every v1 router into one object for app.main to mount.

New feature routers are registered here and nowhere else, which keeps the whole
URL surface of the API readable from a single file.
"""

from fastapi import APIRouter

from app.api.v1 import admin, dashboard, demo, health, leads

api_v1_router = APIRouter()

# Public — reachable from the browser, CORS-allowlisted.
api_v1_router.include_router(health.router)
api_v1_router.include_router(leads.router)

# Internal — each of these carries Depends(require_internal_access).
api_v1_router.include_router(dashboard.router)
api_v1_router.include_router(demo.router)
api_v1_router.include_router(admin.router)
