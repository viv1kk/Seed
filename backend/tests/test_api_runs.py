"""POST /api/runs, GET /api/runs/{id}/stream, POST /api/runs/{id}/control.

Every streaming test runs against a real uvicorn server rather than
``TestClient``. Starlette's test transport reports ``http.disconnect`` on its
receive channel as soon as the request body is consumed, and sse-starlette
correctly tears the stream down when it sees that, so a streamed response
truncates at an arbitrary point. It is a limitation of the transport, not of the
endpoint. Testing SSE through TestClient produces tests that pass while
asserting almost nothing, so this spends a few seconds on a real server instead.
"""

import json
import socket
import threading
import time
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from app.api.deps import get_registry
from app.main import app

SMALL_REQUIREMENT = """# Small

## One

### Decide the shape

Agent: Architect

- write the contract

### Load it

Agent: ETL Engineer
Depends on: 1.1

- read the extract
"""


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------- a real server


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


@pytest.fixture(scope="module")
def live_url() -> Iterator[str]:
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 20
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "the test server did not start"

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=10)


def live_plan(url: str, markdown: str = SMALL_REQUIREMENT) -> str:
    body = httpx.post(f"{url}/api/plans", json={"markdown": markdown}, timeout=30).json()
    assert body["status"] == "ok", body
    plan_id: str = body["plan"]["id"]
    return plan_id


def live_run(url: str, plan_id: str, speed: int = 5) -> str:
    body = httpx.post(
        f"{url}/api/runs", json={"plan_id": plan_id, "speed": speed}, timeout=30
    ).json()
    run_id: str = body["run_id"]
    return run_id


def live_events(
    url: str, run_id: str, stop_after: int | None = None
) -> list[dict[str, Any]]:
    """Consume a run's SSE stream over real HTTP."""
    events: list[dict[str, Any]] = []
    stream_url = f"{url}/api/runs/{run_id}/stream"
    with httpx.Client(timeout=120.0) as client, client.stream("GET", stream_url) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if not line.startswith("data:"):
                continue
            events.append(json.loads(line[5:].strip()))
            if stop_after is not None and len(events) >= stop_after:
                return events
            if events[-1]["type"] in {"run.completed", "run.failed"}:
                return events
    return events


def live_frames(url: str, run_id: str, take: int) -> tuple[list[str], list[str]]:
    """The raw `event:` names and `id:` values, for checking SSE framing."""
    names: list[str] = []
    ids: list[str] = []
    stream_url = f"{url}/api/runs/{run_id}/stream"
    with httpx.Client(timeout=60.0) as client, client.stream("GET", stream_url) as response:
        for line in response.iter_lines():
            if line.startswith("event:"):
                names.append(line[6:].strip())
            elif line.startswith("id:"):
                ids.append(line[3:].strip())
            if len(names) >= take and len(ids) >= take:
                break
    return names, ids


# ---------------------------------------------------------------- creating


def test_starting_a_run_returns_a_run_id(client: TestClient) -> None:
    plan_id = client.post("/api/plans", json={"markdown": SMALL_REQUIREMENT}).json()["plan"]["id"]
    response = client.post("/api/runs", json={"plan_id": plan_id, "speed": 5})

    assert response.status_code == 200
    run_id = response.json()["run_id"]
    assert run_id.startswith("run_")
    assert get_registry().get(run_id) is not None

    client.post(f"/api/runs/{run_id}/control", json={"action": "cancel"})


def test_a_run_needs_a_plan_that_exists(client: TestClient) -> None:
    assert client.post("/api/runs", json={"plan_id": "plan_nope"}).status_code == 404


def test_only_the_offered_speeds_are_accepted(client: TestClient) -> None:
    plan_id = client.post("/api/plans", json={"markdown": SMALL_REQUIREMENT}).json()["plan"]["id"]
    assert client.post("/api/runs", json={"plan_id": plan_id, "speed": 3}).status_code == 422


def test_a_refused_document_cannot_be_run(client: TestClient) -> None:
    """The phase 1 gate, still true now that runs exist."""
    rejected = client.post(
        "/api/plans",
        json={"markdown": "# T\n\n## P\n\n### A\n\nAgent: Architect\nDepends on: 9.9\n\n- step\n"},
    ).json()
    assert rejected["status"] == "error"
    assert "plan" not in rejected, "there is no plan id with which to start a run"


def test_streaming_an_unknown_run_is_a_404(client: TestClient) -> None:
    assert client.get("/api/runs/run_nope/stream").status_code == 404


