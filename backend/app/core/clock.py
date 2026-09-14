"""Speed-aware sleep, pause, and cancellation.

Runners never call ``asyncio.sleep`` directly. Every wait goes through
``Clock.sleep``, which is what makes pause, resume, cancel, and the speed
multiplier work at all.

Two properties matter:

* ``elapsed_ms`` is *simulated* time and is unaffected by ``speed``. A run at 5x
  reports the same ``at`` values on its events as the same run at 1x, so logs
  stay comparable across speeds (event contract rule 2).
* ``cancel()`` raises ``asyncio.CancelledError`` into whoever is sleeping, and
  that exception must be allowed to propagate all the way out of the runner.
"""

import asyncio
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


class Clock:
    def __init__(self, speed: int = 1) -> None:
        if speed < 1:
            raise ValueError("speed must be at least 1")
        self._speed = speed
        self._elapsed_ms = 0
        self._cancelled = asyncio.Event()
        self._resumed = asyncio.Event()
        self._resumed.set()

    @property
    def speed(self) -> int:
        return self._speed

    @property
    def elapsed_ms(self) -> int:
        """Simulated milliseconds since the run began. Speed-independent."""
        return self._elapsed_ms

    @property
    def is_paused(self) -> bool:
        return not self._resumed.is_set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def set_speed(self, speed: int) -> None:
        if speed < 1:
            raise ValueError("speed must be at least 1")
        self._speed = speed

    def pause(self) -> None:
        self._resumed.clear()

    def resume(self) -> None:
        self._resumed.set()

    def cancel(self) -> None:
        self._cancelled.set()
        # Release anyone parked on the pause gate so they reach the cancel check.
        self._resumed.set()

    async def sleep(self, ms: int) -> None:
        """Advance simulated time by ``ms``, really waiting ``ms / speed``.

        Raises ``ClockCancelled`` (an ``asyncio.CancelledError``) if the run is
        cancelled before or during the wait.
        """
        if ms < 0:
            raise ValueError("ms must not be negative")
        self._raise_if_cancelled()

        started_at = self._elapsed_ms
        remaining = float(ms)

        while remaining > _EPSILON_MS:
            await self._await_resume()
            self._raise_if_cancelled()

            # Speed is re-read every slice, so a change partway through a sleep
            # takes effect on the rest of it.
            real_remaining = remaining / 1000 / self._speed
            real_slice = min(SLICE_SECONDS, real_remaining)
            await self._wait_real(real_slice)

            remaining -= real_slice * 1000 * self._speed
            # Simulated time advances during the sleep, not only at the end, so
            # an event emitted by another task mid-sleep gets a sensible `at`.
            self._elapsed_ms = started_at + round(ms - max(remaining, 0.0))

        # Assign the total exactly rather than letting float error accumulate
        # across a run of several thousand sleeps.
        self._elapsed_ms = started_at + ms
        self._raise_if_cancelled()

    async def _wait_real(self, seconds: float) -> None:
        """Sleep for real, but wake immediately if the run is cancelled."""
        try:
            await asyncio.wait_for(self._cancelled.wait(), timeout=seconds)
        except TimeoutError:
            return  # The normal path: the slice elapsed without a cancel.
        raise ClockCancelled

    async def _await_resume(self) -> None:
        if self._resumed.is_set():
            return
        await self._resumed.wait()

    def _raise_if_cancelled(self) -> None:
        if self._cancelled.is_set():
            raise ClockCancelled
