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
```

Artifact bodies are fetched separately from `GET /api/artifacts/{id}`, not carried on the event. A 400-line source file on an event would bloat the stream and stall the log.

## Events

```python
class _Base(BaseModel):
    run_id: str
    seq: int
    at: int                      # simulated ms since run start

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
        LogEmitted, ArtifactCreated, TaskFailed, TaskRetried, TaskCompleted,
        AgentIdle, RunCompleted, RunFailed,
    ],
    Field(discriminator="type"),
]
```

## Rules

1. `seq` is assigned by the event bus, never by a runner. Monotonic per run.
2. `at` is **simulated** elapsed milliseconds, unaffected by the speed multiplier. A run at 5x reports the same `at` values as the same run at 1x, which keeps logs reproducible across speeds.
3. Every `task.started` has exactly one matching `task.completed` or `task.failed` with `recoverable=False`.
4. `task.failed` with `recoverable=True` is followed by `task.retried` and then a terminal event for the same task.
5. `artifact.created` precedes the `task.completed` of the producing task.
6. `run.completed` is last. Nothing follows it.
7. Numbers inside `metrics` and inside log messages originate from a `WorkKernel` return value. Never a literal.

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
