from collections.abc import AsyncIterator
from typing import cast
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.device_helpers import authorize_client


def test_anonymous_body_is_rejected_before_json_or_image_validation(
    agent_client: TestClient,
) -> None:
    response = agent_client.post(
        "/api/v1/agent/sessions", headers={"Authorization": ""}, content=b"not-json"
    )
    assert response.status_code == 401


def test_device_cannot_read_another_devices_session_even_with_session_token(
    agent_client: TestClient,
) -> None:
    session = agent_client.post(
        "/api/v1/agent/sessions",
        json={
            "schema_version": "1.0",
            "client_session_id": str(uuid4()),
            "goal": "设置",
            "target_package": "com.test.app",
        },
    ).json()
    authorize_client(agent_client)
    result = agent_client.get(
        f"/api/v1/agent/sessions/{session['session_id']}/turns/{uuid4()}",
        headers={"X-Agent-Session-Token": session["access_token"]},
    )
    assert result.status_code == 404


@pytest.mark.asyncio
async def test_chunked_body_limit_is_enforced_without_content_length(
    agent_client: TestClient,
) -> None:
    async def chunks() -> AsyncIterator[bytes]:
        yield b'{"padding":"'
        for _ in range(13):
            yield b"x" * 1024 * 1024
        yield b'"}'

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=cast(FastAPI, agent_client.app)),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/agent/sessions",
            content=chunks(),
            headers={
                "Authorization": agent_client.headers["Authorization"],
                "Content-Type": "application/json",
            },
        )
    assert response.status_code == 413
    assert "x" * 100 not in response.text


def test_activation_validation_never_echoes_credentials(agent_client: TestClient) -> None:
    secret = "PRIVATE-CREDENTIAL-DO-NOT-LOG"
    response = agent_client.post("/api/v1/devices/activate", json={"device_secret": secret})
    assert response.status_code == 422
    assert secret not in response.text
