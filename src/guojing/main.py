"""FastAPI composition root for the visual guidance agent backend."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import timedelta

from deepagents.backends.protocol import SandboxBackendProtocol
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response

from guojing.api.error_handlers import handle_request_validation_error
from guojing.api.middleware import AgentSecurityMiddleware, access_response
from guojing.api.router import api_router
from guojing.application.agent.coordinator import AgentRunCoordinator
from guojing.application.agent.ports import SandboxRegistry, VisualGuidanceAgent
from guojing.application.agent.service import AgentService
from guojing.application.device_access import DeviceAccessService
from guojing.core.config import AppEnvironment, Settings
from guojing.domain.agent_guidance import AgentSession, GuidanceDecision, GuidanceStep
from guojing.domain.device_access import AccessDenied
from guojing.infrastructure.agents.deep_guidance_agent import DeepGuidanceAgent
from guojing.infrastructure.persistence.agent_repository import SqlAlchemyAgentRepository
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.device_repository import SqlAlchemyDeviceRepository
from guojing.infrastructure.runtime import ProcessLease, database_ready
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
    database = Database(app_settings.database_url)
    lease = ProcessLease(app_settings.database_url)
    access = DeviceAccessService(
        SqlAlchemyDeviceRepository(database),
        maximum_devices=app_settings.device_maximum,
        device_limit=app_settings.device_daily_limit,
        global_limit=app_settings.global_daily_limit,
    )
    deployed = app_settings.environment in {AppEnvironment.PRODUCTION, AppEnvironment.STAGING}
    if agent_service is None:
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
                deployment_id=app_settings.deployment_id,
            ),
            idle_ttl_seconds=app_settings.sandbox_idle_ttl_seconds,
            maximum_containers=app_settings.agent_max_concurrency,
        )
    if agent_coordinator is None:
        agent_coordinator = AgentRunCoordinator(
            agent_service,
            visual_agent,
            sandbox_registry,
            maximum_concurrency=app_settings.agent_max_concurrency,
            queue_capacity=app_settings.agent_queue_capacity,
            run_timeout_seconds=app_settings.agent_run_timeout_seconds,
            queue_timeout_seconds=app_settings.agent_queue_timeout_seconds,
            cleanup_timeout_seconds=app_settings.sandbox_cleanup_timeout_seconds,
            access=access,
        )

    agent_coordinator.bind_access(access)

    async def dependencies_ready() -> bool:
        try:
            if not agent_coordinator.ready:
                return False
            if not database_ready(
                database,
                lease.directory,
                app_settings.minimum_free_disk_bytes,
                check_schema=app_settings.environment is not AppEnvironment.TEST,
            ):
                return False
            if isinstance(sandbox_registry, DockerSandboxRegistry):
                if app_settings.deepseek_api_key is None:
                    return False
                return await asyncio.wait_for(sandbox_registry.check_ready(deployed), timeout=5)
            return True
        except Exception:
            return False

    async def is_ready() -> bool:
        return await dependencies_ready() and access.accepting()

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
        lease.acquire()
        try:
            if isinstance(sandbox_registry, DockerSandboxRegistry):
                try:
                    await sandbox_registry.start()
                except Exception:
                    if deployed:
                        raise RuntimeError("Docker startup validation failed") from None
            await agent_coordinator.start()
            try:
                if deployed and not await dependencies_ready():
                    raise RuntimeError("production dependencies are not ready")
                yield
            finally:
                await agent_coordinator.stop()
        finally:
            database.dispose()
            lease.release()

    async def handle_access_error(_request: Request, error: Exception) -> Response:
        assert isinstance(error, AccessDenied)
        return access_response(error)

    application = FastAPI(
        title=app_settings.app_name,
        debug=app_settings.debug,
        lifespan=lifespan,
        docs_url=None if deployed else "/docs",
        redoc_url=None if deployed else "/redoc",
        openapi_url=None if deployed else "/openapi.json",
    )
    application.add_middleware(AgentSecurityMiddleware)
    application.add_exception_handler(AccessDenied, handle_access_error)
    application.add_exception_handler(
        RequestValidationError,
        handle_request_validation_error,
    )
    application.state.device_access = access
    application.state.is_ready = is_ready
    application.state.dependencies_ready = dependencies_ready
    application.state.settings = app_settings
    application.state.agent_service = agent_service
    application.state.agent_coordinator = agent_coordinator
    application.include_router(api_router)
    return application


app = create_app()
