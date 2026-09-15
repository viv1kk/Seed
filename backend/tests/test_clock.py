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


# ---------------------------------------------------------------- forked hands


@pytest.mark.asyncio
async def test_concurrent_hands_do_not_make_simulated_time_run_fast() -> None:
    """Two agents each sleeping a second is one second of run time, not two.

    A single accumulating counter gets this wrong, and the error only appears
    once tasks actually run in parallel, where it would show as timestamps
    racing ahead of the run.
    """
    clock = Clock(speed=20)
    first = clock.fork()
    second = clock.fork()

    await asyncio.gather(first.sleep(1_000), second.sleep(1_000))

    assert first.elapsed_ms == 1_000
    assert second.elapsed_ms == 1_000
    assert clock.run_elapsed_ms == 1_000, "the run clock summed its hands"


@pytest.mark.asyncio
async def test_a_hand_starts_where_the_run_clock_is() -> None:
    """A task that starts late does not begin its timestamps at zero."""
    clock = Clock(speed=20)
    first = clock.fork()
    await first.sleep(500)

    second = clock.fork()
    assert second.elapsed_ms == 500

    await second.sleep(200)
    assert second.elapsed_ms == 700
    assert clock.run_elapsed_ms == 700


@pytest.mark.asyncio
async def test_pause_and_cancel_are_shared_by_every_hand() -> None:
    clock = Clock()
    hand = clock.fork()

    # Read into locals before asserting. mypy narrows `hand.is_paused` on an
    # assert and cannot see that `clock.resume()` mutates the state behind it,
    # so asserting directly makes everything after look unreachable.
    clock.pause()
    paused = hand.is_paused
    clock.resume()
    released = not hand.is_paused

    assert paused, "pausing the run clock did not pause a forked hand"
    assert released, "resuming the run clock did not release a forked hand"

    clock.cancel()
    assert hand.is_cancelled
    with pytest.raises(ClockCancelled):
        await hand.sleep(10)


@pytest.mark.asyncio
async def test_speed_changes_reach_every_hand() -> None:
    clock = Clock(speed=1)
    hand = clock.fork()
    clock.set_speed(10)
    assert hand.speed == 10
