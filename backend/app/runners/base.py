"""The swap seam.

``AgentRunner`` is the whole interface between "how work gets narrated" and
everything else. ``SimulatedRunner`` yields narration around real kernel calls.
A future ``LlmRunner`` yields narration derived from streamed model output
around the same real kernel calls. The orchestrator, the event bus, the API and
the entire frontend are identical in both cases.

When API access arrives:

1. Add ``runners/llm.py``.
2. Add a runner-selection setting.
3. Nothing else.

That claim will be made to the client, so keep it true. Anything a runner needs
goes on ``AgentContext``; nothing about simulation may leak past this module.

Runners are async generators. Pause, cancel and speed all depend on it: every
wait goes through ``ctx.clock.sleep``, and ``asyncio.CancelledError`` raised
there must be allowed to propagate out of the generator untouched.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass

from app.core.clock import Clock
from app.core.rng import Rng
from app.core.types import (
    AgentId,
    Artifact,
    ArtifactChunk,
    ArtifactCreated,
    ArtifactStreaming,
    LogEmitted,
    LogLevel,
    Plan,
    SeedEvent,
    Task,
    TaskFailed,
    TaskProgress,
    TaskRetried,
)
from app.pipeline.kernel import WorkKernel


@dataclass(frozen=True)
class AgentContext:
    run_id: str
    plan: Plan
    artifacts: Mapping[str, Artifact]  # outputs of completed tasks
    kernel: WorkKernel  # real work
    clock: Clock  # this runner's own hand: speed-aware sleep, pause, cancel
    rng: Rng  # seeded


class AgentRunner(ABC):
    agent_id: AgentId

    @abstractmethod
    def run(self, task: Task, ctx: AgentContext) -> AsyncIterator[SeedEvent]: ...


class Emitter:
    """Builds events for one task, so runners do not repeat the bookkeeping.

    ``seq`` is left at 0 on purpose. The event bus assigns it (contract rule 1)
    and a runner that set its own would be wrong the moment two runners are
    emitting at once. ``at`` is read from this runner's clock hand at the moment
    the event is built.
    """

    def __init__(self, ctx: AgentContext, task: Task, agent_id: AgentId) -> None:
        self._ctx = ctx
        self._task = task
        self._agent_id = agent_id

    @property
    def at(self) -> int:
        return self._ctx.clock.elapsed_ms

    @property
    def run_id(self) -> str:
        return self._ctx.run_id

    def say(self, message: str, level: LogLevel = "info") -> LogEmitted:
        """A line in the agent's own voice."""
        return LogEmitted(
            run_id=self._ctx.run_id,
            seq=0,
            at=self.at,
            agent_id=self._agent_id,
            task_id=self._task.id,
            level=level,
            message=message,
            source="agent",
        )

    def kernel_line(self, message: str, level: LogLevel = "debug") -> LogEmitted:
        """A machine-voice line carrying real numbers from the kernel."""
        return LogEmitted(
            run_id=self._ctx.run_id,
            seq=0,
            at=self.at,
            agent_id=self._agent_id,
            task_id=self._task.id,
            level=level,
            message=message,
            source="runtime",
        )

    def progress(self, step_id: str, pct: float) -> TaskProgress:
        return TaskProgress(
            run_id=self._ctx.run_id,
            seq=0,
            at=self.at,
            task_id=self._task.id,
            step_id=step_id,
            pct=pct,
        )

    def streaming(self, artifact_id: str, path: str, lang: str | None) -> ArtifactStreaming:
        return ArtifactStreaming(
            run_id=self._ctx.run_id,
            seq=0,
            at=self.at,
            artifact_id=artifact_id,
            path=path,
            lang=lang,
            produced_by=self._agent_id,
            task_id=self._task.id,
        )

    def chunk(self, artifact_id: str, text: str) -> ArtifactChunk:
        return ArtifactChunk(
            run_id=self._ctx.run_id,
            seq=0,
            at=self.at,
            artifact_id=artifact_id,
            text=text,
        )

    def created(self, artifact: Artifact) -> ArtifactCreated:
        return ArtifactCreated(
            run_id=self._ctx.run_id,
            seq=0,
            at=self.at,
            artifact=artifact,
        )

    def failed(self, reason: str, *, recoverable: bool) -> TaskFailed:
        """A task going wrong in a way the runner saw coming and can describe.

        Distinct from a runner raising, which the orchestrator reports as an
        unrecoverable failure with the exception text. This one is for a failure
        the agent has diagnosed and is about to do something about.
        """
        return TaskFailed(
            run_id=self._ctx.run_id,
            seq=0,
            at=self.at,
            task_id=self._task.id,
            agent_id=self._agent_id,
            reason=reason,
            recoverable=recoverable,
        )

    def retried(self, attempt: int, strategy: str) -> TaskRetried:
        return TaskRetried(
            run_id=self._ctx.run_id,
            seq=0,
            at=self.at,
            task_id=self._task.id,
            agent_id=self._agent_id,
            attempt=attempt,
            strategy=strategy,
        )
