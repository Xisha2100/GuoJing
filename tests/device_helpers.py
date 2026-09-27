import secrets
from typing import cast
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from guojing.application.device_access import DeviceAccessService


def authorize_client(client: TestClient) -> str:
    app = cast(FastAPI, client.app)
    service = cast(DeviceAccessService, app.state.device_access)
    secret = secrets.token_urlsafe(32)
    result = client.post(
        "/api/v1/devices/activate",
        json={
            "schema_version": "1.0",
            "invitation_code": service.invite("test device"),
            "installation_id": str(uuid4()),
            "device_secret": secret,
        },
    )
    assert result.status_code == 200, result.json()
    identifier = str(result.json()["device_id"])
    client.headers["Authorization"] = f"Bearer {identifier}.{secret}"
    return identifier
