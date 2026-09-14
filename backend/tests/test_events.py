"""The event bus assigns seq, retains everything, and replays without gaps."""

import asyncio

import pytest

from app.core.events import EventBus
from app.core.types import LogEmitted, RunCompleted, RunStarted, SeedEvent


def _started(run_id: str = "r1") -> RunStarted:
    return RunStarted(run_id=run_id, seq=0, at=0, requirement_title="t", seed=1, speed=1)


def _log(message: str, run_id: str = "r1") -> LogEmitted:
    return LogEmitted(
        run_id=run_id, seq=0, at=0, level="info", message=message, source="runtime"
    )


@pytest.mark.asyncio
async def test_publish_assigns_monotonic_seq_from_zero() -> None:
    bus = EventBus("r1")
    for _ in range(5):
        await bus.publish(_log("x"))

    assert [event.seq for event in bus.history] == [0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_publish_does_not_mutate_the_event_it_is_given() -> None:
    """A runner must be able to emit without caring what seq it lands on."""
    bus = EventBus("r1")
    await bus.publish(_log("first"))

    original = _log("second")
    stamped = await bus.publish(original)

    assert original.seq == 0
    assert stamped.seq == 1


@pytest.mark.asyncio
async def test_a_subscriber_replays_the_whole_run_from_seq_zero() -> None:
    """Someone will refresh the page mid-run during the demo."""
    bus = EventBus("r1")
    await bus.publish(_started())
    await bus.publish(_log("one"))
    await bus.publish(_log("two"))

    received: list[SeedEvent] = []
    async for event in bus.subscribe():
        received.append(event)
        if len(received) == 3:
            break

    assert [event.seq for event in received] == [0, 1, 2]


@pytest.mark.asyncio
async def test_a_subscriber_receives_live_events_after_the_replay() -> None:
    bus = EventBus("r1")
    await bus.publish(_started())

    received: list[SeedEvent] = []

    async def reader() -> None:
        async for event in bus.subscribe():
            received.append(event)

    task = asyncio.create_task(reader())
    await asyncio.sleep(0)  # let the subscription register and replay

    await bus.publish(_log("live"))
    await asyncio.sleep(0)
    await bus.close()
    await task

    assert [event.seq for event in received] == [0, 1]


@pytest.mark.asyncio
async def test_an_event_published_during_the_replay_is_delivered_exactly_once() -> None:
    """The gap-and-duplicate case the subscribe ordering exists to prevent."""
    bus = EventBus("r1")
    for index in range(3):
        await bus.publish(_log(f"backlog {index}"))

    received: list[SeedEvent] = []
    subscription = bus.subscribe()

    # Take the first replayed event, publish while the replay is mid-flight,
    # then drain the rest.
    received.append(await anext(subscription))
    await bus.publish(_log("published mid replay"))
    await bus.close()

    async for event in subscription:
        received.append(event)

    seqs = [event.seq for event in received]
    assert seqs == [0, 1, 2, 3]
    assert len(seqs) == len(set(seqs))


@pytest.mark.asyncio
async def test_two_subscribers_both_see_everything() -> None:
    bus = EventBus("r1")
    await bus.publish(_started())

    async def drain() -> list[int]:
        return [event.seq async for event in bus.subscribe()]

    first = asyncio.create_task(drain())
    second = asyncio.create_task(drain())
    await asyncio.sleep(0)

    await bus.publish(_log("shared"))
    await asyncio.sleep(0)
    await bus.close()

    assert await first == [0, 1]
    assert await second == [0, 1]


@pytest.mark.asyncio
async def test_subscribing_after_close_replays_and_then_stops() -> None:
    bus = EventBus("r1")
    await bus.publish(_started())
    await bus.publish(RunCompleted(run_id="r1", seq=0, at=9, duration_ms=9, artifact_ids=[]))
    await bus.close()

    assert [event.seq async for event in bus.subscribe()] == [0, 1]


@pytest.mark.asyncio
async def test_publishing_to_a_closed_bus_is_an_error() -> None:
    bus = EventBus("r1")
    await bus.close()

    with pytest.raises(RuntimeError, match="closed"):
        await bus.publish(_log("too late"))


@pytest.mark.asyncio
async def test_close_is_idempotent() -> None:
    bus = EventBus("r1")
    await bus.close()
    await bus.close()
    assert bus.closed


@pytest.mark.asyncio
async def test_history_is_a_snapshot_not_a_live_view() -> None:
    bus = EventBus("r1")
    await bus.publish(_started())
    snapshot = bus.history
    await bus.publish(_log("after"))

    assert len(snapshot) == 1
    assert len(bus.history) == 2
