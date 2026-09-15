"""The scheduling loop.

A loop over a ready set, not a timeline. Each iteration starts whatever is ready
and there are slots for, then blocks on a single inbox that every running runner
feeds. That inbox is the fan-in: each runner's async generator is drained by its
own ``asyncio.Task`` which puts events on the shared queue. Merging the
generators directly would mean one slow runner holding up another.

``MAX_PARALLEL`` is 2. Two agents working at once reads as parallel. Four reads
as noise.

Cancellation: ``clock.cancel()`` raises into whichever runners are sleeping, the
drain tasks let it propagate, and ``execute`` returns with the registry in a
clean, resettable state.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from app.core.agents import ROSTER
from app.core.clock import Clock
from app.core.events import EventBus
from app.core.rng import Rng, derive_rng
from app.core.types import (
    AgentId,
    AgentIdle,
    AgentSpawned,
    LogEmitted,
    Plan,
    PlanBuilt,
    RunCompleted,
    RunFailed,
    RunStarted,
    SeedEvent,
    Task,
    TaskCompleted,
    TaskFailed,
    TaskMetrics,
    TaskReady,
    TaskStarted,
)
from app.orchestrator.scheduler import Scheduler
from app.pipeline.kernel import WorkKernel
from app.runners.base import AgentContext, AgentRunner
from app.runners.simulated import SimulatedRunner

MAX_PARALLEL: Final[int] = 2


@dataclass
class _Emitted:
    """One event from a runner, with the clock hand that produced it.

    The hand travels with the event because the bus stamps ``at`` from it. A
    hand read at any other moment is a question about real elapsed time rather
    than simulated, and the run stops being reproducible. See ``core/events.py``.
    """

    event: SeedEvent
    hand: Clock


@dataclass
class _RunnerDone:
    """A runner's generator finished, successfully or not.

    Sent after the last event so the loop knows the slot is free. Without it a
    runner that ended without a terminal event would hang the run.
    """

    task_id: str
    error: BaseException | None
    ended_ms: int


_Message = _Emitted | _RunnerDone


class Orchestrator:
    def __init__(
        self,
        run_id: str,
        plan: Plan,
        bus: EventBus,
        clock: Clock,
        rng: Rng,
        kernel: WorkKernel,
        runner_for: Callable[[AgentId], AgentRunner],
        seed: int,
    ) -> None:
        self._run_id = run_id
        self._plan = plan
        self._bus = bus
        self._clock = clock
        self._rng = rng
        self._kernel = kernel
        self._runner_for = runner_for
        self._seed = seed

        self._scheduler = Scheduler(plan)
        self._inbox: asyncio.Queue[_Message] = asyncio.Queue()
        self._drains: dict[str, asyncio.Task[None]] = {}
        self._announced_ready: set[str] = set()

        # Where a new clock hand starts. Advanced only at a deterministic
        # moment, a task finishing, and only to that task's own final position.
        #
        # It is tempting to fork from the run clock instead, since that is what
        # the bus stamps on events, and a hand forked from it would never start
        # behind the stream. It is also wrong: the run clock at any moment
        # between events depends on how far the *other* runner has got through
        # its current sleep, which is a question about real elapsed time. Fork
        # from that and the two runners' sleeps land in a different order on a
        # cold process than on a warm one, and two runs at one seed stop
        # matching. Measured, not assumed: it reordered the log about one run in
        # four.
        self._timeline_ms = 0

    # ------------------------------------------------------------ public

    async def execute(self) -> None:
        try:
            await self._open()
            await self._loop()
        except asyncio.CancelledError:
            # Cancellation is a control action, not a failure. Let it through
            # after tearing the runners down.
            await self._abandon_runners()
            raise
        finally:
            await self._bus.close()

    # ------------------------------------------------------------ the loop

    async def _loop(self) -> None:
        while self._scheduler.has_incomplete_tasks():
            await self._announce_ready()
            self._fill_slots()

            if not self._drains:
                # Nothing running and nothing startable. The graph cannot
                # progress, which a valid plan should make impossible.
                await self._fail_run(
                    "The run stopped because no task could start and none were running."
                )
                return

            message = await self._inbox.get()
            if isinstance(message, _RunnerDone):
                if await self._runner_finished(message):
                    return
                continue

            await self._bus.publish(message.event, message.hand)

        await self._complete()

    async def _announce_ready(self) -> None:
        for task_id in self._scheduler.ready_set():
            if task_id in self._announced_ready:
                continue
            self._announced_ready.add(task_id)
            self._scheduler.mark_ready(task_id)
            await self._publish(
                TaskReady(run_id=self._run_id, seq=0, at=0, task_id=task_id)
            )

    def _fill_slots(self) -> None:
        free = MAX_PARALLEL - len(self._drains)
        for task_id in self._scheduler.ready_set()[:free]:
            self._start(task_id)

    def _start(self, task_id: str) -> None:
        task = self._plan.tasks[task_id]
        self._scheduler.mark_running(task_id)
        self._drains[task_id] = asyncio.create_task(
            self._drain(task), name=f"runner-{task_id}"
        )

    async def _drain(self, task: Task) -> None:
        """Pump one runner's generator into the shared inbox.

        Every runner gets its own drain task, and its own hand on the clock so
        that two agents working at once do not make simulated time run fast.
        """
        runner = self._runner_for(task.agent_id)
        ctx = AgentContext(
            run_id=self._run_id,
            plan=self._plan,
            artifacts=self._kernel.artifacts,
            kernel=self._kernel,
            # A task that starts late does not begin its timestamps at zero.
            # See _timeline_ms for why the position comes from there and not
            # from the run clock.
            clock=self._clock.fork(self._timeline_ms),
            # Its own generator, derived from the run seed and this task's id.
            # Sharing one across concurrent runners makes the draws depend on
            # scheduling, and the run stops being reproducible.
            rng=derive_rng(self._seed, task.id),
        )
        started_ms = ctx.clock.settled_ms

        error: BaseException | None = None
        cancelled = False
        try:
            await self._emit(
                ctx,
                TaskStarted(
                    run_id=self._run_id,
                    seq=0,
                    at=0,
                    task_id=task.id,
                    agent_id=task.agent_id,
                ),
            )
            async for event in runner.run(task, ctx):
                await self._emit(ctx, event)
            await self._emit(
                ctx,
                TaskCompleted(
                    run_id=self._run_id,
                    seq=0,
                    at=0,
                    task_id=task.id,
                    agent_id=task.agent_id,
                    metrics=self._metrics(task, ctx.clock.settled_ms - started_ms),
                ),
            )
        except asyncio.CancelledError:
            # Never swallowed. The run is being torn down, and nobody is left
            # reading the inbox, so do not report back either.
            cancelled = True
            raise
        except Exception as exc:  # reported on the stream, never hidden
            error = exc
        finally:
            if not cancelled:
                await self._inbox.put(
                    _RunnerDone(
                        task_id=task.id, error=error, ended_ms=ctx.clock.settled_ms
                    )
                )

    async def _emit(self, ctx: AgentContext, event: SeedEvent) -> None:
        """Hand one runner event to the loop, with the hand that produced it."""
        await self._inbox.put(_Emitted(event=event, hand=ctx.clock))

    def _metrics(self, task: Task, duration_ms: int) -> TaskMetrics:
        """Row counts from the kernel, duration from the clock.

        The runner is the only thing that knows which kernel calls a task made,
        so it files the counts as it goes and the orchestrator picks them up
        here. The duration is the orchestrator's: it owns the clock hand this
        task ran on. Contract rule 8 holds either way, since nothing on this
        event was written by hand.
        """
        recorded = self._kernel.metrics_for(task.id)
        if recorded is None:
            return TaskMetrics(duration_ms=duration_ms)
        return recorded.model_copy(update={"duration_ms": duration_ms})

    async def _runner_finished(self, message: _RunnerDone) -> bool:
        """Retire a finished runner. Returns True if the run is over."""
        self._drains.pop(message.task_id, None)

        if message.error is not None:
            skipped = self._scheduler.mark_failed(message.task_id)
            await self._publish_runner_failure(message, skipped)
            await self._fail_run(
                f"The run stopped at task {message.task_id}. {message.error}"
            )
            return True

        # The one place the fork position moves, and it only moves forward.
        self._timeline_ms = max(self._timeline_ms, message.ended_ms)
        self._scheduler.mark_completed(message.task_id)
        await self._maybe_idle(self._plan.tasks[message.task_id].agent_id)
        return False

    async def _publish_runner_failure(
        self, message: _RunnerDone, skipped: list[str]
    ) -> None:
        task = self._plan.tasks[message.task_id]
        await self._publish(
            TaskFailed(
                run_id=self._run_id,
                seq=0,
                at=0,
                task_id=task.id,
                agent_id=task.agent_id,
                reason=str(message.error),
                recoverable=False,
            )
        )
        for task_id in skipped:
            await self._publish(
                LogEmitted(
                    run_id=self._run_id,
                    seq=0,
                at=0,
                    task_id=task_id,
                    level="warn",
                    message=f"Task {task_id} was skipped because {task.id} failed.",
                    source="runtime",
                )
            )

    async def _maybe_idle(self, agent_id: AgentId) -> None:
        """Report an agent idle once it has nothing left to do."""
        outstanding = [
            task_id
            for task_id, task in self._plan.tasks.items()
            if task.agent_id == agent_id
            and self._scheduler.status[task_id] in {"pending", "ready", "running"}
        ]
        if not outstanding:
            await self._publish(
                AgentIdle(run_id=self._run_id, seq=0, at=0, agent_id=agent_id)
            )

    # ------------------------------------------------------------ lifecycle

    async def _open(self) -> None:
        await self._publish(
            RunStarted(
                run_id=self._run_id,
                seq=0,
                at=0,
                requirement_title=self._plan.title,
                seed=self._seed,
                speed=self._clock.speed,
            )
        )
        await self._publish(
            PlanBuilt(run_id=self._run_id, seq=0, at=0, plan=self._plan)
        )

        # Roster order, not plan order, so the agent rail is stable between runs.
        for profile in ROSTER:
            assigned = [
                task_id
                for task_id in self._plan.order
                if self._plan.tasks[task_id].agent_id == profile.id
            ]
            if assigned:
                await self._publish(
                    AgentSpawned(
                        run_id=self._run_id,
                        seq=0,
                at=0,
                        agent_id=profile.id,
                        role=profile.display_name,
                        assigned_task_ids=assigned,
                    )
                )

    async def _complete(self) -> None:
        await self._publish(
            RunCompleted(
                run_id=self._run_id,
                seq=0,
                at=0,
                duration_ms=self._bus.at,
                artifact_ids=list(self._kernel.artifacts),
            )
        )

    async def _fail_run(self, error: str) -> None:
        await self._abandon_runners()
        await self._publish(
            RunFailed(run_id=self._run_id, seq=0, at=0, error=error)
        )

    async def _abandon_runners(self) -> None:
        for drain in self._drains.values():
            drain.cancel()
        if self._drains:
            await asyncio.gather(*self._drains.values(), return_exceptions=True)
        self._drains.clear()

    # ------------------------------------------------------------ helpers

    async def _publish(self, event: SeedEvent) -> None:
        """Publish a run-level event: one the run emitted, not a runner.

        No hand, so it carries the run clock as it already stands. Every event
        built in this module leaves with ``at=0``, the same placeholder as
        ``seq=0``; neither is the orchestrator's to assign. See
        ``core/events.py``.
        """
        await self._bus.publish(event)


def default_runner_for(agent_id: AgentId) -> AgentRunner:
    return SimulatedRunner(agent_id)


__all__ = ["MAX_PARALLEL", "Orchestrator", "default_runner_for"]
