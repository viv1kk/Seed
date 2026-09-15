"""The frozen event contract.

Copied verbatim from ``docs/03-EVENT-CONTRACT.md``. This module is the single
definition of everything that crosses the backend/frontend boundary; the
TypeScript in ``frontend/src/types/events.ts`` is generated from it.

Adding a variant is allowed. Changing or removing one requires updating
``docs/03-EVENT-CONTRACT.md`` in the same commit.
"""

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
    id: str  # "2.1"
    phase_id: str  # "2"
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
    order: list[str]  # topologically sorted task ids
    warnings: list[ParseWarning]


class ParseError(BaseModel):
    code: Literal[
        "unknown-dependency",
        "self-dependency",
        "dependency-cycle",
        "task-outside-phase",
        "no-tasks",
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
    Union[ParseSucceeded, ParseFailed],  # noqa: UP007
    Field(discriminator="status"),
]


class ExampleSummary(BaseModel):
    id: str
    title: str


ArtifactKind = Literal["code", "dataset", "table", "dashboard", "doc"]


class Artifact(BaseModel):
    id: str
    kind: ArtifactKind
    path: str  # "pipeline/clean.py"
    produced_by: AgentId
    task_id: str
    bytes: int
    lang: str | None = None  # code
    rows: int | None = None  # dataset
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
    """The contents of one artifact, fetched separately from the event stream.

    Code arrives as Pygments HTML rather than as source, because the
    highlighting is done server side and there is no client-side highlighter in
    this project. ``text`` carries the raw source for anything that wants it,
    such as a copy action, and documents use it directly.
    """

    id: str
    kind: ArtifactKind
    path: str
    lang: str | None = None
    text: str | None = None
    html: str | None = None
    lines: int | None = None
    rows: int | None = None
    columns: list[str] | None = None
    preview: list[list[str]] | None = None


# ---------------------------------------------------------------- analytics


class Filters(BaseModel):
    """The cross-filter, applied to the retained derived frame.

    Sent by the dashboard to ``POST /api/runs/{id}/query`` and echoed back on
    the bundle, so a response can be matched to the request that produced it
    without the frontend tracking what it asked for.
    """

    date_from: str | None = None
    date_to: str | None = None
    category: str | None = None
    region: str | None = None


class Kpis(BaseModel):
    net_revenue: float
    order_count: int
    average_order_value: float
    margin_pct: float
    return_rate: float


class WeekPoint(BaseModel):
    week: str  # the Monday of the week, as an ISO date
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
    """Everything the dashboard draws, computed in one pass over one frame.

    One bundle per query, rather than an endpoint per surface. Every figure on
    screen then comes from the same filtered frame at the same moment, so the
    category totals and the region totals cannot disagree with the headline
    because one of them was computed a request later.
    """

    kpis: Kpis
    revenue_over_time: list[WeekPoint]
    revenue_by_category: list[CategoryRow]
    revenue_by_region: list[RegionRow]
    top_products: list[ProductRow]
    rows: int  # rows the filters admitted, before the revenue statuses narrow it
    computed_ms: int
    filters: Filters


class AggregateReady(BaseModel):
    status: Literal["ok"] = "ok"
    bundle: AggBundle


class NoAnalyticalTable(BaseModel):
    """The run has not produced a frame to aggregate, and may never.

    Two different situations, deliberately one answer. A query that arrives
    before the analytics task has derived the table is early; a run whose
    document never described an aggregate at all will never have one. Neither is
    a fault, and the dashboard does the same thing in both cases: it does not
    draw.
    """

    status: Literal["no-analytical-table"] = "no-analytical-table"
    message: str


QueryResult = Annotated[
    Union[AggregateReady, NoAnalyticalTable],  # noqa: UP007
    Field(discriminator="status"),
]


class _Base(BaseModel):
    run_id: str
    seq: int
    at: int  # the run clock in simulated ms, stamped by the bus. See rule 2.


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
    """A code artifact is about to arrive, in chunks.

    Optional. A runner may emit `artifact.created` on its own, as before. When
    it does stream, this opens the stream, `artifact.chunk` carries the text,
    and `artifact.created` closes it with the finished metadata.

    This exists for the swap path rather than for the animation. A future
    LlmRunner streams tokens because that is how a model emits code, so the
    contract has to carry chunks from the start. Adding them later would either
    break a frozen contract or leave the real runner behaving differently from
    the simulated one, which is the one thing the seam must not do.
    """

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
    Union[  # noqa: UP007
        RunStarted,
        PlanBuilt,
        AgentSpawned,
        TaskReady,
        TaskStarted,
        TaskProgress,
        LogEmitted,
        ArtifactStreaming,
        ArtifactChunk,
        ArtifactCreated,
        TaskFailed,
        TaskRetried,
        TaskCompleted,
        AgentIdle,
        RunCompleted,
        RunFailed,
    ],
    Field(discriminator="type"),
]

__all__ = [
    "AgentId",
    "AgentIdle",
    "AgentSpawned",
    "AggBundle",
    "Artifact",
    "ArtifactBody",
    "ArtifactChunk",
    "ArtifactCreated",
    "ArtifactKind",
    "ArtifactStreaming",
    "CategoryRow",
    "Constraint",
    "ExampleSummary",
    "Filters",
    "Kpis",
    "LogEmitted",
    "LogLevel",
    "ParseError",
    "ParseFailed",
    "ParseResult",
    "ParseSucceeded",
    "ParseWarning",
    "Phase",
    "Plan",
    "PlanBuilt",
    "ProductRow",
    "RegionRow",
    "RunCompleted",
    "RunFailed",
    "RunStarted",
    "SeedEvent",
    "Task",
    "TaskCompleted",
    "TaskFailed",
    "TaskMetrics",
    "TaskProgress",
    "TaskReady",
    "TaskRetried",
    "TaskStarted",
    "TaskStatus",
    "TaskStep",
    "WeekPoint",
]
