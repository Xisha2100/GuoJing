"""Composition root for HTTP routes."""

from fastapi import APIRouter

from guojing.api.health import router as health_router
from guojing.api.tutorials import router as tutorials_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(tutorials_router)
