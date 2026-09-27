import os
from uuid import uuid4

import pytest

from guojing.core.config import Settings
from guojing.infrastructure.sandbox.docker_backend import DockerSandboxFactory


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("GUOJING_RUN_DOCKER_TESTS") != "1", reason="explicit real Docker opt-in required"
)
def test_real_container_isolation_and_kernel_resource_controls() -> None:
    settings = Settings()
    factory = DockerSandboxFactory(
        docker_host=settings.sandbox_docker_host,
        image=settings.sandbox_image,
        deployment_id=f"test-{uuid4()}",
    )
    backend = factory.create(uuid4())
    try:
        result = backend.execute(
            "cat /sys/fs/cgroup/cpu.max /sys/fs/cgroup/memory.max /sys/fs/cgroup/pids.max"
        )
        cpu, memory, pids = result.output.strip().splitlines()
        quota, period = map(int, cpu.split())
        assert quota / period == 0.5
        assert int(memory) == 512 * 1024 * 1024 and int(pids) == 64
        assert backend.execute("id -u").output.strip() == "65532"
        assert backend.execute("touch /etc/forbidden").exit_code != 0
        assert backend.upload_files([("/workspace/probe.txt", b"synthetic probe")])[0].error is None
        assert backend.download_files(["/workspace/probe.txt"])[0].content == b"synthetic probe"
        container = backend._container
        container.reload()
        assert container.attrs["HostConfig"]["NetworkMode"] == "none"
        assert container.attrs["HostConfig"]["CapDrop"] == ["ALL"]
        assert not any(mount["Type"] == "bind" for mount in container.attrs["Mounts"])
    finally:
        backend.destroy()
        factory.close()
