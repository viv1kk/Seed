"""POST /api/plans and GET /api/examples."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_registry
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def post_plan(client: TestClient, **body: Any) -> dict[str, Any]:
    response = client.post("/api/plans", json=body)
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


# ---------------------------------------------------------------- examples


def test_the_bundled_example_is_listed(client: TestClient) -> None:
    response = client.get("/api/examples")
    assert response.status_code == 200

    examples = response.json()
    assert {"id": "retail-analytics", "title": "Retail revenue analytics platform"} in examples


def test_an_unknown_example_is_a_404(client: TestClient) -> None:
    assert client.get("/api/examples/not-a-file").status_code == 404


def test_an_example_id_cannot_escape_the_examples_directory(client: TestClient) -> None:
    """The id is matched against what is on disk, never joined onto a path."""
    response = client.post("/api/plans", json={"example_id": "../../CLAUDE"})
    assert response.status_code == 404


# ---------------------------------------------------------------- planning


def test_planning_the_bundled_example(client: TestClient) -> None:
    body = post_plan(client, example_id="retail-analytics")

    assert body["status"] == "ok"
    assert len(body["plan"]["phases"]) == 3
    assert len(body["plan"]["tasks"]) == 7
    assert body["plan"]["warnings"] == []


def test_planning_raw_markdown(client: TestClient) -> None:
    body = post_plan(
        client,
        markdown="# T\n\n## P\n\n### A task\n\nAgent: ETL Engineer\n\n- a step\n",
    )
    assert body["status"] == "ok"
    assert body["plan"]["tasks"]["1.1"]["agent_id"] == "etl"


def test_the_source_document_comes_back_for_rendering(client: TestClient) -> None:
    body = post_plan(client, example_id="retail-analytics")
    assert body["plan"]["source_markdown"].startswith("# Retail revenue analytics platform")


def test_a_broken_dependency_is_answered_with_errors_and_no_plan(client: TestClient) -> None:
    """The gate: the error is shown and the run is refused.

    Refused means there is no plan and therefore no plan id to start a run with,
    rather than a 500 or a traceback.
    """
    body = post_plan(
        client,
        markdown=(
            "# T\n\n## P\n\n### A\n\nAgent: Architect\n\n- step\n\n"
            "### B\n\nAgent: Architect\nDepends on: 4.4\n\n- step\n"
        ),
    )

    assert body["status"] == "error"
    assert "plan" not in body
    assert body["errors"][0]["code"] == "unknown-dependency"
    assert body["errors"][0]["task_id"] == "1.2"


def test_a_parse_failure_is_not_an_http_error(client: TestClient) -> None:
    """The document belongs to the user. A mistake in it is not a server fault."""
    response = client.post("/api/plans", json={"markdown": "### Orphan\n"})
    assert response.status_code == 200
    assert response.json()["status"] == "error"


def test_a_successful_plan_is_retained_for_a_later_run(client: TestClient) -> None:
    """POST /api/runs takes a plan_id, so the plan has to still be there."""
    body = post_plan(client, example_id="retail-analytics")
    plan_id = body["plan"]["id"]

    assert get_registry().get_plan(plan_id) is not None


def test_a_refused_document_leaves_nothing_behind(client: TestClient) -> None:
    before = len(get_registry().list_runs())
    post_plan(client, markdown="### Orphan\n")
    assert len(get_registry().list_runs()) == before


def test_the_request_needs_exactly_one_source(client: TestClient) -> None:
    assert client.post("/api/plans", json={}).status_code == 422
    assert (
        client.post(
            "/api/plans", json={"markdown": "# T\n", "example_id": "retail-analytics"}
        ).status_code
        == 422
    )


def test_replanning_the_same_document_gives_the_same_plan_id(client: TestClient) -> None:
    first = post_plan(client, example_id="retail-analytics")
    second = post_plan(client, example_id="retail-analytics")
    assert first["plan"]["id"] == second["plan"]["id"]


def test_editing_the_document_gives_a_different_plan(client: TestClient) -> None:
    source = post_plan(client, example_id="retail-analytics")["plan"]["source_markdown"]
    edited = source.replace("### 3.1 Build the revenue dashboard", "### 3.1 Ship the dashboard")

    body = post_plan(client, markdown=edited)
    assert body["plan"]["tasks"]["3.1"]["title"] == "Ship the dashboard"
