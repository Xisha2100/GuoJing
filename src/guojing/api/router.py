"""Composition root for HTTP routes."""

from fastapi import APIRouter

from guojing.api.agent import router as agent_router
from guojing.api.devices import router as devices_router
from guojing.api.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(agent_router)
api_router.include_router(devices_router)