def test_controlling_an_unknown_run_is_a_404(client: TestClient) -> None:
    assert (
        client.post("/api/runs/run_nope/control", json={"action": "pause"}).status_code == 404
    )


# ---------------------------------------------------------------- streaming


def test_a_run_streams_from_start_to_completion(live_url: str) -> None:
    run_id = live_run(live_url, live_plan(live_url))
    events = live_events(live_url, run_id)

    assert events[0]["type"] == "run.started"
    assert events[1]["type"] == "plan.built"
    assert events[-1]["type"] == "run.completed"
    assert [e["seq"] for e in events] == list(range(len(events)))


def test_the_stream_sets_the_event_name_and_id(live_url: str) -> None:
    """The framing docs/03-EVENT-CONTRACT.md specifies."""
    run_id = live_run(live_url, live_plan(live_url))
    names, ids = live_frames(live_url, run_id, take=2)

    assert names[0] == "run.started"
    assert ids[:2] == ["0", "1"]


def test_reconnecting_mid_run_replays_and_rejoins(live_url: str) -> None:
    """The refresh-during-the-demo case.

    Disconnect part way through, reconnect, and the second connection has to
    deliver the run from seq 0 and then carry on to the end. Joining late would
    leave the graph undrawn for the rest of the run.
    """
    run_id = live_run(live_url, live_plan(live_url), speed=2)

    partial = live_events(live_url, run_id, stop_after=5)
    assert len(partial) == 5
    assert partial[-1]["type"] != "run.completed", "the run ended before it could be cut"

    rejoined = live_events(live_url, run_id)

    assert rejoined[:5] == partial, "the replay differed from what was seen live"
    assert rejoined[-1]["type"] == "run.completed"
    assert [e["seq"] for e in rejoined] == list(range(len(rejoined)))


def test_subscribing_after_the_run_is_over_still_replays_everything(
    live_url: str,
) -> None:
    run_id = live_run(live_url, live_plan(live_url))
    live = live_events(live_url, run_id)
    replayed = live_events(live_url, run_id)

    assert replayed == live


def test_the_demo_requirement_runs_end_to_end(live_url: str) -> None:
    source = httpx.post(
        f"{live_url}/api/plans", json={"example_id": "retail-analytics"}, timeout=30
    ).json()["plan"]["source_markdown"]
    run_id = live_run(live_url, live_plan(live_url, source), speed=5)

    events = live_events(live_url, run_id)

    assert events[-1]["type"] == "run.completed"
    assert len([e for e in events if e["type"] == "task.completed"]) == 7
    # The twelve artifacts listed in docs/05-DATA-AND-PIPELINE.md.
    assert len(events[-1]["artifact_ids"]) == 12
    # Code and documents stream in chunks; datasets and the finished dashboard
    # are announced whole, because there is no writing to watch.
    streamed = [e for e in events if e["type"] == "artifact.streaming"]
    assert len(streamed) == 8

    # The failure beat. Exactly one task fails recoverably and is retried once,
    # and the run still completes, which is the shape the whole demo turns on.
    failures = [e for e in events if e["type"] == "task.failed"]
    retries = [e for e in events if e["type"] == "task.retried"]
    assert [(e["task_id"], e["recoverable"]) for e in failures] == [("2.1", True)]
    assert [(e["task_id"], e["attempt"]) for e in retries] == [("2.1", 2)]

    # And the numbers on screen came from the file. 12,847 rows read, 771 of
    # them carrying the second timestamp format.
    probe = [e for e in events if e["type"] == "log.emitted" and "probe:" in e["message"]]
    assert len(probe) == 1
    assert "771 of 12,847" in probe[0]["message"]


def test_two_runs_at_one_seed_produce_identical_streams(live_url: str) -> None:
    """The gate's reproducibility check, over the serving path."""
    plan_id = live_plan(live_url)

    def stream_of(run_id: str) -> list[dict[str, Any]]:
        return [
            {k: v for k, v in e.items() if k != "run_id"}
            for e in live_events(live_url, run_id)
        ]

    first = stream_of(live_run(live_url, plan_id, speed=5))
    second = stream_of(live_run(live_url, plan_id, speed=5))

    assert first == second
    assert len(first) > 15


