"""In-memory run registry. No persistence, by design.

A run's reproducible state is created in one place, ``create_run``, so that the
bus, the clock, and the seeded generator for a run can never be assembled
inconsistently.

Scope note: this holds runs only. Plan storage arrives with ``POST /api/plans``
in phase 1, and the retained derived frame for the cross-filter query endpoint
arrives in phase 3.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field

from app.core.clock import Clock
from app.core.events import EventBus
from app.core.rng import DEFAULT_SEED, Rng, make_rng


@dataclass
class RunRecord:
    run_id: str
    plan_id: str
    seed: int
    speed: int
    bus: EventBus
    clock: Clock
    rng: Rng
    created_at: float
    task: asyncio.Task[None] | None = field(default=None)


class RunNotFoundError(KeyError):
    """Raised by ``require`` when a run id is unknown."""


class RunRegistry:
    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}

    def create_run(
        self,
        plan_id: str,
        seed: int = DEFAULT_SEED,
        speed: int = 1,
    ) -> RunRecord:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        record = RunRecord(
            run_id=run_id,
            plan_id=plan_id,
            seed=seed,
            speed=speed,
            bus=EventBus(run_id),
            clock=Clock(speed=speed),
            rng=make_rng(seed),
            created_at=time.time(),
        )
        self._runs[run_id] = record
        return record

    def get(self, run_id: str) -> RunRecord | None:
        return self._runs.get(run_id)

    def require(self, run_id: str) -> RunRecord:
        record = self._runs.get(run_id)
        if record is None:
            raise RunNotFoundError(run_id)
        return record

    def list_runs(self) -> list[RunRecord]:
        """Oldest first."""
        return sorted(self._runs.values(), key=lambda r: r.created_at)

    def remove(self, run_id: str) -> None:
        self._runs.pop(run_id, None)
