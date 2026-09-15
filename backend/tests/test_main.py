"""The static mount, which serves the built frontend from the API process.

The mount is a catch-all on "/". Registered before the routers it swallows every
/api path, and the symptom is a 404 that looks like a missing endpoint rather
than a missing route order. These tests pin the order from both sides: the API
still answers, and the page is served.
"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import DIST, NOT_BUILT, create_app, mount_frontend


def test_the_api_answers_with_the_mount_registered() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/examples").status_code == 200


def test_an_unbuilt_frontend_says_how_to_build_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refusing to start would be worse: the API is the half that is running."""
    monkeypatch.setattr("app.main.DIST", tmp_path / "nothing-here")
    app = FastAPI()
    mount_frontend(app)

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.text == NOT_BUILT


def test_a_built_frontend_is_served_from_the_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><title>Seed</title>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("export const seed = 1;", encoding="utf-8")
    monkeypatch.setattr("app.main.DIST", tmp_path)
    app = FastAPI()
    mount_frontend(app)

    with TestClient(app) as client:
        index = client.get("/")
        asset = client.get("/assets/app.js")

    assert index.status_code == 200
    assert "<title>Seed</title>" in index.text
    assert asset.status_code == 200


def test_the_dist_path_points_at_the_frontend_build_directory() -> None:
    """A wrong parents[] index silently serves nothing, forever."""
    assert DIST.name == "dist"
    assert DIST.parent.name == "frontend"
    assert (DIST.parent / "package.json").is_file()