def test_the_same_seed_at_a_different_speed_reports_the_same_timestamps(
    live_url: str,
) -> None:
    """Event contract rule 2, over the serving path.

    A run at 5x reports the same `at` values as the same run at 2x, which is
    what keeps a sped-up rehearsal comparable with the real thing.
    """
    plan_id = live_plan(live_url)

    def ats(run_id: str) -> list[int]:
        return [e["at"] for e in live_events(live_url, run_id)]

    assert ats(live_run(live_url, plan_id, speed=5)) == ats(
        live_run(live_url, plan_id, speed=2)
    )


# ---------------------------------------------------------------- control


def wait_until_history_exceeds(run_id: str, count: int, timeout: float = 6.0) -> int:
    """Poll rather than guess at a sleep. Step pacing is jittered by design."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        size = len(get_registry().require(run_id).bus.history)
        if size > count:
            return size
        time.sleep(0.05)
    pytest.fail(f"run {run_id} published nothing beyond {count} within {timeout}s")


def test_pause_and_resume_report_the_run_state(client: TestClient) -> None:
    plan_id = client.post("/api/plans", json={"markdown": SMALL_REQUIREMENT}).json()["plan"]["id"]
    run_id = client.post("/api/runs", json={"plan_id": plan_id, "speed": 1}).json()["run_id"]

    assert client.post(f"/api/runs/{run_id}/control", json={"action": "pause"}).json()["paused"]
    assert not client.post(f"/api/runs/{run_id}/control", json={"action": "resume"}).json()[
        "paused"
    ]

    client.post(f"/api/runs/{run_id}/control", json={"action": "cancel"})


def test_pause_actually_stops_the_run(live_url: str) -> None:
    """Against a real server, because a paused run has to be observed running.

    Under TestClient the event loop only turns during a request, so a run looks
    paused whether or not pause works. That test would assert nothing.
    """
    run_id = live_run(live_url, live_plan(live_url), speed=1)
    wait_until_history_exceeds(run_id, 3)

    httpx.post(f"{live_url}/api/runs/{run_id}/control", json={"action": "pause"}, timeout=30)
    time.sleep(0.3)  # let whatever slice was in flight finish

    held = len(get_registry().require(run_id).bus.history)
    time.sleep(1.2)
    assert len(get_registry().require(run_id).bus.history) == held, (
        "the run kept publishing while paused"
    )

    httpx.post(f"{live_url}/api/runs/{run_id}/control", json={"action": "resume"}, timeout=30)
    wait_until_history_exceeds(run_id, held)

    httpx.post(f"{live_url}/api/runs/{run_id}/control", json={"action": "cancel"}, timeout=30)


def test_speed_can_be_changed_mid_run(client: TestClient) -> None:
    plan_id = client.post("/api/plans", json={"markdown": SMALL_REQUIREMENT}).json()["plan"]["id"]
    run_id = client.post("/api/runs", json={"plan_id": plan_id, "speed": 1}).json()["run_id"]

    acked = client.post(
        f"/api/runs/{run_id}/control", json={"action": "speed", "value": 5}
    ).json()
    assert acked["speed"] == 5

    client.post(f"/api/runs/{run_id}/control", json={"action": "cancel"})


def test_a_speed_change_needs_an_offered_value(client: TestClient) -> None:
    plan_id = client.post("/api/plans", json={"markdown": SMALL_REQUIREMENT}).json()["plan"]["id"]
    run_id = client.post("/api/runs", json={"plan_id": plan_id, "speed": 1}).json()["run_id"]

    response = client.post(
        f"/api/runs/{run_id}/control", json={"action": "speed", "value": 7}
    )
    assert response.status_code == 422

    client.post(f"/api/runs/{run_id}/control", json={"action": "cancel"})


def test_cancel_stops_the_run_and_leaves_the_registry_clean(live_url: str) -> None:
    run_id = live_run(live_url, live_plan(live_url), speed=1)
    wait_until_history_exceeds(run_id, 3)

    acked = httpx.post(
        f"{live_url}/api/runs/{run_id}/control", json={"action": "cancel"}, timeout=30
    ).json()
    assert acked["cancelled"] is True

    deadline = time.monotonic() + 10
    record = get_registry().require(run_id)
    while time.monotonic() < deadline:
        if record.task is not None and record.task.done():
            break
        time.sleep(0.05)

    assert record.task is not None
    assert record.task.done(), "the orchestrator task outlived the cancel"
    # Whatever was published before the cancel is still there to replay.
    assert len(record.bus.history) > 0
    # And a cancelled run publishes nothing further.
    settled = len(record.bus.history)
    time.sleep(0.5)
    assert len(record.bus.history) == settled
