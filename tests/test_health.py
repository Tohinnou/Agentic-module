"""Sanity check : le package s'importe et expose sa version."""
from fastapi.testclient import TestClient

from sandbox.api import app


def test_package_imports():
    import sandbox
    assert sandbox.__version__ == "0.1.0"


def test_health_endpoint_returns_ok():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
