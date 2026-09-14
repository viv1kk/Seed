"""The event bus: one queue-backed fan-out per run, with full replay.

Responsibilities, and deliberately nothing else:

* assign ``seq``, monotonic from 0 (event contract rule 1). Runners emit events
  with ``seq=0`` and never set it themselves.
* retain every event for the run, so ``GET /api/runs/{id}/stream`` can replay
  from ``seq=0``. Someone will refresh the page mid-run during the demo.
* fan out to any number of live subscribers.

``at`` is not the bus's business; it comes from the clock at the emit site.
"""

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Final

from app.core.types import SeedEvent

# Pushed to every subscriber queue by close(), so subscribers finish cleanly
# rather than hanging on a queue that will never receive another event. None is
# usable as the sentinel because no event is ever None, and it keeps the queue
# element type narrow enough for mypy to follow.
_SENTINEL: Final[None] = None


class EventBus:
    def __init__(self, run_id: str) -> None:
        self._run_id = run_id
        self._history: list[SeedEvent] = []
        self._subscribers: list[asyncio.Queue[SeedEvent | None]] = []
        self._next_seq = 0
        self._closed = False

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def history(self) -> Sequence[SeedEvent]:
        """Every event published so far, in seq order."""
        return tuple(self._history)

    async def publish(self, event: SeedEvent) -> SeedEvent:
        """Stamp ``seq``, retain, and fan out. Returns the stamped copy.

        The argument is not mutated; the stamped copy is what reaches
        subscribers and what is retained for replay.
        """
        if self._closed:
            raise RuntimeError(f"run {self._run_id} bus is closed")

        stamped: SeedEvent = event.model_copy(update={"seq": self._next_seq})
        self._next_seq += 1
        self._history.append(stamped)
        for queue in self._subscribers:
            queue.put_nowait(stamped)
        return stamped

    async def subscribe(self) -> AsyncIterator[SeedEvent]:
        """Replay from seq=0, then follow live events.

        The queue is registered *before* history is snapshotted, so an event
        published during the replay is buffered rather than lost. Anything that
        arrives on the queue with a seq already replayed is then dropped, so a
        subscriber sees each event exactly once, in order.
        """
        queue: asyncio.Queue[SeedEvent | None] = asyncio.Queue()
        # Whether the bus was already closed when this subscriber arrived. It
        # cannot be re-read later: if the bus closes *during* the replay, the
        # sentinel is already sitting in this queue and the live loop must run
        # to reach it, along with anything published just before it. Only a
        # subscriber that arrived after the close has no sentinel coming.
        closed_on_arrival = self._closed
        self._subscribers.append(queue)
        try:
            replayed = tuple(self._history)
            for event in replayed:
                yield event
            last_replayed_seq = replayed[-1].seq if replayed else -1

            if closed_on_arrival:
                return

            while True:
                item = await queue.get()
                if item is _SENTINEL:
                    return
                if item.seq <= last_replayed_seq:
                    continue  # Already delivered during replay.
                yield item
        finally:
            self._subscribers.remove(queue)

    async def close(self) -> None:
        """Stop accepting events and release every subscriber."""
        if self._closed:
            return
        self._closed = True
        for queue in self._subscribers:
            queue.put_nowait(_SENTINEL)
