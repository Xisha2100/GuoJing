"""Contract tests for the process health endpoint."""

from fastapi.testclient import TestClient


def test_health_returns_stable_success_contract(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok"}
