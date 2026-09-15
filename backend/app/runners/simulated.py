"""The simulated runner, on generic beats derived from the task itself.

Phase 2 has no per-agent scripts. Everything runs on the fallback sequence built
from the task's own steps, constraints and acceptance criteria, which is also
what an edited or pasted requirement file will always use. Per-agent scripts
arrive in phase 3 under ``runners/scripts/`` and this stays as the graceful
degradation beneath them.

Timing follows docs/04-AGENT-RUNTIME.md. Pacing differs per agent because
uniform pacing is the loudest tell that nothing is really happening, and roughly
one step in ten carries a longer pause, as if the agent is thinking. That pause
does more for the run reading as real than any animation would.

Every wait is ``ctx.clock.sleep``. Never ``asyncio.sleep``: pause, speed and
cancel all depend on going through the clock.
"""

from collections.abc import AsyncIterator
from typing import Final

from app.core.agents import display_name
from app.core.rng import jitter
from app.core.types import AgentId, Artifact, SeedEvent, Task
from app.runners.base import AgentContext, AgentRunner, Emitter

# Milliseconds per step, before jitter. From the roster table in
# docs/04-AGENT-RUNTIME.md: the ETL Engineer is slowest and loudest, the
# Architect fastest and most decisive.
BASE_STEP_MS: Final[dict[AgentId, int]] = {
    "architect": 900,
    "etl": 2_200,
    "analytics": 1_400,
    "dashboard": 1_100,
}

# Spacing between lines inside a step, in ms before jitter.
LINE_GAP_MS: Final[int] = 260

# Roughly one step in ten gets a longer pause before its line.
THINKING_CHANCE: Final[float] = 0.1
THINKING_MS: Final[tuple[int, int]] = (1_500, 3_000)

# Characters per streamed chunk. Small enough to read as typing, large enough
# that a 2kB file does not flood the stream with hundreds of events.
CHUNK_CHARS: Final[int] = 120
CHUNK_GAP_MS: Final[int] = 90

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
        emit = Emitter(ctx, task, self.agent_id)
        clock = ctx.clock
        base_ms = BASE_STEP_MS[self.agent_id]

        yield emit.say(self._opening(task))
        await clock.sleep(jitter(ctx.rng, LINE_GAP_MS))

        for index, step in enumerate(task.steps, start=1):
            if ctx.rng.random() < THINKING_CHANCE:
                await clock.sleep(ctx.rng.randint(*THINKING_MS))

            yield emit.say(step.text.rstrip("."))
            await clock.sleep(jitter(ctx.rng, base_ms))

            yield emit.progress(step.id, index / len(task.steps))
            await clock.sleep(jitter(ctx.rng, LINE_GAP_MS))

        async for event in self._produce_artifact(task, ctx, emit):
            yield event

        for criterion in task.acceptance:
            yield emit.say(f"Checked against the criterion: {criterion}", level="success")
            await clock.sleep(jitter(ctx.rng, LINE_GAP_MS))

    def _opening(self, task: Task) -> str:
        if not task.steps:
            return f"Task {task.id}. {task.title}."
        return f"Task {task.id}. {task.title}, in {len(task.steps)} steps."

    async def _produce_artifact(
        self,
        task: Task,
        ctx: AgentContext,
        emit: Emitter,
    ) -> AsyncIterator[SeedEvent]:
        """One artifact per task, built from what the task actually says.

        A task carrying a fenced code block has real source to produce, so that
        source is streamed in chunks and then created. A task without one
        produces a document written from its own steps and criteria. Either way
        the bytes are the real bytes, counted, not asserted.
        """
        # Keyed by plan and task, never by run id. Two runs of the same
        # document must produce byte-identical streams, and the plan id is a
        # hash of the markdown, so this is both stable and unique across
        # different documents.
        artifact_id = f"art_{ctx.plan.id}_{task.id.replace('.', '_')}"

        if task.constraints:
            constraint = task.constraints[0]
            lang = constraint.lang or "text"
            path = f"design/{task.id}-constraint.{_EXTENSIONS.get(lang, 'txt')}"
            text = constraint.code

            yield emit.streaming(artifact_id, path, lang)
            yield emit.say(f"Writing {path}.")

            for start in range(0, len(text), CHUNK_CHARS):
                yield emit.chunk(artifact_id, text[start : start + CHUNK_CHARS])
                await ctx.clock.sleep(jitter(ctx.rng, CHUNK_GAP_MS))

            artifact = Artifact(
                id=artifact_id,
                kind="code",
                path=path,
                produced_by=self.agent_id,
                task_id=task.id,
                bytes=len(text.encode("utf-8")),
                lang=lang,
            )
        else:
            path = f"design/{task.id}-notes.md"
            text = self._notes(task)
            artifact = Artifact(
                id=artifact_id,
                kind="doc",
                path=path,
                produced_by=self.agent_id,
                task_id=task.id,
                bytes=len(text.encode("utf-8")),
            )
            yield emit.say(f"Writing {path}.")
            await ctx.clock.sleep(jitter(ctx.rng, LINE_GAP_MS))

        ctx.kernel.emit_artifact(artifact)
        yield emit.created(artifact)
        yield emit.kernel_line(f"artifact: {artifact.path} {artifact.bytes:,} bytes")

    def _notes(self, task: Task) -> str:
        lines = [f"# {task.title}", "", f"Owner: {display_name(self.agent_id)}", ""]
        if task.steps:
            lines += ["## Steps", "", *(f"- {step.text}" for step in task.steps), ""]
        if task.acceptance:
            lines += ["## Acceptance", "", *(f"- {item}" for item in task.acceptance), ""]
        return "\n".join(lines)
