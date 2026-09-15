# 03. Event Contract

Frozen. Defined once in Python, generated into TypeScript. This is what a real agent backend will speak later.

Implement in `backend/app/core/types.py`. Adding a variant is allowed. Changing or removing one requires updating this document in the same commit.

## Domain models

```python
from typing import Annotated, Literal, Union
from pydantic import BaseModel, Field

AgentId = Literal["architect", "etl", "analytics", "dashboard"]
TaskStatus = Literal["pending", "ready", "running", "retrying", "completed", "failed", "skipped"]
LogLevel = Literal["debug", "info", "warn", "error", "success"]

class TaskStep(BaseModel):
    id: str
    text: str

class Constraint(BaseModel):
    lang: str
    code: str

class Task(BaseModel):
    id: str                      # "2.1"
    phase_id: str                # "2"
    title: str
    agent_id: AgentId
    depends_on: list[str]
    steps: list[TaskStep]
    constraints: list[Constraint]
    acceptance: list[str]

class Phase(BaseModel):
    id: str
    index: int
    title: str
    task_ids: list[str]

class ParseWarning(BaseModel):
    code: Literal["unassigned-agent", "implicit-dependency", "empty-task"]
    task_id: str | None = None
    message: str

class Plan(BaseModel):
    id: str
    title: str
    source_markdown: str
    phases: list[Phase]
    tasks: dict[str, Task]
    order: list[str]             # topologically sorted task ids
    warnings: list[ParseWarning]

class ParseError(BaseModel):
    code: Literal[
        "unknown-dependency", "self-dependency", "dependency-cycle",
        "task-outside-phase", "no-tasks",
    ]
    task_id: str | None = None
    message: str

class ParseSucceeded(BaseModel):
    status: Literal["ok"] = "ok"
    plan: Plan

class ParseFailed(BaseModel):
    status: Literal["error"] = "error"
    errors: list[ParseError]
    warnings: list[ParseWarning]

ParseResult = Annotated[
    Union[ParseSucceeded, ParseFailed],
    Field(discriminator="status"),
]

class ExampleSummary(BaseModel):
    id: str
    title: str

ArtifactKind = Literal["code", "dataset", "table", "dashboard", "doc"]

class Artifact(BaseModel):
    id: str
    kind: ArtifactKind
    path: str                    # "pipeline/clean.py"
    produced_by: AgentId
    task_id: str
    bytes: int
    lang: str | None = None      # code
    rows: int | None = None      # dataset
    columns: list[str] | None = None
    preview: list[list[str]] | None = None

class TaskMetrics(BaseModel):
    rows_in: int | None = None
    rows_out: int | None = None
    rows_dropped: int | None = None
    columns_added: list[str] | None = None
    null_rates: dict[str, float] | None = None
    duration_ms: int

class ArtifactBody(BaseModel):
    id: str
    kind: ArtifactKind
    path: str
    lang: str | None = None
    text: str | None = None      # raw source, for a copy action
    html: str | None = None      # code: Pygments HTML, highlighted server side
    lines: int | None = None
    rows: int | None = None      # dataset
    columns: list[str] | None = None
    preview: list[list[str]] | None = None
```

Artifact bodies are fetched separately from `GET /api/artifacts/{id}`, not carried on the event. A 400-line source file on an event would bloat the stream and stall the log.

## Analytics models

Added in phase 3. These never appear on the event stream: `Filters` is the body of `POST /api/runs/{id}/query` and `AggBundle` is its response, which is the whole of what the dashboard draws. Both are roots in `scripts/export_schema.py`, because nothing in the event union references them and without an explicit root they would not reach the generated TypeScript.

```python
class Filters(BaseModel):
    date_from: str | None = None     # ISO date, inclusive
    date_to: str | None = None       # ISO date, inclusive
    category: str | None = None
    region: str | None = None

class Kpis(BaseModel):
    net_revenue: float
    order_count: int
    average_order_value: float
    margin_pct: float
    return_rate: float

class WeekPoint(BaseModel):
    week: str                        # the Monday of the week, as an ISO date
    net_revenue: float
    order_count: int

class CategoryRow(BaseModel):
    category: str
    net_revenue: float
    margin_pct: float

class RegionRow(BaseModel):
    region: str
    net_revenue: float
    share: float

class ProductRow(BaseModel):
    sku: str
    product_name: str
    net_revenue: float
    units: int
    margin_pct: float

class AggBundle(BaseModel):
    kpis: Kpis
    revenue_over_time: list[WeekPoint]
    revenue_by_category: list[CategoryRow]
    revenue_by_region: list[RegionRow]
    top_products: list[ProductRow]
    rows: int                        # rows the filters admitted
    computed_ms: int
    filters: Filters                 # echoed, so a response identifies its request

class AggregateReady(BaseModel):
    status: Literal["ok"] = "ok"
    bundle: AggBundle

class NoAnalyticalTable(BaseModel):
    status: Literal["no-analytical-table"] = "no-analytical-table"
    message: str

QueryResult = Annotated[
    Union[AggregateReady, NoAnalyticalTable],
    Field(discriminator="status"),
]
```

