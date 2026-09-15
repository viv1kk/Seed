"""In-memory run registry. No persistence, by design.

A run's reproducible state is created in one place, ``create_run``, so that the
bus, the clock, and the seeded generator for a run can never be assembled
inconsistently.

The run keeps its kernel after it finishes. That is what lets the delivered
dashboard go on cross-filtering: the derived frame is still in memory, and
``POST /api/runs/{id}/query`` re-aggregates the same frame the run itself
reported from. Nothing is persisted; a restart is a clean slate, by design.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field

from app.core.clock import Clock
from app.core.events import EventBus
from app.core.rng import DEFAULT_SEED, Rng, make_rng
from app.core.types import Artifact, Plan
from app.pipeline.kernel import PolarsKernel


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
    kernel: PolarsKernel
    task: asyncio.Task[None] | None = field(default=None)


class RunNotFoundError(KeyError):
    """Raised by ``require`` when a run id is unknown."""


class PlanNotFoundError(KeyError):
    """Raised by ``require_plan`` when a plan id is unknown."""


class RunRegistry:
    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._plans: dict[str, Plan] = {}

    # ------------------------------------------------------------ plans

    def put_plan(self, plan: Plan) -> Plan:
        """Retain a parsed plan so a later POST /api/runs can find it by id."""
        self._plans[plan.id] = plan
        return plan

    def get_plan(self, plan_id: str) -> Plan | None:
        return self._plans.get(plan_id)

    def require_plan(self, plan_id: str) -> Plan:
        plan = self._plans.get(plan_id)
        if plan is None:
            raise PlanNotFoundError(plan_id)
        return plan

    # ------------------------------------------------------------ runs

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
            kernel=PolarsKernel(),
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

    def find_artifact(self, artifact_id: str) -> tuple[RunRecord, Artifact] | None:
        """Locate an artifact by id, newest run first.

        Artifact ids are keyed by plan and task rather than by run, so two runs
        of the same document produce the same ids. Searching newest first means
        a link opened during a run resolves against that run rather than against
        a stale one still sitting in memory.
        """
        for record in reversed(self.list_runs()):
            artifact = record.kernel.artifacts.get(artifact_id)
            if artifact is not None:
                return record, artifact
        return None

    def remove(self, run_id: str) -> None:
        self._runs.pop(run_id, None)
