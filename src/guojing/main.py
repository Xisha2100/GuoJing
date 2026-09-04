"""FastAPI composition root for the visual guidance agent backend."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import timedelta

from deepagents.backends.protocol import SandboxBackendProtocol
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from guojing.api.error_handlers import handle_request_validation_error
from guojing.api.middleware import AgentSecurityMiddleware
from guojing.api.router import api_router
from guojing.application.agent.coordinator import AgentRunCoordinator
from guojing.application.agent.ports import SandboxRegistry, VisualGuidanceAgent
from guojing.application.agent.service import AgentService
from guojing.core.config import Settings
from guojing.domain.agent_guidance import AgentSession, GuidanceDecision, GuidanceStep
from guojing.infrastructure.agents.deep_guidance_agent import DeepGuidanceAgent
from guojing.infrastructure.persistence.agent_repository import SqlAlchemyAgentRepository
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.sandbox.docker_backend import (
    DockerSandboxFactory,
    DockerSandboxRegistry,
)


class UnconfiguredGuidanceAgent:
    """Keep local health checks available until a model key is configured."""

    async def analyze(
        self,
        *,
        session: AgentSession,
        history: Sequence[GuidanceStep],
        screenshot: bytes,
        image_media_type: str,
        sandbox: SandboxBackendProtocol,
    ) -> GuidanceDecision:
        del session, history, screenshot, image_media_type, sandbox
        raise RuntimeError("DeepSeek is not configured")


def create_app(
    settings: Settings | None = None,
    *,
    agent_service: AgentService | None = None,
    visual_agent: VisualGuidanceAgent | None = None,
    sandbox_registry: SandboxRegistry | None = None,
    agent_coordinator: AgentRunCoordinator | None = None,
) -> FastAPI:
    """Build an isolated application instance for production or tests."""
    app_settings = settings or Settings()
    database: Database | None = None
    if agent_service is None:
        database = Database(app_settings.database_url)
        agent_service = AgentService(
            SqlAlchemyAgentRepository(database),
            session_ttl=timedelta(hours=app_settings.agent_session_ttl_hours),
        )
    if visual_agent is None:
        if app_settings.deepseek_api_key is None:
            visual_agent = UnconfiguredGuidanceAgent()
        else:
            visual_agent = DeepGuidanceAgent(
                api_key=app_settings.deepseek_api_key.get_secret_value(),
                base_url=app_settings.deepseek_base_url,
                model_name=app_settings.deepseek_vision_model,
                model_timeout_seconds=app_settings.deepseek_model_timeout_seconds,
                confidence_threshold=app_settings.agent_confidence_threshold,
            )
    if sandbox_registry is None:
        sandbox_registry = DockerSandboxRegistry(
            DockerSandboxFactory(
                docker_host=app_settings.sandbox_docker_host,
                image=app_settings.sandbox_image,
            ),
            idle_ttl_seconds=app_settings.sandbox_idle_ttl_seconds,
        )
    if agent_coordinator is None:
        agent_coordinator = AgentRunCoordinator(
            agent_service,
            visual_agent,
            sandbox_registry,
            maximum_concurrency=app_settings.agent_max_concurrency,
            queue_capacity=app_settings.agent_queue_capacity,
            run_timeout_seconds=app_settings.agent_run_timeout_seconds,
        )

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
        if isinstance(sandbox_registry, DockerSandboxRegistry):
            await sandbox_registry.start()
        await agent_coordinator.start()
        reaper = asyncio.create_task(_reap_sandboxes(sandbox_registry))
        try:
            yield
        finally:
            reaper.cancel()
            await asyncio.gather(reaper, return_exceptions=True)
            await agent_coordinator.stop()
            if database is not None:
                database.dispose()

    application = FastAPI(
        title=app_settings.app_name,
        debug=app_settings.debug,
        lifespan=lifespan,
    )
    application.add_middleware(AgentSecurityMiddleware)
    application.add_exception_handler(
        RequestValidationError,
        handle_request_validation_error,
    )
    application.state.settings = app_settings
    application.state.agent_service = agent_service
    application.state.agent_coordinator = agent_coordinator
    application.include_router(api_router)
    return application


async def _reap_sandboxes(registry: SandboxRegistry) -> None:
    while True:
        await asyncio.sleep(60)
        await registry.cleanup_idle()


app = create_app()
