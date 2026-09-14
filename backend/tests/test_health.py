"""The one route phase 0 serves."""

from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0", "mode": "simulation"}


def test_the_api_is_not_shadowed_by_a_catch_all_mount() -> None:
    """The static mount arrives in phase 2 and must be registered last.

    Mounted before the routers it swallows every /api path. Asserting the route
    resolves now means the test is already in place when the mount is added.
    """
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
