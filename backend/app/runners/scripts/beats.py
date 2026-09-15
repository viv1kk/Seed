"""The vocabulary a script is written in, and the driver that performs one.

A script is an ordered list of beats. Four kinds:

``Work``  calls the kernel and files the result under a step id.
``Say``   emits a line, built from results already filed.
``Emit``  produces an artifact, streaming it if it has source to stream.
``Pause`` waits, because a run with no silence in it reads as a progress bar.

The load-bearing detail is that ``Say.text`` is a callable rather than a string.
It runs at the moment the line is emitted, with the results of every earlier
``Work`` beat available to it, which is what makes "12,847 rows" a thing the
pipeline measured a second ago instead of a thing somebody typed. A ``Say`` that
returns a fixed string containing a digit is a defect, and it is a defect that
this arrangement makes awkward to write by accident.

The driver owns pacing. Individual scripts describe what happens, never when, so
the timing model in docs/04-AGENT-RUNTIME.md lives in one place and an agent's
character comes from its own ``base_step_ms`` rather than from sleeps sprinkled
through its script.
"""

from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field
from typing import Final, TypeVar

from app.core.clock import Clock
from app.core.rng import Rng, jitter
from app.core.types import Artifact, LogLevel, Plan, SeedEvent, Task
from app.pipeline.kernel import WorkKernel
from app.runners.base import Emitter

# Spacing between lines inside a step, in ms before jitter.
LINE_GAP_MS: Final[int] = 260

# Roughly one beat in ten gets a longer pause in front of it. This does more for
# the run reading as real than any animation would.
THINKING_CHANCE: Final[float] = 0.1
THINKING_MS: Final[tuple[int, int]] = (1_500, 3_000)

# Characters per streamed chunk. Small enough to read as typing, large enough
# that a 4kB module does not put four hundred events on the stream.
CHUNK_CHARS: Final[int] = 120
CHUNK_GAP_MS: Final[int] = 90

T = TypeVar("T")


class BeatCtx:
    """What a beat can see: the task, the kernel, and every earlier result.

    Results are filed under the step id of the ``Work`` beat that produced them
    and read back with an expected type, so a ``Say`` that quotes the wrong
    step's numbers fails immediately rather than printing something plausible.
    """

    def __init__(self, task: Task, plan: Plan, kernel: WorkKernel, rng: Rng) -> None:
        self.task = task
        self.plan = plan
        self.kernel = kernel
        self.rng = rng
        self._results: dict[str, object] = {}

    def file(self, step_id: str, value: object) -> None:
        self._results[step_id] = value

    def get(self, step_id: str, kind: type[T]) -> T:
        """The result of an earlier Work beat, checked against its type."""
        try:
            value = self._results[step_id]
        except KeyError as exc:
            raise LookupError(f"No result filed for step {step_id!r}") from exc
        if not isinstance(value, kind):
            raise TypeError(
                f"Step {step_id!r} produced {type(value).__name__}, not {kind.__name__}"
            )
        return value

    def has(self, step_id: str) -> bool:
        return step_id in self._results


@dataclass(frozen=True)
class Say:
    """A log line. ``text`` runs at emit time so it can quote real results."""

    text: Callable[[BeatCtx], str]
    level: LogLevel = "info"
    # Machine voice rather than the agent's own. Carries kernel numbers.
    runtime: bool = False
    # Emit this line only if the condition holds. The level is fixed when the
    # script is written, but whether a run went well is not known until it has,
    # so a beat list says "this line at success, that line at warn" and lets the
    # measured result choose between them.
    when: Callable[[BeatCtx], bool] | None = None


@dataclass(frozen=True)
class Work:
    """A kernel call. The result is filed under ``step_id`` for later beats.

    Synchronous on purpose. The kernel is Polars over a frame already in memory
    and it returns in single-digit milliseconds; wrapping it in a coroutine
    would suggest a wait that does not happen. The pacing around it is the
    driver's business and goes through the clock.
    """

    step_id: str
    call: Callable[[WorkKernel, BeatCtx], object]


