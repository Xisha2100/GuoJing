import pytest

from guojing.core.config import Settings
from guojing.operations import sandbox_check


def test_bounded_release_gate_does_not_access_docker(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        sandbox_check, "Settings", lambda: Settings(guidance_engine="bounded", _env_file=None)
    )

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("bounded release must not access Docker or the API process lease")

    monkeypatch.setattr(sandbox_check, "DockerSandboxFactory", forbidden)
    monkeypatch.setattr(sandbox_check, "ProcessLease", forbidden)
    sandbox_check.verify()
    assert capsys.readouterr().out == "bounded guidance: no sandbox required\n"