One bundle per query rather than an endpoint per surface, so every figure on screen comes from the same filtered frame at the same moment and the cuts cannot disagree with the headline.

`POST /api/runs/{id}/query` answers `QueryResult`, always with HTTP 200, for the
same reason `POST /api/plans` does: a run with no analytical table is a normal
outcome rather than a server fault. Most requirement documents somebody writes
describe no revenue aggregate at all, and the run still built what it was asked
for. A failure status would make the browser log a console error on a path that
is working correctly, and the PRD asks for a clean console through a full run.

"No table" stays distinct from an empty bundle, which is what a filter matching
nothing returns. The dashboard draws nothing in the first case and zeroes in the
second, and it must not confuse them.

`QueryResult` is a third tagged union, so its tag is marked required in the
exported schema exactly as `SeedEvent`'s and `ParseResult`'s are. See the note
under **Parse results**.

## Events

```python
class _Base(BaseModel):
    run_id: str
    seq: int
    at: int                      # run clock, simulated ms. Stamped by the bus.

class RunStarted(_Base):
    type: Literal["run.started"] = "run.started"
    requirement_title: str
    seed: int
    speed: int

class PlanBuilt(_Base):
    type: Literal["plan.built"] = "plan.built"
    plan: Plan

class AgentSpawned(_Base):
    type: Literal["agent.spawned"] = "agent.spawned"
    agent_id: AgentId
    role: str
    assigned_task_ids: list[str]

class TaskReady(_Base):
    type: Literal["task.ready"] = "task.ready"
    task_id: str

class TaskStarted(_Base):
    type: Literal["task.started"] = "task.started"
    task_id: str
    agent_id: AgentId

class TaskProgress(_Base):
    type: Literal["task.progress"] = "task.progress"
    task_id: str
    step_id: str
    pct: float

class LogEmitted(_Base):
    type: Literal["log.emitted"] = "log.emitted"
    agent_id: AgentId | None = None
    task_id: str | None = None
    level: LogLevel
    message: str
    source: Literal["agent", "runtime"]

class ArtifactStreaming(_Base):
    type: Literal["artifact.streaming"] = "artifact.streaming"
    artifact_id: str
    path: str
    lang: str | None = None
    produced_by: AgentId
    task_id: str

class ArtifactChunk(_Base):
    type: Literal["artifact.chunk"] = "artifact.chunk"
    artifact_id: str
    text: str

class ArtifactCreated(_Base):
    type: Literal["artifact.created"] = "artifact.created"
    artifact: Artifact

class TaskFailed(_Base):
    type: Literal["task.failed"] = "task.failed"
    task_id: str
    agent_id: AgentId
    reason: str
    recoverable: bool

class TaskRetried(_Base):
    type: Literal["task.retried"] = "task.retried"
    task_id: str
    agent_id: AgentId
    attempt: int
    strategy: str

class TaskCompleted(_Base):
    type: Literal["task.completed"] = "task.completed"
    task_id: str
    agent_id: AgentId
    metrics: TaskMetrics

class AgentIdle(_Base):
    type: Literal["agent.idle"] = "agent.idle"
    agent_id: AgentId

class RunCompleted(_Base):
    type: Literal["run.completed"] = "run.completed"
    duration_ms: int
    artifact_ids: list[str]

class RunFailed(_Base):
    type: Literal["run.failed"] = "run.failed"
    error: str

SeedEvent = Annotated[
    Union[
        RunStarted, PlanBuilt, AgentSpawned, TaskReady, TaskStarted, TaskProgress,
        LogEmitted, ArtifactStreaming, ArtifactChunk, ArtifactCreated,
        TaskFailed, TaskRetried, TaskCompleted,
        AgentIdle, RunCompleted, RunFailed,
    ],
    Field(discriminator="type"),
]
```