@dataclass(frozen=True)
class Emit:
    """An artifact.

    With ``stream`` set, the body registered by ``build`` is sent as chunks
    before the artifact is created, so the panel fills in as the agent writes.
    The text comes from the registered body rather than from a second callable,
    because the streamed text and the delivered artifact must be the same bytes.
    """

    build: Callable[[BeatCtx], Artifact]
    stream: bool = False


@dataclass(frozen=True)
class Pause:
    """A deliberate silence, in ms before jitter."""

    ms: int = 900


Beat = Say | Work | Emit | Pause

# A script is a list of beats, or a factory that builds one from the task. The
# factory form exists for tasks whose shape depends on the requirement document,
# such as the verification pass that walks whatever criteria were written.
Script = Sequence[Beat] | Callable[[Task, Plan], Sequence[Beat]]


@dataclass
class Performance:
    """Driver state for one task. Tracks which of the task's steps are done."""

    ctx: BeatCtx
    emitter: Emitter
    base_step_ms: int
    completed_steps: set[str] = field(default_factory=set)


async def perform(
    beats: Sequence[Beat],
    performance: Performance,
    clock: Clock,
) -> AsyncIterator[SeedEvent]:
    """Run a beat list, emitting events and pacing the gaps between them."""
    ctx = performance.ctx
    emit = performance.emitter
    rng = ctx.rng

    for beat in beats:
        if rng.random() < THINKING_CHANCE:
            await clock.sleep(rng.randint(*THINKING_MS))

        match beat:
            case Say(text=text, level=level, runtime=runtime, when=when):
                if when is not None and not when(ctx):
                    continue
                line = text(ctx)
                yield emit.kernel_line(line, level) if runtime else emit.say(line, level)
                await clock.sleep(jitter(rng, LINE_GAP_MS))

            case Work(step_id=step_id, call=call):
                # The wait goes first. Reporting a result and only then pausing
                # would put every silence in the wrong place: the agent would
                # look like it was resting after the work rather than doing it.
                await clock.sleep(jitter(rng, performance.base_step_ms))
                ctx.file(step_id, call(ctx.kernel, ctx))
                progress = _progress(ctx.task, step_id, performance.completed_steps)
                if progress is not None:
                    yield emit.progress(step_id, progress)

            case Emit(build=build, stream=stream):
                async for event in _emit_artifact(build, stream, performance, clock):
                    yield event

            case Pause(ms=ms):
                await clock.sleep(jitter(rng, ms))


async def _emit_artifact(
    build: Callable[[BeatCtx], Artifact],
    stream: bool,
    performance: Performance,
    clock: Clock,
) -> AsyncIterator[SeedEvent]:
    ctx = performance.ctx
    emit = performance.emitter
    artifact = build(ctx)

    body = ctx.kernel.body(artifact.id) if stream else None
    text = body.text if body is not None else None
    if text:
        yield emit.streaming(artifact.id, artifact.path, artifact.lang)
        for start in range(0, len(text), CHUNK_CHARS):
            yield emit.chunk(artifact.id, text[start : start + CHUNK_CHARS])
            await clock.sleep(jitter(ctx.rng, CHUNK_GAP_MS))

    ctx.kernel.emit_artifact(artifact)
    yield emit.created(artifact)
    yield emit.kernel_line(f"artifact: {artifact.path} {artifact.bytes:,} bytes")
    await clock.sleep(jitter(ctx.rng, LINE_GAP_MS))


def _progress(task: Task, step_id: str, completed: set[str]) -> float | None:
    """How far through its own steps the task is, once ``step_id`` is done.

    Returns None for a step id the task does not declare, which happens whenever
    a script does more kernel work than the document listed. Progress belongs to
    the document's steps; the extra work still runs, it just does not move a bar
    that has no notch for it.
    """
    ids = [step.id for step in task.steps]
    if step_id not in ids:
        return None
    completed.add(step_id)
    return len(completed) / len(ids)
