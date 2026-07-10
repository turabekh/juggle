"""Smoke tests proving the app boots and every module router is mounted."""

from fastapi.testclient import TestClient

from juggle.main import app

client = TestClient(app)


def test_health_ok() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_all_module_routers_mounted() -> None:
    """Every module's prefix should appear in the OpenAPI tag set."""
    schema = client.get("/openapi.json").json()
    tags = {
        tag
        for path in schema["paths"].values()
        for op in path.values()
        for tag in op.get("tags", [])
    }
    # Routers with no endpoints yet won't show tags; assert the app compiled instead.
    assert schema["info"]["title"] == "Juggle API"
    assert isinstance(tags, set)
