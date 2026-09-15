"""The event bus: one queue-backed fan-out per run, with full replay.

Responsibilities, and deliberately nothing else:

* assign ``seq``, monotonic from 0 (event contract rule 1). Runners emit events
  with ``seq=0`` and never set it themselves.
* assign ``at``, the run's simulated clock (event contract rule 2). Runners do
  not set this one either.
* retain every event for the run, so ``GET /api/runs/{id}/stream`` can replay
  from ``seq=0``. Someone will refresh the page mid-run during the demo.
* fan out to any number of live subscribers.

``seq`` and ``at`` are stamped together, here, for the same reason.

A runner reading its own clock hand cannot produce a coherent ``at``: two
runners work at once, each hand sits at its own position, and their events
interleave in whatever order they arrive. Stamped at the emit site, the log
walks backwards every time the stream crosses from one agent to the other. Sort
the log by ``at`` afterwards and it looks right while telling you the wrong
thing, because it no longer shows the order in which the run actually did what
it did.

So ``at`` is a property of the *stream*, not of the emitting hand: the run's
simulated clock at the moment the event enters the stream, which is the furthest
any hand has reached. Publishing is serialised and the furthest-reached only
moves forward, so ``at`` rises with ``seq`` without anything having to reorder
it. And because it is only ever built from settled hand positions, which are
exact sums of simulated sleeps, it stays free of real elapsed time and so of the
speed multiplier. That is what rule 2 asks for.

Each hand is sampled as it publishes rather than read live, which is the part
worth explaining. A hand advances on its own schedule inside its own
``asyncio.Task``, so reading every hand at publish time answers "had the other
runner finished its current sleep yet", and that is a question about real
elapsed time. Two runs at one seed then disagree about ``at`` by however long
that sleep had left, which was exactly the failure this replaced. Sampling a
hand when it speaks makes the run clock a function of the event order alone, and
the event order is already what the seed fixes. The high-water mark is the same
maximum either way; it is only read at reproducible moments.
"""

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Final

from app.core.clock import Clock
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
        self._at = 0
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

    @property
    def at(self) -> int:
        """The run's simulated clock: the furthest any hand has reached."""
        return self._at

    async def publish(self, event: SeedEvent, hand: Clock | None = None) -> SeedEvent:
        """Stamp ``seq`` and ``at``, retain, and fan out. Returns the stamped copy.

        ``hand`` is the clock of whichever runner emitted this, and passing it is
        how that hand joins the run clock. Omit it for an event the run itself
        emitted rather than a runner: those carry the clock as it already
        stands, which is what "now" means for them.

        Whatever the caller put in ``seq`` and ``at`` is overwritten. The
        argument is not mutated; the stamped copy is what reaches subscribers
        and what is retained for replay.
        """
        if self._closed:
            raise RuntimeError(f"run {self._run_id} bus is closed")

        if hand is not None:
            self._at = max(self._at, hand.settled_ms)

        stamped: SeedEvent = event.model_copy(
            update={"seq": self._next_seq, "at": self._at}
        )
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
