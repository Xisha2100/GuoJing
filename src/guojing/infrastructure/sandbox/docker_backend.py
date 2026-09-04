"""Rootless-friendly Docker implementation of the Deep Agents sandbox protocol."""

import asyncio
import io
import shlex
import tarfile
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
                archive = io.BytesIO()
                with tarfile.open(fileobj=archive, mode="w") as tar:
                    info = tarfile.TarInfo(name=path.name)
                    info.size = len(content)
                    info.mode = 0o600
                    tar.addfile(info, io.BytesIO(content))
                archive.seek(0)
                parent = str(path.parent)
                self.execute(f"mkdir -p {shlex.quote(parent)}")
                if not self._container.put_archive(parent, archive.getvalue()):
                    raise RuntimeError("Docker rejected archive")
                responses.append(FileUploadResponse(path=str(path), error=None))
            except ValueError:
                responses.append(FileUploadResponse(path=raw_path, error="invalid_path"))
            except Exception:
                responses.append(FileUploadResponse(path=raw_path, error="upload_failed"))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses: list[FileDownloadResponse] = []
        for raw_path in paths:
            try:
                path = _safe_path(raw_path)
                stream, _stat = self._container.get_archive(str(path))
                archive_bytes = b"".join(stream)
                with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r") as tar:
                    member = tar.next()
                    extracted = tar.extractfile(member) if member is not None else None
                    if extracted is None:
                        raise FileNotFoundError
                    content = extracted.read()
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

    def destroy(self) -> None:
        try:
            self._container.remove(force=True)
        except Exception:
            pass


class DockerSandboxFactory:
    """Create resource-bounded containers without host mounts or credentials."""

    def __init__(self, *, docker_host: str | None, image: str) -> None:
        self._docker_host = docker_host
        self._image = image
        self._client: Any | None = None
        self._lock = Lock()

    def create(self, session_id: UUID) -> DockerSandboxBackend:
        client = self._get_client()
        container = client.containers.run(
            self._image,
            ["sh", "-lc", "while :; do sleep 3600; done"],
            detach=True,
            auto_remove=False,
            network_disabled=True,
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
            working_dir="/workspace",
            labels={
                "com.xisha.guojing.agent-sandbox": "true",
                "com.xisha.guojing.session-id": str(session_id),
            },
        )
        return DockerSandboxBackend(client, container)

    def cleanup_orphans(self) -> None:
        client = self._get_client()
        containers = client.containers.list(
            all=True,
            filters={"label": "com.xisha.guojing.agent-sandbox=true"},
        )
        for container in containers:
            try:
                container.remove(force=True)
            except Exception:
                continue

    def close(self) -> None:
        if self._client is not None:
            self._client.close()

    def _get_client(self) -> Any:
        with self._lock:
            if self._client is None:
                self._client = (
                    docker.DockerClient(base_url=self._docker_host)
                    if self._docker_host
                    else docker.from_env()
                )
            return self._client


@dataclass(slots=True)
class _SandboxEntry:
    backend: DockerSandboxBackend
    touched_at: float


class DockerSandboxRegistry:
    """Keep at most one isolated container per guidance session."""

    def __init__(self, factory: DockerSandboxFactory, *, idle_ttl_seconds: int = 600) -> None:
        self._factory = factory
        self._idle_ttl_seconds = idle_ttl_seconds
        self._entries: dict[UUID, _SandboxEntry] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        try:
            await asyncio.to_thread(self._factory.cleanup_orphans)
        except Exception:
            pass

    async def acquire(self, session_id: UUID) -> DockerSandboxBackend:
        async with self._lock:
            entry = self._entries.get(session_id)
            if entry is None:
                backend = await asyncio.to_thread(self._factory.create, session_id)
                entry = _SandboxEntry(backend=backend, touched_at=time.monotonic())
                self._entries[session_id] = entry
            else:
                entry.touched_at = time.monotonic()
            return entry.backend

    async def destroy(self, session_id: UUID) -> None:
        async with self._lock:
            entry = self._entries.pop(session_id, None)
        if entry is not None:
            await asyncio.to_thread(entry.backend.destroy)

    async def cleanup_idle(self) -> None:
        cutoff = time.monotonic() - self._idle_ttl_seconds
        async with self._lock:
            expired = [key for key, value in self._entries.items() if value.touched_at <= cutoff]
        for session_id in expired:
            await self.destroy(session_id)

    async def close(self) -> None:
        async with self._lock:
            entries = list(self._entries.values())
            self._entries.clear()
        await asyncio.gather(
            *(asyncio.to_thread(entry.backend.destroy) for entry in entries),
            return_exceptions=True,
        )
        await asyncio.to_thread(self._factory.close)


def _safe_path(raw_path: str) -> PurePosixPath:
    path = PurePosixPath(raw_path)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("sandbox path is invalid")
    if not any(path == root or root in path.parents for root in _ALLOWED_ROOTS):
        raise ValueError("sandbox path is outside writable roots")
    return path
