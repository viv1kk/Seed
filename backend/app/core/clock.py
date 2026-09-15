"""Speed-aware sleep, pause, and cancellation.

Runners never call ``asyncio.sleep`` directly. Every wait goes through
``Clock.sleep``, which is what makes pause, resume, cancel, and the speed
multiplier work at all.

Three properties matter:

* ``elapsed_ms`` is *simulated* time and is unaffected by ``speed``. A run at 5x
  reports the same ``at`` values on its events as the same run at 1x, so logs
  stay comparable across speeds (event contract rule 2).
* ``cancel()`` raises ``asyncio.CancelledError`` into whoever is sleeping, and
  that exception must be allowed to propagate all the way out of the runner.
* concurrent sleepers share one timeline. Two agents each sleeping a second is
  one second of simulated time, not two.

That last one is why ``fork`` exists. A single accumulating counter is wrong the
moment two tasks run at once: both would add their sleeps to it, and a run with
two agents working in parallel would report timestamps racing ahead at double
speed. So each runner gets its own hand on the same clock, with its own
position, and the run's simulated time is the furthest any hand has reached.
Pause, cancel and speed stay shared, because those are properties of the run.

Two positions per hand, which is the subtle part. ``elapsed_ms`` advances
*during* a sleep, so that a paused run reports where it stopped rather than
where it started. ``settled_ms`` advances only when a sleep completes, and it is
the one ``run_elapsed_ms`` reads. The difference matters because a mid-sleep
position is a function of how much *real* time has passed, and real time is
divided by the speed multiplier in slices whose granularity scales with it. Take
the run clock from mid-sleep positions and a run at 5x stops reporting the same
timestamps as the same run at 1x, which is exactly what rule 2 forbids. Settled
positions are only ever exact sums of simulated sleeps, so they carry no trace
of real time at all.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Final

# Real seconds per wait slice. A long sleep is served as a run of slices so that
# a mid-sleep pause() or set_speed() is observed promptly rather than at the end
# of the wait.
#
# The slice is measured in *real* time, not simulated time, and that matters on
# Windows: the event loop timer granularity there is around 15ms, so slicing a
# sleep into fixed simulated chunks makes every chunk cost a full timer tick and
# a run at 20x ends up barely faster than a run at 1x. Slicing by real duration
# means a fast run is one short wait, and only a slow run is subdivided.
SLICE_SECONDS: Final[float] = 0.025

# Float accumulation floor. Below this, the remaining sleep is nothing.
_EPSILON_MS: Final[float] = 1e-9


class ClockCancelled(asyncio.CancelledError):
    """Raised into a sleeper when the run is cancelled."""


@dataclass
class _Shared:
    """Run-wide clock state. One instance per run, held by every hand."""

    speed: int
    cancelled: asyncio.Event = field(default_factory=asyncio.Event)
    resumed: asyncio.Event = field(default_factory=asyncio.Event)
    hands: list["Clock"] = field(default_factory=list)


class Clock:
    def __init__(
        self,
        speed: int = 1,
        *,
        _shared: _Shared | None = None,
        _position_ms: int = 0,
    ) -> None:
        if _shared is None:
            if speed < 1:
                raise ValueError("speed must be at least 1")
            _shared = _Shared(speed=speed)
            _shared.resumed.set()
        self._shared = _shared
        self._elapsed_ms = _position_ms
        self._settled_ms = _position_ms
        self._shared.hands.append(self)

    def fork(self, at_ms: int | None = None) -> "Clock":
        """A second hand on the same run clock.

        Each runner gets one. It shares pause, cancel and speed with every other
        hand, and keeps its own position so that parallel work does not make
        simulated time run fast.

        The default start is the run clock, so a task that starts late does not
        begin its timestamps at zero. ``at_ms`` overrides it, for a caller that
        knows better where a hand belongs.
        """
        position = self.run_elapsed_ms if at_ms is None else at_ms
        return Clock(_shared=self._shared, _position_ms=position)

    @property
    def speed(self) -> int:
        return self._shared.speed

    @property
    def elapsed_ms(self) -> int:
        """This hand's own simulated position, in ms since the run began.

        Advances during a sleep, so a paused run reports where it stopped.
        """
        return self._elapsed_ms

    @property
    def settled_ms(self) -> int:
        """This hand's position as of its last completed sleep.

        Only ever an exact sum of simulated sleeps, so unlike ``elapsed_ms`` it
        carries no trace of real elapsed time. See the module docstring.
        """
        return self._settled_ms

    @property
    def run_elapsed_ms(self) -> int:
        """The run's simulated clock: the furthest any hand has settled.

        This is what the event bus stamps on every event as ``at``, and what a
        new hand forks from.
        """
        return max(hand._settled_ms for hand in self._shared.hands)

    @property
    def is_paused(self) -> bool:
        return not self._shared.resumed.is_set()

    @property
    def is_cancelled(self) -> bool:
        return self._shared.cancelled.is_set()

    def set_speed(self, speed: int) -> None:
        if speed < 1:
            raise ValueError("speed must be at least 1")
        self._shared.speed = speed

    def pause(self) -> None:
        self._shared.resumed.clear()

    def resume(self) -> None:
        self._shared.resumed.set()

    def cancel(self) -> None:
        self._shared.cancelled.set()
        # Release anyone parked on the pause gate so they reach the cancel check.
        self._shared.resumed.set()

    async def sleep(self, ms: int) -> None:
        """Advance simulated time by ``ms``, really waiting ``ms / speed``.

        Raises ``ClockCancelled`` (an ``asyncio.CancelledError``) if the run is
        cancelled before or during the wait.
        """
        if ms < 0:
            raise ValueError("ms must not be negative")
        self._raise_if_cancelled()

        # From the settled position, not the live one. The two are equal here
        # in every reachable case, and anchoring to the settled one means a
        # sleep that was interrupted can never leave the hand drifting.
        started_at = self._settled_ms
        remaining = float(ms)

        while remaining > _EPSILON_MS:
            await self._await_resume()
            self._raise_if_cancelled()

            # Speed is re-read every slice, so a change partway through a sleep
            # takes effect on the rest of it.
            real_remaining = remaining / 1000 / self.speed
            real_slice = min(SLICE_SECONDS, real_remaining)
            await self._wait_real(real_slice)

            remaining -= real_slice * 1000 * self.speed
            # The live position moves during the sleep so that a pause reports
            # where the run stopped. The settled position does not, and it is
            # the settled one the run clock reads.
            self._elapsed_ms = started_at + round(ms - max(remaining, 0.0))

        # Assign the total exactly rather than letting float error accumulate
        # across a run of several thousand sleeps. Settling here and only here
        # is what keeps the run clock free of real time.
        self._elapsed_ms = self._settled_ms = started_at + ms
        self._raise_if_cancelled()

    async def _wait_real(self, seconds: float) -> None:
        """Sleep for real, but wake immediately if the run is cancelled."""
        try:
            await asyncio.wait_for(self._shared.cancelled.wait(), timeout=seconds)
        except TimeoutError:
            return  # The normal path: the slice elapsed without a cancel.
        raise ClockCancelled

    async def _await_resume(self) -> None:
        if self._shared.resumed.is_set():
            return
        await self._shared.resumed.wait()

    def _raise_if_cancelled(self) -> None:
        if self._shared.cancelled.is_set():
            raise ClockCancelled
