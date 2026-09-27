"""Rootless-friendly Docker implementation of the Deep Agents sandbox protocol."""

import asyncio
import shlex
import socket
import time
from dataclasses import dataclass
from pathlib import PurePosixPath
from threading import Lock
from typing import Any
from uuid import UUID

import docker  # type: ignore[import-untyped]
from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox

_ALLOWED_ROOTS = (PurePosixPath("/workspace"), PurePosixPath("/tmp"))


class DockerSandboxBackend(BaseSandbox):
    """Expose one locked-down container as a Deep Agents sandbox."""

    def __init__(
        self,
        client: Any,
        container: Any,
        *,
        command_timeout_seconds: int = 10,
        maximum_output_bytes: int = 16 * 1024,
    ) -> None:
        self._client = client
        self._container = container
        self._command_timeout_seconds = command_timeout_seconds
        self._maximum_output_bytes = maximum_output_bytes

    @property
    def id(self) -> str:
        return str(self._container.id)

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        bounded_timeout = min(
            timeout or self._command_timeout_seconds,
            self._command_timeout_seconds,
        )
        wrapped = f"timeout -s KILL {bounded_timeout}s sh -lc {shlex.quote(command)}"
        created = self._client.api.exec_create(
            self._container.id,
            ["sh", "-lc", wrapped],
            stdout=True,
            stderr=True,
        )
        exec_id = created["Id"]
        stream = self._client.api.exec_start(exec_id, stream=True, demux=False)
        output = bytearray()
        truncated = False
        for chunk in stream:
            if not isinstance(chunk, bytes):
                continue
            remaining = self._maximum_output_bytes - len(output)
            if remaining > 0:
                output.extend(chunk[:remaining])
            if len(chunk) > remaining:
                truncated = True
        inspected = self._client.api.exec_inspect(exec_id)
        return ExecuteResponse(
            output=output.decode("utf-8", errors="replace"),
            exit_code=inspected.get("ExitCode"),
            truncated=truncated,
        )

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        responses: list[FileUploadResponse] = []
        for raw_path, content in files:
            try:
                path = _safe_path(raw_path)
                parent = str(path.parent)
                created_parent = self.execute(f"mkdir -p {shlex.quote(parent)}")
                if created_parent.exit_code != 0:
                    raise RuntimeError("sandbox parent creation failed")
                self._write_file(path, content)
                responses.append(FileUploadResponse(path=str(path), error=None))
            except ValueError:
                responses.append(FileUploadResponse(path=raw_path, error="invalid_path"))
            except Exception:
                responses.append(FileUploadResponse(path=raw_path, error="upload_failed"))
        return responses

    def _write_file(self, path: PurePosixPath, content: bytes) -> None:
        """Stream bytes through a container process into the writable tmpfs.

        Docker's archive-copy endpoint rejects every destination when the container
        root filesystem is read-only, including writable tmpfs mounts. Standard
        input preserves the read-only-root policy while allowing writes strictly
        through the unprivileged process inside the sandbox.
        """
        created = self._client.api.exec_create(
            self._container.id,
            ["sh", "-lc", f"umask 077; cat > {shlex.quote(str(path))}"],
            stdin=True,
            stdout=True,
            stderr=True,
        )
        exec_id = created["Id"]
        stream = self._client.api.exec_start(exec_id, socket=True)
        raw_socket = getattr(stream, "_sock", stream)
        try:
            raw_socket.sendall(content)
            raw_socket.shutdown(socket.SHUT_WR)
            while raw_socket.recv(4096):
                pass
        finally:
            stream.close()
        inspected = self._client.api.exec_inspect(exec_id)
        if inspected.get("ExitCode") != 0:
            raise RuntimeError("sandbox file write failed")

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses: list[FileDownloadResponse] = []
        for raw_path in paths:
            try:
                path = _safe_path(raw_path)
                content = self._read_file(path)
                responses.append(FileDownloadResponse(path=str(path), content=content, error=None))
            except ValueError:
                responses.append(
                    FileDownloadResponse(path=raw_path, content=None, error="invalid_path")
                )
            except Exception:
                responses.append(
                    FileDownloadResponse(path=raw_path, content=None, error="file_not_found")
                )
        return responses

    def _read_file(self, path: PurePosixPath) -> bytes:
        # Docker's archive endpoint is unreliable for files inside a read-only
        # root filesystem's tmpfs; exec reads the exact path without a host mount.
        created = self._client.api.exec_create(
            self._container.id,
            ["sh", "-lc", f"cat {shlex.quote(str(path))}"],
            stdout=True,
            stderr=False,
        )
        output = bytearray()
        for chunk in self._client.api.exec_start(created["Id"], stream=True, demux=False):
            if not isinstance(chunk, bytes):
                continue
            if len(output) + len(chunk) > 16 * 1024 * 1024:
                raise RuntimeError("sandbox file too large")
            output.extend(chunk)
        if self._client.api.exec_inspect(created["Id"]).get("ExitCode") != 0:
            raise FileNotFoundError
        return bytes(output)

    def destroy(self) -> None:
        try:
            self._container.remove(force=True)
        except docker.errors.NotFound:
            pass


