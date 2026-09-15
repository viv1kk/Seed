"""The event bus assigns seq and at, retains everything, and replays in order."""

import asyncio

import pytest

from app.core.clock import Clock
from app.core.events import EventBus
from app.core.types import LogEmitted, RunCompleted, RunStarted, SeedEvent


def _bus(run_id: str = "r1") -> EventBus:
    return EventBus(run_id)


def _started(run_id: str = "r1") -> RunStarted:
    return RunStarted(run_id=run_id, seq=0, at=0, requirement_title="t", seed=1, speed=1)


def _log(message: str, run_id: str = "r1") -> LogEmitted:
    return LogEmitted(
        run_id=run_id, seq=0, at=0, level="info", message=message, source="runtime"
    )


@pytest.mark.asyncio
async def test_publish_assigns_monotonic_seq_from_zero() -> None:
    bus = _bus()
    for _ in range(5):
        await bus.publish(_log("x"))

    assert [event.seq for event in bus.history] == [0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_publish_does_not_mutate_the_event_it_is_given() -> None:
    """A runner must be able to emit without caring what seq it lands on."""
    bus = _bus()
    await bus.publish(_log("first"))

    original = _log("second")
    stamped = await bus.publish(original)

    assert original.seq == 0
    assert stamped.seq == 1


@pytest.mark.asyncio
async def test_a_subscriber_replays_the_whole_run_from_seq_zero() -> None:
    """Someone will refresh the page mid-run during the demo."""
    bus = _bus()
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
    bus = _bus()
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
    bus = _bus()
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
    bus = _bus()
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
    bus = _bus()
    await bus.publish(_started())
    await bus.publish(RunCompleted(run_id="r1", seq=0, at=9, duration_ms=9, artifact_ids=[]))
    await bus.close()

    assert [event.seq async for event in bus.subscribe()] == [0, 1]


@pytest.mark.asyncio
async def test_publishing_to_a_closed_bus_is_an_error() -> None:
    bus = _bus()
    await bus.close()

    with pytest.raises(RuntimeError, match="closed"):
        await bus.publish(_log("too late"))


@pytest.mark.asyncio
async def test_close_is_idempotent() -> None:
    bus = _bus()
    await bus.close()
    await bus.close()
    assert bus.closed


@pytest.mark.asyncio
async def test_history_is_a_snapshot_not_a_live_view() -> None:
    bus = _bus()
    await bus.publish(_started())
    snapshot = bus.history
    await bus.publish(_log("after"))

    assert len(snapshot) == 1
    assert len(bus.history) == 2


# ---------------------------------------------------------------- the run clock


@pytest.mark.asyncio
async def test_publish_stamps_at_from_the_hand_that_emitted() -> None:
    clock = Clock(speed=200)
    hand = clock.fork()
    bus = _bus()

    await hand.sleep(400)
    published = await bus.publish(_log("after four hundred"), hand)

    assert published.at == 400


@pytest.mark.asyncio
async def test_at_never_goes_backwards_when_two_hands_interleave() -> None:
    """Contract rule 2, and the reason `at` is stamped here rather than emitted.

    The second hand is behind the first. Its events still belong where the run
    has got to, because `at` describes the stream and not the hand.
    """
    clock = Clock(speed=200)
    ahead, behind = clock.fork(), clock.fork()
    bus = _bus()

    await ahead.sleep(5_000)
    await behind.sleep(800)

    first = await bus.publish(_log("from the hand in front"), ahead)
    second = await bus.publish(_log("from the hand behind"), behind)

    assert first.at == 5_000
    assert second.at == 5_000, "an event from a lagging hand rewound the run clock"
    assert [event.at for event in bus.history] == sorted(event.at for event in bus.history)


@pytest.mark.asyncio
async def test_an_event_with_no_hand_carries_the_clock_as_it_stands() -> None:
    """Run-level events: `run.started`, `task.ready`, `run.completed`."""
    clock = Clock(speed=200)
    hand = clock.fork()
    bus = _bus()

    opening = await bus.publish(_started())
    await hand.sleep(1_200)
    await bus.publish(_log("some work happened"), hand)
    closing = await bus.publish(
        RunCompleted(run_id="r1", seq=0, at=0, duration_ms=0, artifact_ids=[])
    )

    assert opening.at == 0
    assert closing.at == 1_200


@pytest.mark.asyncio
async def test_a_hand_mid_sleep_does_not_move_the_run_clock() -> None:
    """Otherwise `at` would depend on real elapsed time, and so on the speed.

    The hand is deliberately read while it is partway through a sleep. Its
    settled position, the one the bus uses, is still where the sleep began.
    """
    clock = Clock(speed=1)
    hand = clock.fork()
    bus = _bus()

    await hand.sleep(100)
    sleeper = asyncio.create_task(hand.sleep(1_000))
    await asyncio.sleep(0.1)

    published = await bus.publish(_log("mid sleep"), hand)
    assert hand.elapsed_ms > 100, "the test did not catch the hand mid-sleep"
    assert published.at == 100

    await sleeper
