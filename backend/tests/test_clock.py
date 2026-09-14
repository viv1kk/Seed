"""The clock carries pause, resume, cancel, and the speed multiplier."""

import asyncio
import time

import pytest

from app.core.clock import Clock, ClockCancelled


@pytest.mark.asyncio
async def test_sleep_advances_simulated_time_by_exactly_the_requested_amount() -> None:
    clock = Clock()
    await clock.sleep(120)
    assert clock.elapsed_ms == 120


@pytest.mark.asyncio
async def test_simulated_time_is_unaffected_by_speed() -> None:
    """Contract rule 2, and the reason logs are comparable across speeds."""
    slow = Clock(speed=1)
    fast = Clock(speed=20)

    await slow.sleep(100)
    await fast.sleep(100)

    assert slow.elapsed_ms == fast.elapsed_ms == 100


@pytest.mark.asyncio
async def test_speed_shortens_the_real_wait() -> None:
    started = time.monotonic()
    await Clock(speed=20).sleep(400)
    real_ms = (time.monotonic() - started) * 1000

    # 400ms of simulated time at 20x is 20ms of real time. The bound is loose
    # because it is a scheduler, but it must be nowhere near 400ms.
    assert real_ms < 200


@pytest.mark.asyncio
async def test_cancel_raises_into_the_sleeper() -> None:
    clock = Clock()

    async def sleeper() -> None:
        await clock.sleep(10_000)

    task = asyncio.create_task(sleeper())
    await asyncio.sleep(0.01)
    clock.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_cancel_is_observed_before_a_sleep_even_begins() -> None:
    clock = Clock()
    clock.cancel()

    with pytest.raises(ClockCancelled):
        await clock.sleep(50)


@pytest.mark.asyncio
async def test_cancel_interrupts_promptly_rather_than_at_the_end_of_the_sleep() -> None:
    clock = Clock()
    started = time.monotonic()

    async def sleeper() -> None:
        await clock.sleep(5_000)

    task = asyncio.create_task(sleeper())
    await asyncio.sleep(0.02)
    clock.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert (time.monotonic() - started) * 1000 < 500


@pytest.mark.asyncio
async def test_pause_holds_simulated_time_still_and_resume_releases_it() -> None:
    # Speed 1 on purpose: the sleep is then served as many real slices, so there
    # is genuinely a middle of the sleep to pause in.
    clock = Clock(speed=1)

    async def sleeper() -> None:
        await clock.sleep(400)

    task = asyncio.create_task(sleeper())
    await asyncio.sleep(0.05)
    clock.pause()
    await asyncio.sleep(0.05)  # let the slice already in flight finish

    paused_at = clock.elapsed_ms
    assert clock.is_paused
    assert 0 < paused_at < 400

    await asyncio.sleep(0.1)
    assert clock.elapsed_ms == paused_at, "simulated time advanced while paused"

    clock.resume()
    await task
    assert clock.elapsed_ms == 400


@pytest.mark.asyncio
async def test_cancel_releases_a_paused_sleeper() -> None:
    """A paused run must still be cancellable, or Reset hangs."""
    clock = Clock()
    clock.pause()

    async def sleeper() -> None:
        await clock.sleep(10_000)

    task = asyncio.create_task(sleeper())
    await asyncio.sleep(0.01)
    clock.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_sleep_of_zero_is_a_no_op() -> None:
    clock = Clock()
    await clock.sleep(0)
    assert clock.elapsed_ms == 0


def test_speed_must_be_at_least_one() -> None:
    with pytest.raises(ValueError, match="speed"):
        Clock(speed=0)
    with pytest.raises(ValueError, match="speed"):
        Clock().set_speed(-1)


@pytest.mark.asyncio
async def test_negative_sleep_is_rejected() -> None:
    with pytest.raises(ValueError, match="negative"):
        await Clock().sleep(-1)
