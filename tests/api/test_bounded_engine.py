import json
import logging
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from tests.api.test_agent import _png_base64, _wait_for_terminal
from tests.device_helpers import authorize_client
from tests.infrastructure.agents.test_deepagents_compatibility import Script

from guojing.core.config import AppEnvironment, GuidanceEngine, Settings
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.models import Base
from guojing.main import create_app


def test_bounded_api_preserves_contract_and_idempotence_without_docker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="guojing.application.agent.coordinator")
    script = Script(monkeypatch)

    def no_docker(*args: object, **kwargs: object) -> None:
        pytest.fail("bounded engine must not construct a Docker factory")

    monkeypatch.setattr("guojing.main.DockerSandboxFactory", no_docker)
    settings = Settings(
        _env_file=None,
        environment=AppEnvironment.TEST,
        database_url=f"sqlite:///{tmp_path / 'bounded.db'}",
        guidance_engine=GuidanceEngine.BOUNDED,
        deepseek_api_key=SecretStr("offline"),
    )
    database = Database(settings.database_url)
    Base.metadata.create_all(database.engine)
    try:
        with TestClient(create_app(settings)) as client:
            assert client.get("/ready").status_code == 200
            authorize_client(client)
            response = client.post(
                "/api/v1/agent/sessions",
                json={
                    "schema_version": "1.0",
                    "client_session_id": str(uuid4()),
                    "goal": "打开设置",
                    "target_package": "com.example.app",
                },
            )
            assert response.status_code == 201
            saved = response.json()
            assert set(saved) == {"schema_version", "session_id", "access_token", "status"}
            headers = {"X-Agent-Session-Token": saved["access_token"]}
            turn = str(uuid4())
            payload = {
                "schema_version": "1.0",
                "client_turn_id": turn,
                "image_media_type": "image/png",
                "screen_width": 8,
                "screen_height": 12,
                "screenshot_base64": _png_base64(8, 12),
            }
            path = f"/api/v1/agent/sessions/{saved['session_id']}/runs"
            accepted = client.post(path, headers=headers, json=payload)
            assert accepted.status_code == 202
            assert set(accepted.json()) == {"schema_version", "run_id", "status", "events_endpoint"}
            run_id = accepted.json()["run_id"]
            result = _wait_for_terminal(client, run_id, headers)
            assert set(result) == {
                "schema_version",
                "run_id",
                "session_id",
                "status",
                "result",
                "error_code",
                "retryable",
            }
            assert result["status"] == "completed"
            decision = result["result"]
            assert isinstance(decision, dict)
            assert set(decision) == {"status", "instruction", "target", "confidence"}
            assert client.post(path, headers=headers, json=payload).json()["run_id"] == run_id
            restored = client.get(
                f"/api/v1/agent/sessions/{saved['session_id']}/turns/{turn}", headers=headers
            )
            assert restored.json() == result
            events = client.get(f"/api/v1/agent/runs/{run_id}/events", headers=headers).text
            assert "candidate" not in events and "image_url" not in events
            assert len(script.calls) == 2
            repeated = client.post(
                path, headers=headers, json={**payload, "client_turn_id": str(uuid4())}
            )
            repeated_result = _wait_for_terminal(client, repeated.json()["run_id"], headers)
            repeated_decision = repeated_result["result"]
            assert isinstance(repeated_decision, dict)
            assert repeated_decision["status"] == "cannot_determine"
            assert repeated_decision["target"] is None
    finally:
        database.dispose()
    logs = [record.message for record in caplog.records if record.message.startswith("agent_run ")]
    assert len(logs) == 2
    metrics = json.loads(logs[0].removeprefix("agent_run "))
    assert metrics["engine"] == "bounded"
    assert metrics["prompt_version"] == "bounded-1"
    assert metrics["sandbox_prepare_ms"] == metrics["cleanup_ms"] == 0
    assert metrics["model_calls"] == 2
    assert len(metrics["stages"]) == 2
    assert all(value not in logs[0] for value in ("打开设置", "设置按钮", "image_url", "base64"))
    assert json.loads(logs[1].removeprefix("agent_run "))["rejection"] == "unchanged_guidance"


def test_bounded_without_model_key_is_not_ready(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        environment=AppEnvironment.TEST,
        database_url=f"sqlite:///{tmp_path / 'unconfigured.db'}",
        guidance_engine=GuidanceEngine.BOUNDED,
        deepseek_api_key=None,
    )
    database = Database(settings.database_url)
    Base.metadata.create_all(database.engine)
    try:
        with TestClient(create_app(settings)) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/ready").status_code == 503
    finally:
        database.dispose()
