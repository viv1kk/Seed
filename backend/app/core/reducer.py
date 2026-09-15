"""A pure reducer over the event stream, and the Python half of the parity net.

This mirrors ``frontend/src/state/applyEvent.ts`` exactly. The same fixtures run
through both, and ``summarise`` on either side must produce the same dict, so
contract drift between the two languages fails a test rather than surprising
someone during the demo.

It is pure in the strict sense: ``apply_event`` returns a new ``RunState`` and
never mutates its argument, which is also how the Zustand store updates.

Nothing in the serving path uses this yet. The orchestrator owns run state on the
backend; this exists so the frontend reducer has something to be checked against.
It imports from ``core.types`` and nothing else.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Literal, assert_never

from app.core.types import (
    AgentId,
    AgentIdle,
    AgentSpawned,
    Artifact,
    ArtifactChunk,
    ArtifactCreated,
    ArtifactStreaming,
    LogEmitted,
    LogLevel,
    Plan,
    PlanBuilt,
    RunCompleted,
    RunFailed,
    RunStarted,
    SeedEvent,
    TaskCompleted,
    TaskFailed,
    TaskMetrics,
    TaskProgress,
    TaskReady,
    TaskRetried,
    TaskStarted,
    TaskStatus,
)


@dataclass(frozen=True)
class LogLine:
    seq: int
    at: int
    level: LogLevel
    message: str
    source: Literal["agent", "runtime"]
    agent_id: AgentId | None
    task_id: str | None


@dataclass(frozen=True)
class AgentView:
    agent_id: AgentId
    role: str
    assigned_task_ids: tuple[str, ...]
    idle: bool


@dataclass(frozen=True)
class StreamingArtifact:
    """A code artifact arriving in chunks.

    ``text`` accumulates as chunks land and is kept after ``complete`` flips, so
    a viewer can show what streamed without refetching the finished body.
    """

    artifact_id: str
    path: str
    lang: str | None
    produced_by: AgentId
    task_id: str
    text: str
    complete: bool


@dataclass(frozen=True)
class RunState:
    run_id: str | None
    seed: int | None
    speed: int
    requirement_title: str | None
    started: bool
    completed: bool
    error: str | None
    duration_ms: int | None
    plan: Plan | None
    task_status: Mapping[str, TaskStatus]
    task_agent: Mapping[str, AgentId]
    task_progress: Mapping[str, float]
    task_metrics: Mapping[str, TaskMetrics]
    task_attempts: Mapping[str, int]
    agents: Mapping[AgentId, AgentView]
    artifacts: tuple[Artifact, ...]
    streaming: Mapping[str, StreamingArtifact]
    logs: tuple[LogLine, ...]
    retry_count: int
    last_seq: int


def initial_state() -> RunState:
    return RunState(
        run_id=None,
        seed=None,
        speed=1,
        requirement_title=None,
        started=False,
        completed=False,
        error=None,
        duration_ms=None,
        plan=None,
        task_status={},
        task_agent={},
        task_progress={},
        task_metrics={},
        task_attempts={},
        agents={},
        artifacts=(),
        streaming={},
        logs=(),
        retry_count=0,
        last_seq=-1,
    )


def apply_events(state: RunState, events: Iterable[SeedEvent]) -> RunState:
    for event in events:
        state = apply_event(state, event)
    return state


def apply_event(state: RunState, event: SeedEvent) -> RunState:
    """Fold one event into the state. Never mutates the state passed in."""
    base = replace(state, last_seq=event.seq, run_id=event.run_id)

    match event:
        case RunStarted():
            return replace(
                base,
                started=True,
                seed=event.seed,
                speed=event.speed,
                requirement_title=event.requirement_title,
            )

        case PlanBuilt():
            # Every task in the plan enters the board as pending, so the whole
            # graph can be drawn before anything moves.
            pending: dict[str, TaskStatus] = dict.fromkeys(event.plan.tasks, "pending")
            return replace(
                base,
                plan=event.plan,
                task_status=pending,
                task_agent={
                    task_id: task.agent_id for task_id, task in event.plan.tasks.items()
                },
            )

        case AgentSpawned():
            return replace(
                base,
                agents={
                    **base.agents,
                    event.agent_id: AgentView(
                        agent_id=event.agent_id,
                        role=event.role,
                        assigned_task_ids=tuple(event.assigned_task_ids),
                        idle=False,
                    ),
                },
            )

        case TaskReady():
            return replace(base, task_status=_with_status(base, event.task_id, "ready"))

        case TaskStarted():
            return replace(
                base,
                task_status=_with_status(base, event.task_id, "running"),
                task_agent={**base.task_agent, event.task_id: event.agent_id},
                agents=_with_agent_idle(base, event.agent_id, idle=False),
            )

        case TaskProgress():
            return replace(
                base,
                task_progress={**base.task_progress, event.task_id: event.pct},
            )

        case LogEmitted():
            return replace(
                base,
                logs=(
                    *base.logs,
                    LogLine(
                        seq=event.seq,
                        at=event.at,
                        level=event.level,
                        message=event.message,
                        source=event.source,
                        agent_id=event.agent_id,
                        task_id=event.task_id,
                    ),
                ),
            )

        case ArtifactStreaming():
            return replace(
                base,
                streaming={
                    **base.streaming,
                    event.artifact_id: StreamingArtifact(
                        artifact_id=event.artifact_id,
                        path=event.path,
                        lang=event.lang,
                        produced_by=event.produced_by,
                        task_id=event.task_id,
                        text="",
                        complete=False,
                    ),
                },
            )

        case ArtifactChunk():
            open_stream = base.streaming.get(event.artifact_id)
            if open_stream is None:
                # Every stream is opened by an artifact.streaming before any
                # chunk, and replay always starts at seq=0, so this is
                # unreachable in a well formed run. Drop it rather than invent
                # metadata we were not given.
                return base
            return replace(
                base,
                streaming={
                    **base.streaming,
                    event.artifact_id: replace(
                        open_stream, text=open_stream.text + event.text
                    ),
                },
            )

        case ArtifactCreated():
            streamed = base.streaming.get(event.artifact.id)
            streaming = base.streaming
            if streamed is not None:
                streaming = {
                    **base.streaming,
                    event.artifact.id: replace(streamed, complete=True),
                }
            return replace(
                base, artifacts=(*base.artifacts, event.artifact), streaming=streaming
            )

        case TaskFailed():
            # A recoverable failure reads as retrying, because a task.retried is
            # coming (contract rule 4) and the node must not look dead.
            status: TaskStatus = "retrying" if event.recoverable else "failed"
            return replace(
                base,
                task_status=_with_status(base, event.task_id, status),
                task_agent={**base.task_agent, event.task_id: event.agent_id},
            )

        case TaskRetried():
            return replace(
                base,
                task_status=_with_status(base, event.task_id, "running"),
                task_attempts={**base.task_attempts, event.task_id: event.attempt},
                retry_count=base.retry_count + 1,
            )

        case TaskCompleted():
            return replace(
                base,
                task_status=_with_status(base, event.task_id, "completed"),
                task_agent={**base.task_agent, event.task_id: event.agent_id},
                task_metrics={**base.task_metrics, event.task_id: event.metrics},
                task_progress={**base.task_progress, event.task_id: 1.0},
            )

        case AgentIdle():
            return replace(base, agents=_with_agent_idle(base, event.agent_id, idle=True))

        case RunCompleted():
            return replace(base, completed=True, duration_ms=event.duration_ms)

        case RunFailed():
            return replace(base, error=event.error)

        case _ as unreachable:
            assert_never(unreachable)


def _with_status(state: RunState, task_id: str, status: TaskStatus) -> Mapping[str, TaskStatus]:
    return {**state.task_status, task_id: status}


def _with_agent_idle(
    state: RunState,
    agent_id: AgentId,
    *,
    idle: bool,
) -> Mapping[AgentId, AgentView]:
    existing = state.agents.get(agent_id)
    if existing is None:
        # An agent can be referenced before its agent.spawned arrives, on a
        # replay that starts mid-stream. Record what we know.
        return {
            **state.agents,
            agent_id: AgentView(agent_id=agent_id, role="", assigned_task_ids=(), idle=idle),
        }
    return {**state.agents, agent_id: replace(existing, idle=idle)}


def summarise(state: RunState) -> dict[str, object]:
    """The comparable shape asserted by the expected block in each fixture.

    ``frontend/src/state/summarise.ts`` returns the identical dict, with the
    identical snake_case keys. Keep the two in step.
    """
    return {
        "last_seq": state.last_seq,
        "run_id": state.run_id,
        "seed": state.seed,
        "speed": state.speed,
        "requirement_title": state.requirement_title,
        "started": state.started,
        "completed": state.completed,
        "error": state.error,
        "duration_ms": state.duration_ms,
        "task_status": dict(sorted(state.task_status.items())),
        "task_agent": dict(sorted(state.task_agent.items())),
        "task_attempts": dict(sorted(state.task_attempts.items())),
        "retry_count": state.retry_count,
        "artifact_count": len(state.artifacts),
        "artifact_ids": [artifact.id for artifact in state.artifacts],
        "log_count": len(state.logs),
        "streaming_ids": sorted(state.streaming),
        "streamed_chars": sum(len(s.text) for s in state.streaming.values()),
        "streams_complete": sorted(i for i, s in state.streaming.items() if s.complete),
        "agents_spawned": sorted(state.agents),
        "agents_idle": sorted(a for a, view in state.agents.items() if view.idle),
        "plan_task_count": len(state.plan.tasks) if state.plan else 0,
    }