class DockerSandboxFactory:
    """Create resource-bounded containers without host mounts or credentials."""

    def __init__(
        self, *, docker_host: str | None, image: str, deployment_id: str = "local"
    ) -> None:
        self._docker_host = docker_host
        self._image = image
        self._deployment_id = deployment_id
        self._client: Any | None = None
        self._lock = Lock()

    def create(self, session_id: UUID) -> DockerSandboxBackend:
        client = self._get_client()
        container = client.containers.run(
            self._image,
            ["sh", "-lc", "while :; do sleep 3600; done"],
            detach=True,
            auto_remove=False,
            network_mode="none",
            read_only=True,
            tmpfs={
                "/workspace": "rw,nosuid,nodev,noexec,mode=1777,size=64m",
                "/tmp": "rw,nosuid,nodev,noexec,mode=1777,size=16m",
            },
            user="65532:65532",
            nano_cpus=500_000_000,
            mem_limit="512m",
            pids_limit=64,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            environment={},
            log_config={"type": "none"},
            working_dir="/workspace",
            labels={
                "com.xisha.guojing.agent-sandbox": "true",
                "com.xisha.guojing.deployment": self._deployment_id,
                "com.xisha.guojing.session-id": str(session_id),
            },
        )
        return DockerSandboxBackend(client, container)

    def cleanup_orphans(self) -> None:
        client = self._get_client()
        containers = client.containers.list(
            all=True,
            filters={
                "label": [
                    "com.xisha.guojing.agent-sandbox=true",
                    f"com.xisha.guojing.deployment={self._deployment_id}",
                ]
            },
        )
        for container in containers:
            try:
                container.remove(force=True)
            except docker.errors.NotFound:
                continue

    def check_ready(self, require_rootless: bool = False) -> bool:
        client = self._get_client()
        client.ping()
        client.images.get(self._image)
        if require_rootless:
            info = client.info()
            return (
                info.get("CgroupVersion") == "2"
                and info.get("CgroupDriver") == "systemd"
                and "name=rootless" in info.get("SecurityOptions", [])
                and all(
                    info.get(name)
                    for name in ("MemoryLimit", "PidsLimit", "CpuCfsQuota", "CpuCfsPeriod")
                )
            )
        return True

    def close(self) -> None:
        if self._client is not None:
            self._client.close()

    def _get_client(self) -> Any:
        with self._lock:
            if self._client is None:
                self._client = (
                    docker.DockerClient(base_url=self._docker_host, timeout=5)
                    if self._docker_host
                    else docker.from_env(timeout=5)
                )
            return self._client


@dataclass(slots=True)
class _SandboxEntry:
    backend: DockerSandboxBackend
    touched_at: float


class DockerSandboxRegistry:
    """Bound both active and late-created containers; retain failures for recovery."""

    def __init__(
        self,
        factory: DockerSandboxFactory,
        *,
        idle_ttl_seconds: int = 600,
        maximum_containers: int = 2,
    ) -> None:
        self._factory = factory
        self._idle_ttl_seconds = idle_ttl_seconds
        self._maximum_containers = maximum_containers
        self._entries: dict[UUID, _SandboxEntry] = {}
        self._creating: dict[UUID, asyncio.Task[DockerSandboxBackend]] = {}
        self._background: set[asyncio.Task[None]] = set()
        self._lock = asyncio.Lock()
        self.healthy = True

    async def start(self) -> None:
        try:
            await asyncio.to_thread(self._factory.cleanup_orphans)
        except Exception:
            self.healthy = False
            raise

    async def check_ready(self, require_rootless: bool = False) -> bool:
        return self.healthy and await asyncio.to_thread(self._factory.check_ready, require_rootless)

    async def acquire(self, session_id: UUID) -> DockerSandboxBackend:
        async with self._lock:
            if not self.healthy:
                raise RuntimeError("sandbox cleanup requires recovery")
            entry = self._entries.get(session_id)
            if entry:
                entry.touched_at = time.monotonic()
                return entry.backend
            task = self._creating.get(session_id)
            if task is None:
                if len(self._entries) + len(self._creating) >= self._maximum_containers:
                    raise RuntimeError("sandbox capacity reached")
                task = asyncio.create_task(asyncio.to_thread(self._factory.create, session_id))
                self._creating[session_id] = task
        try:
            backend = await asyncio.shield(task)
        except asyncio.CancelledError:
            cleanup = asyncio.create_task(self.destroy(session_id))
            self._background.add(cleanup)
            cleanup.add_done_callback(self._background_done)
            raise
        except Exception:
            self.healthy = False
            async with self._lock:
                self._creating.pop(session_id, None)
            raise
        async with self._lock:
            self._creating.pop(session_id, None)
            self._entries[session_id] = _SandboxEntry(backend, time.monotonic())
        return backend

    async def destroy(self, session_id: UUID) -> None:
        async with self._lock:
            creation = self._creating.get(session_id)
            entry = self._entries.get(session_id)
            if creation is not None:
                try:
                    backend = await asyncio.shield(creation)
                except Exception:
                    self._creating.pop(session_id, None)
                    return
                entry = _SandboxEntry(backend, time.monotonic())
                self._entries[session_id] = entry
                self._creating.pop(session_id, None)
            if entry is not None:
                try:
                    await asyncio.to_thread(entry.backend.destroy)
                except BaseException:
                    self.healthy = False
                    raise
                self._entries.pop(session_id, None)

    def _background_done(self, task: asyncio.Task[None]) -> None:
        self._background.discard(task)
        if task.cancelled() or task.exception() is not None:
            self.healthy = False

    async def cleanup_idle(self) -> None:
        cutoff = time.monotonic() - self._idle_ttl_seconds
        async with self._lock:
            expired = [key for key, value in self._entries.items() if value.touched_at <= cutoff]
        for session_id in expired:
            await self.destroy(session_id)

    async def close(self) -> None:
        for session_id in set(self._entries) | set(self._creating):
            await self.destroy(session_id)
        if self._background:
            await asyncio.gather(*self._background, return_exceptions=True)
        await asyncio.to_thread(self._factory.close)


def _safe_path(raw_path: str) -> PurePosixPath:
    path = PurePosixPath(raw_path)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("sandbox path is invalid")
    if not any(path == root or root in path.parents for root in _ALLOWED_ROOTS):
        raise ValueError("sandbox path is outside writable roots")
    return path