## Rules

1. `seq` is assigned by the event bus, never by a runner. Monotonic per run.
2. `at` is assigned by the event bus too, alongside `seq`, and for the same
   reason. It is **simulated** elapsed milliseconds, unaffected by the speed
   multiplier, and it never decreases as `seq` increases.

   `at` describes the *stream*, not the hand that emitted. It is the run clock:
   the furthest any runner has reached at the moment the event entered the
   stream. A runner cannot supply this, because it sees only its own clock hand
   while two agents work at once and their events interleave in arrival order.
   Stamped at the emit site, the log walks backwards every time the stream
   crosses from one agent to the other. Sorting it afterwards hides that while
   telling you the wrong thing, because the order shown is then no longer the
   order the run did the work in.

   Two consequences worth stating, because both are load-bearing:

   - A task's timestamps depend on what ran beside it. The same task in the same
     plan reports later `at` values when it is sharing the run with a task that
     is further along, and that is correct: it is a clock reading, not a
     stopwatch on the task. Per-task elapsed time is `TaskMetrics.duration_ms`,
     which is measured on that task's own hand and is not affected.
   - The bus samples a hand when that hand publishes, never by polling all the
     hands. A hand mid-sleep sits where real elapsed time has carried it, so
     polling would make `at` a function of wall-clock timing, break the
     speed-independence above, and reorder the log between runs at one seed.
3. Every `task.started` has exactly one matching `task.completed` or `task.failed` with `recoverable=False`.
4. `task.failed` with `recoverable=True` is followed by `task.retried` and then a terminal event for the same task.
5. `artifact.created` precedes the `task.completed` of the producing task.
6. Streaming an artifact is optional. When a runner does stream one, the order is
   `artifact.streaming`, then one or more `artifact.chunk` for that
   `artifact_id`, then `artifact.created`. A runner may still emit
   `artifact.created` alone. Chunks carry no metadata beyond the id, so the
   opener always precedes them, which replay from `seq=0` guarantees.
7. `run.completed` is last. Nothing follows it.
8. Numbers inside `metrics` and inside log messages originate from a `WorkKernel` return value. Never a literal.

## Parse results

`POST /api/plans` answers `ParseResult`, always with HTTP 200.

A parse failure is a normal outcome, not a server fault: the requirement
document belongs to the person using this, and a broken `Depends on:` reference
is an ordinary thing to write. The frontend branches on `status` and renders
either the plan or the errors. The run is refused by there being no plan, and so
no plan id to start one with.

`ParseResult` discriminates on `status`, exactly as `SeedEvent` discriminates on
`type`. Both tags are marked required in the exported schema by
`scripts/export_schema.py`, because Pydantic omits a defaulted field from
`required` and an optional tag does not discriminate. Adding a third tagged
union means checking it comes out the same way; `npm run gen:types` fails the
build if it does not.

## SSE framing

`sse-starlette` `EventSourceResponse`. One JSON object per message, `event:` set to the event type so the client can attach typed handlers if useful, `id:` set to `seq`.

```python
yield {"event": ev.type, "id": str(ev.seq), "data": ev.model_dump_json()}
```

The bus retains every event for the run in memory. `GET /api/runs/{id}/stream` replays from `seq=0` before subscribing to live events, so a page refresh mid-run recovers the whole run rather than joining late. This is worth the small cost: someone will refresh during the demo.

Use `snake_case` on the wire. The generated TypeScript will match. Do not add a camelCase conversion layer, it is one more place for the contract to drift.

## Generating the TypeScript

```python
# backend/scripts/export_schema.py
from pydantic import TypeAdapter
from app.core.types import SeedEvent, Plan, Artifact, AggBundle
print(json.dumps({
    "$defs": ...,
    "oneOf": [TypeAdapter(SeedEvent).json_schema(), ...]
}, indent=2))
```

Then `json-schema-to-typescript` into `frontend/src/types/events.ts`. Committed, never hand-edited, regenerated by `make demo`.

## Test requirement

Record one full run's event list to a JSON fixture. Two tests use it:

- **Python.** Replay the fixture through a pure `apply_event` reducer and assert terminal state: task statuses, artifact count, and exactly one retry having occurred.
- **TypeScript.** Load the same fixture, apply it to the Zustand store, assert the same terminal state.

One fixture, two languages, same assertions. That is the regression net for the whole pipeline and it catches contract drift immediately.
