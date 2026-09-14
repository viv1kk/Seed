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


class _Base(BaseModel):
    run_id: str
    seq: int
    at: int  # simulated ms since run start


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
    Union[  # noqa: UP007
        RunStarted,
        PlanBuilt,
        AgentSpawned,
        TaskReady,
        TaskStarted,
        TaskProgress,
        LogEmitted,
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
    "Artifact",
    "ArtifactCreated",
    "ArtifactKind",
    "Constraint",
    "ExampleSummary",
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
]
