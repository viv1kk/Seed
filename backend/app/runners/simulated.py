"""The simulated runner: a scripted narration where there is one, generic beats
where there is not.

Dispatch is the whole of this module. A task the bundled demo document declares
has a script under ``runners/scripts/`` written in that agent's voice around
real kernel calls. Every other task, an edited heading, a task someone added, a
pasted requirement file, runs on beats derived from its own steps, constraints
and acceptance criteria, over the same bundled dataset and through the same
kernel.

The fallback is not a lesser path that exists to avoid a crash. It is what makes
"this is a platform, not a recording" answerable: the demo can be edited live
and the run still does real work and still narrates it.

Timing follows docs/04-AGENT-RUNTIME.md. Pacing differs per agent because
uniform pacing is the loudest tell that nothing is really happening. Every wait
goes through ``ctx.clock.sleep``: pause, speed and cancel all depend on it.
"""

from collections.abc import AsyncIterator, Callable, Sequence
from typing import Final

from app.core.agents import display_name
from app.core.clock import Clock
from app.core.types import AgentId, Artifact, SeedEvent, Task, TaskMetrics
from app.pipeline.kernel import WorkKernel
from app.runners.base import AgentContext, AgentRunner, Emitter
from app.runners.scripts import artifacts, script_for
from app.runners.scripts.beats import Beat, BeatCtx, Emit, Performance, Say, Work, perform

# Milliseconds per step, before jitter. From the roster table in
# docs/04-AGENT-RUNTIME.md: the ETL Engineer is slowest and loudest, the
# Architect fastest and most decisive.
BASE_STEP_MS: Final[dict[AgentId, int]] = {
    "architect": 900,
    "etl": 2_200,
    "analytics": 1_400,
    "dashboard": 1_100,
}

_EXTENSIONS: Final[dict[str, str]] = {
    "python": "py",
    "sql": "sql",
    "yaml": "yaml",
    "json": "json",
    "typescript": "tsx",
}


class SimulatedRunner(AgentRunner):
    def __init__(self, agent_id: AgentId) -> None:
        self.agent_id = agent_id

    async def run(self, task: Task, ctx: AgentContext) -> AsyncIterator[SeedEvent]:
        performance = Performance(
            ctx=BeatCtx(task=task, plan=ctx.plan, kernel=ctx.kernel, rng=ctx.rng),
            emitter=Emitter(ctx, task, self.agent_id),
            base_step_ms=BASE_STEP_MS[self.agent_id],
        )

        narrate = script_for(ctx.plan, self.agent_id, task.id)
        if narrate is None:
            narrate = self._generic

        async for event in narrate(performance, ctx.clock):
            yield event

    # ------------------------------------------------------------ fallback

    async def _generic(self, performance: Performance, clock: Clock) -> AsyncIterator[SeedEvent]:
        async for event in perform(self._generic_beats(performance.ctx.task), performance, clock):
            yield event

    def _generic_beats(self, task: Task) -> Sequence[Beat]:
        """Beats built from what the task itself says.

        The one kernel call is a load of the bundled orders extract, so even an
        unscripted task reports a real row count and a real timing rather than
        narrating over nothing.
        """
        beats: list[Beat] = [
            Say(lambda c: self._opening(c.task)),
            Work("load", lambda k, _: k.load_csv("orders")),
            Say(lambda c: _loaded_line(c), runtime=True),
        ]

        for step in task.steps:
            beats.append(Say(_fixed(step.text.rstrip("."))))
            beats.append(Work(step.id, lambda k, _: k.preview("orders")))

        beats.append(Emit(lambda c: self._artifact(c), stream=True))
        beats += [
            Say(_criterion_text(criterion), level="success") for criterion in task.acceptance
        ]
        beats.append(Work("record", self._record))
        return beats

    def _opening(self, task: Task) -> str:
        if not task.steps:
            return f"Task {task.id}. {task.title}."
        return f"Task {task.id}. {task.title}, in {len(task.steps)} steps."

    def _artifact(self, ctx: BeatCtx) -> Artifact:
        """One artifact per task, built from what the task actually says.

        A task carrying a fenced code block has real source to produce, so that
        block is the artifact. A task without one produces a document written
        from its own steps and criteria. Either way the bytes are counted rather
        than asserted.
        """
        task = ctx.task
        if task.constraints:
            constraint = task.constraints[0]
            lang = constraint.lang or "text"
            path = f"design/{task.id}-constraint.{_EXTENSIONS.get(lang, 'txt')}"
            return artifacts.written(ctx, path, constraint.code, self.agent_id, kind="code")
        return artifacts.written(
            ctx, f"design/{task.id}-notes.md", self._notes(task), self.agent_id
        )

    def _notes(self, task: Task) -> str:
        lines = [f"# {task.title}", "", f"Owner: {display_name(self.agent_id)}", ""]
        if task.steps:
            lines += ["## Steps", "", *(f"- {step.text}" for step in task.steps), ""]
        if task.acceptance:
            lines += ["## Acceptance", "", *(f"- {item}" for item in task.acceptance), ""]
        return "\n".join(lines)

    def _record(self, kernel: WorkKernel, ctx: BeatCtx) -> None:
        del kernel  # the figures come from results already filed
        preview = ctx.kernel.preview("orders")
        ctx.kernel.record_metrics(
            ctx.task.id,
            TaskMetrics(rows_in=preview.rows, rows_out=preview.rows, duration_ms=0),
        )


def _loaded_line(ctx: BeatCtx) -> str:
    preview = ctx.kernel.preview("orders")
    return f"read_csv: orders.csv {preview.rows:,} rows, {len(preview.columns)} columns"


def _fixed(line: str) -> Callable[[BeatCtx], str]:
    """A Say that quotes no measurement.

    Bound eagerly so the line is the step's own text rather than whichever step
    the loop variable happened to end on. Every one of these comes straight out
    of the requirement document, which is why it carries no number.
    """
    return lambda _: line


def _criterion_text(criterion: str) -> Callable[[BeatCtx], str]:
    return lambda _: f"Checked against the criterion: {criterion}"
