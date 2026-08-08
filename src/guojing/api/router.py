"""Composition root for HTTP routes."""

from fastapi import APIRouter

from guojing.api.admin_auth import router as admin_auth_router
from guojing.api.health import router as health_router
from guojing.api.tutorial_drafts import router as tutorial_drafts_router
from guojing.api.tutorials import router as tutorials_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(admin_auth_router)
api_router.include_router(tutorial_drafts_router)
api_router.include_router(tutorials_router)
