"""Release gate: inspect actual kernel limits inside a disposable rootless sandbox."""

from uuid import uuid4

from guojing.core.config import Settings
from guojing.infrastructure.runtime import ProcessLease
from guojing.infrastructure.sandbox.docker_backend import DockerSandboxFactory


def verify() -> None:
    settings = Settings()
    lease = ProcessLease(settings.database_url)
    lease.acquire()  # The API must be stopped during this probe.
    factory = DockerSandboxFactory(
        docker_host=settings.sandbox_docker_host,
        image=settings.sandbox_image,
        deployment_id=settings.deployment_id,
    )
    try:
        if not factory.check_ready(require_rootless=True):
            raise RuntimeError(
                "rootless Docker with cgroup v2/systemd and pre-pulled image required"
            )
        factory.cleanup_orphans()
        backend = factory.create(uuid4())
        try:
            response = backend.execute(
                "cat /sys/fs/cgroup/cpu.max /sys/fs/cgroup/memory.max /sys/fs/cgroup/pids.max"
            )
            if response.exit_code != 0:
                raise RuntimeError("cannot inspect sandbox cgroup controls")
            cpu, memory, pids = response.output.strip().splitlines()
            quota, period = cpu.split()
            if quota == "max" or int(quota) / int(period) != 0.5:
                raise RuntimeError("CPU limit is not effective")
            if memory != str(512 * 1024 * 1024) or pids != "64":
                raise RuntimeError("memory or PID limit is not effective")
            if backend.execute("touch /etc/guojing-readonly-probe").exit_code == 0:
                raise RuntimeError("sandbox root filesystem is writable")
            print("rootless/cgroup-v2: cpu=0.5 memory=512MiB pids=64 read-only-root: verified")
        finally:
            backend.destroy()
    finally:
        factory.close()
        lease.release()


if __name__ == "__main__":
    verify()
