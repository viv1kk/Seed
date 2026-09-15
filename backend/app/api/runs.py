"""Start a run, watch it, control it, and query what it produced.

The stream replays from ``seq=0`` before following live events, so a refresh
mid-run recovers the whole run rather than joining late. Someone will refresh
during the demo.

The query endpoint is the one that changes what the dashboard is. The run's
derived frame stays in the registry after the last agent goes idle, so brushing
a date range or clicking a category re-runs the same five aggregations in Polars
over the same frame and answers in single-digit milliseconds. The dashboard is
therefore a live surface over the pipeline rather than a picture of one, and a
canned screenshot cannot do it.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator
from sse_starlette.sse import EventSourceResponse

from app.api.deps import Registry
from app.core.registry import RunRecord, RunRegistry
from app.core.rng import DEFAULT_SEED
from app.core.types import AggregateReady, Filters, NoAnalyticalTable, QueryResult
from app.orchestrator.orchestrator import Orchestrator, default_runner_for
from app.pipeline.aggregate import aggregate

router = APIRouter(prefix="/api", tags=["runs"])

ALLOWED_SPEEDS = (1, 2, 5)


class RunRequest(BaseModel):
    plan_id: str
    seed: int = DEFAULT_SEED
    speed: int = 1

    @model_validator(mode="after")
    def speed_is_offered(self) -> "RunRequest":
        if self.speed not in ALLOWED_SPEEDS:
            raise ValueError(f"speed must be one of {ALLOWED_SPEEDS}")
        return self


class RunCreated(BaseModel):
    run_id: str


class ControlRequest(BaseModel):
    action: Literal["pause", "resume", "cancel", "speed"]
    value: int | None = Field(default=None)

    @model_validator(mode="after")
    def speed_carries_a_value(self) -> "ControlRequest":
        if self.action == "speed" and self.value not in ALLOWED_SPEEDS:
            raise ValueError(f"speed requires value in {ALLOWED_SPEEDS}")
        return self


class ControlAck(BaseModel):
    run_id: str
    action: str
    speed: int
    paused: bool
    cancelled: bool


def _require(registry: RunRegistry, run_id: str) -> RunRecord:
    record = registry.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No run with id {run_id!r}")
    return record


@router.post("/runs")
async def create_run(request: RunRequest, registry: Registry) -> RunCreated:
    """Create a run and start executing it.

    Execution begins here rather than on subscribe, because the bus retains
    everything and the stream replays from seq=0. Nothing is lost by the client
    connecting a moment later, and tying execution to a subscriber would mean a
    run that stalls when someone closes a tab.
    """
    plan = registry.get_plan(request.plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"No plan with id {request.plan_id!r}")

    record = registry.create_run(request.plan_id, seed=request.seed, speed=request.speed)
    orchestrator = Orchestrator(
        run_id=record.run_id,
        plan=plan,
        bus=record.bus,
        clock=record.clock,
        rng=record.rng,
        kernel=record.kernel,
        runner_for=default_runner_for,
        seed=record.seed,
    )
    record.task = asyncio.create_task(
        orchestrator.execute(), name=f"run-{record.run_id}"
    )
    return RunCreated(run_id=record.run_id)


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str, registry: Registry) -> EventSourceResponse:
    record = _require(registry, run_id)

    async def publisher() -> AsyncIterator[dict[str, str]]:
        async for event in record.bus.subscribe():
            yield {
                "event": event.type,
                "id": str(event.seq),
                "data": event.model_dump_json(),
            }

    return EventSourceResponse(publisher())


@router.post("/runs/{run_id}/control")
async def control_run(
    run_id: str, request: ControlRequest, registry: Registry
) -> ControlAck:
    record = _require(registry, run_id)
    clock = record.clock

    match request.action:
        case "pause":
            clock.pause()
        case "resume":
            clock.resume()
        case "cancel":
            # Raises into whichever runners are sleeping. The drain tasks let it
            # propagate and the run ends with the registry still resettable.
            clock.cancel()
            if record.task is not None:
                record.task.cancel()
        case "speed":
            assert request.value is not None  # guaranteed by the validator
            clock.set_speed(request.value)

    return ControlAck(
        run_id=run_id,
        action=request.action,
        speed=clock.speed,
        paused=clock.is_paused,
        cancelled=clock.is_cancelled,
    )


@router.post("/runs/{run_id}/query")
async def query_run(run_id: str, filters: Filters, registry: Registry) -> QueryResult:
    """Re-aggregate the run's derived frame under a cross-filter.

    Always 200, with a discriminated result, exactly as `POST /api/plans`
    answers a rejected document. A run with no analytical table is a normal
    outcome and not a server fault: a requirement document belongs to whoever
    wrote it, and most documents do not describe a revenue aggregate. The run
    still built what it was asked for.

    The distinction that matters is kept either way. "No table" is a different
    answer from an empty bundle, which is what a filter matching nothing
    returns, and the dashboard must not confuse the two. It used to be a 409,
    which said the same thing but made every browser watching the demo log a
    console error on a path that is working correctly.
    """
    record = _require(registry, run_id)
    frame = record.kernel.derived
    if frame is None:
        return NoAnalyticalTable(
            message="This run has not produced an analytical table."
        )
    return AggregateReady(bundle=aggregate(frame, filters))
