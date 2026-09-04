import time
from typing import Any, cast
from uuid import uuid4

import pytest

from guojing.infrastructure.sandbox.docker_backend import (
    DockerSandboxBackend,
    DockerSandboxFactory,
    DockerSandboxRegistry,
)


class FakeContainerCollection:
    def __init__(self) -> None:
        self.arguments: dict[str, Any] = {}
        self.container = FakeContainer()

    def run(self, image: str, command: list[str], **kwargs: Any) -> "FakeContainer":
        self.arguments = {"image": image, "command": command, **kwargs}
        return self.container


class FakeContainer:
    id = "sandbox-container"


class FakeDockerClient:
    def __init__(self) -> None:
        self.containers = FakeContainerCollection()


def test_factory_applies_isolation_and_resource_limits() -> None:
    client = FakeDockerClient()
    factory = DockerSandboxFactory(docker_host=None, image="guojing-sandbox:test")
    factory._client = client

    backend = factory.create(uuid4())

    options = client.containers.arguments
    assert backend.id == "sandbox-container"
    assert options["network_disabled"] is True
    assert options["read_only"] is True
    assert options["nano_cpus"] == 500_000_000
    assert options["mem_limit"] == "512m"
    assert options["pids_limit"] == 64
    assert options["cap_drop"] == ["ALL"]
    assert options["security_opt"] == ["no-new-privileges:true"]
    assert options["user"] == "65532:65532"
    assert options["environment"] == {}
    assert options["working_dir"] == "/workspace"
    assert "volumes" not in options
    assert "/workspace" in options["tmpfs"]


class FakeExecApi:
    def __init__(self) -> None:
        self.command: list[str] = []

    def exec_create(self, _container_id: str, command: list[str], **_kwargs: Any) -> dict[str, str]:
        self.command = command
        return {"Id": "exec-id"}

    def exec_start(self, _exec_id: str, **_kwargs: Any) -> list[bytes]:
        return [b"12345", b"67890"]

    def exec_inspect(self, _exec_id: str) -> dict[str, int]:
        return {"ExitCode": 0}


class FakeExecClient:
    def __init__(self) -> None:
        self.api = FakeExecApi()


def test_execute_caps_timeout_and_output() -> None:
    client = FakeExecClient()
    backend = DockerSandboxBackend(
        client,
        FakeContainer(),
        command_timeout_seconds=10,
        maximum_output_bytes=7,
    )

    response = backend.execute("printf safe", timeout=60)

    assert "timeout -s KILL 10s" in client.api.command[-1]
    assert response.output == "1234567"
    assert response.exit_code == 0
    assert response.truncated is True


def test_upload_rejects_host_and_parent_paths() -> None:
    backend = DockerSandboxBackend(FakeExecClient(), FakeContainer())

    responses = backend.upload_files(
        [("/etc/passwd", b"secret"), ("/workspace/../escape", b"secret")]
    )

    assert [response.error for response in responses] == ["invalid_path", "invalid_path"]


class RegistryBackend:
    def __init__(self, backend_id: str) -> None:
        self.id = backend_id
        self.destroyed = False

    def destroy(self) -> None:
        self.destroyed = True


class RegistryFactory:
    def __init__(self) -> None:
        self.created: list[RegistryBackend] = []
        self.cleaned = False
        self.closed = False

    def create(self, _session_id: object) -> RegistryBackend:
        backend = RegistryBackend(str(len(self.created)))
        self.created.append(backend)
        return backend

    def cleanup_orphans(self) -> None:
        self.cleaned = True

    def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_registry_isolates_sessions_and_reaps_idle_containers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = RegistryFactory()
    registry = DockerSandboxRegistry(
        cast(DockerSandboxFactory, factory),
        idle_ttl_seconds=60,
    )
    session_one = uuid4()
    session_two = uuid4()
    monkeypatch.setattr(time, "monotonic", lambda: 100.0)

    await registry.start()
    first = await registry.acquire(session_one)
    repeated = await registry.acquire(session_one)
    second = await registry.acquire(session_two)
    monkeypatch.setattr(time, "monotonic", lambda: 161.0)
    await registry.cleanup_idle()

    assert factory.cleaned is True
    assert first is repeated
    assert first is not second
    assert all(backend.destroyed for backend in factory.created)
    await registry.close()
    assert factory.closed is True
