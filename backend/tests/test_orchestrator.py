"""The scheduling loop: gating, parallelism, cancellation, reproducibility."""

import asyncio
import textwrap
from collections import Counter
from collections.abc import AsyncIterator

import pytest

from app.core.registry import RunRegistry
from app.core.types import (
    AgentId,
    ParseSucceeded,
    Phase,
    Plan,
    SeedEvent,
    Task,
)
from app.orchestrator.orchestrator import MAX_PARALLEL, Orchestrator, default_runner_for
from app.parser import build_plan
from app.runners.base import AgentContext, AgentRunner

# Fast enough to keep the suite quick, slow enough that two concurrent runners
# are not racing inside the event loop's scheduling noise.
TEST_SPEED = 60


def plan_of(markdown: str) -> Plan:
    result = build_plan(textwrap.dedent(markdown))
    assert isinstance(result, ParseSucceeded), result
    return result.plan


LINEAR = plan_of(
    """
    # Linear

    ## One

    ### A

    Agent: Architect

    - decide the schema

    ### B

    Agent: ETL Engineer
    Depends on: 1.1

    - load the extract

    ### C

    Agent: Analytics Engineer
    Depends on: 1.2

    - join and aggregate
    """
)

# 1.2 and 1.3 both depend only on 1.1, so they may run at the same time.
PARALLEL = plan_of(
    """
    # Parallel

    ## One

    ### A

    Agent: Architect

    - decide the schema

    ### Left

    Agent: ETL Engineer
    Depends on: 1.1

    - load the extract

    ### Right

    Agent: Dashboard Engineer
    Depends on: 1.1

    - draft the chart

    ### Join

    Agent: Analytics Engineer
    Depends on: 1.2, 1.3

    - aggregate everything
    """
)

WITH_CODE = plan_of(
    """
    # Streaming

    ## One

    ### Write the loader

    Agent: ETL Engineer

    - read the csv

    ```python
    import polars as pl


    def load(path: str) -> pl.DataFrame:
        return pl.read_csv(path, infer_schema_length=0)
    ```
    """
)


async def run_plan(
    plan: Plan,
    *,
    seed: int = 1337,
    speed: int = TEST_SPEED,
    give_up_after: float = 60.0,
) -> list[SeedEvent]:
    registry = RunRegistry()
    record = registry.create_run(plan.id, seed=seed, speed=speed)
    orchestrator = Orchestrator(
        run_id=record.run_id,
        plan=plan,
        bus=record.bus,
        clock=record.clock,
        rng=record.rng,
        kernel=record.kernel,
        runner_for=default_runner_for,
        seed=record.seed,
    )
    await asyncio.wait_for(orchestrator.execute(), timeout=give_up_after)
    return list(record.bus.history)


def types_of(events: list[SeedEvent]) -> list[str]:
    return [event.type for event in events]


# ---------------------------------------------------------------- a whole run


@pytest.mark.asyncio
async def test_a_run_completes_end_to_end() -> None:
    events = await run_plan(LINEAR)

    counts = Counter(types_of(events))
    assert counts["run.started"] == 1
    assert counts["plan.built"] == 1
    assert counts["task.started"] == 3
    assert counts["task.completed"] == 3
    assert counts["run.completed"] == 1


@pytest.mark.asyncio
async def test_run_completed_is_last_and_nothing_follows_it() -> None:
    """Event contract rule 7."""
    events = await run_plan(LINEAR)
    assert events[-1].type == "run.completed"
    assert types_of(events).count("run.completed") == 1


@pytest.mark.asyncio
async def test_seq_is_monotonic_from_zero() -> None:
    """Event contract rule 1. The bus assigns it, never a runner."""
    events = await run_plan(LINEAR)
    assert [event.seq for event in events] == list(range(len(events)))


@pytest.mark.asyncio
async def test_every_started_task_reaches_a_terminal_event() -> None:
    """Event contract rule 3."""
    events = await run_plan(PARALLEL)
    started = {e.task_id for e in events if e.type == "task.started"}
    completed = {e.task_id for e in events if e.type == "task.completed"}
    assert started == completed == set(PARALLEL.tasks)


@pytest.mark.asyncio
async def test_statuses_move_through_ready_then_started_then_completed() -> None:
    events = await run_plan(LINEAR)
    for task_id in LINEAR.order:
        sequence = [
            e.type
            for e in events
            if getattr(e, "task_id", None) == task_id
            and e.type in {"task.ready", "task.started", "task.completed"}
        ]
        assert sequence == ["task.ready", "task.started", "task.completed"], task_id


@pytest.mark.asyncio
async def test_an_artifact_is_created_before_its_task_completes() -> None:
    """Event contract rule 5."""
    events = await run_plan(LINEAR)
    for index, event in enumerate(events):
        if event.type == "artifact.created":
            later = [
                e
                for e in events[index:]
                if e.type == "task.completed" and e.task_id == event.artifact.task_id
            ]
            assert later, f"{event.artifact.id} was created after its task completed"


# ---------------------------------------------------------------- gating


@pytest.mark.asyncio
async def test_a_task_never_starts_before_its_dependencies_complete() -> None:
    events = await run_plan(PARALLEL)
    completed_at: dict[str, int] = {}
    for index, event in enumerate(events):
        if event.type == "task.completed":
            completed_at[event.task_id] = index
        if event.type == "task.started":
            for dependency in PARALLEL.tasks[event.task_id].depends_on:
                assert dependency in completed_at, (
                    f"{event.task_id} started before {dependency} completed"
                )


@pytest.mark.asyncio
async def test_two_tasks_run_in_parallel_where_the_graph_allows_it() -> None:
    events = await run_plan(PARALLEL)

    running: set[str] = set()
    peak = 0
    seen_together: set[tuple[str, ...]] = set()
    for event in events:
        if event.type == "task.started":
            running.add(event.task_id)
        elif event.type == "task.completed":
            running.discard(event.task_id)
        peak = max(peak, len(running))
        if len(running) > 1:
            seen_together.add(tuple(sorted(running)))

    assert peak == 2, "the two independent tasks never overlapped"
    assert ("1.2", "1.3") in seen_together


@pytest.mark.asyncio
async def test_never_more_than_max_parallel_at_once() -> None:
    events = await run_plan(PARALLEL)
    running = 0
    for event in events:
        if event.type == "task.started":
            running += 1
        elif event.type == "task.completed":
            running -= 1
        assert running <= MAX_PARALLEL


@pytest.mark.asyncio
async def test_a_linear_plan_never_overlaps() -> None:
    events = await run_plan(LINEAR)
    running = 0
    peak = 0
    for event in events:
        if event.type == "task.started":
            running += 1
        elif event.type == "task.completed":
            running -= 1
        peak = max(peak, running)
    assert peak == 1


# ---------------------------------------------------------------- streaming


@pytest.mark.asyncio
async def test_a_code_artifact_streams_before_it_is_created() -> None:
    """The order the contract promises: streaming, chunks, then created."""
    events = await run_plan(WITH_CODE)
    relevant = [
        e.type
        for e in events
        if e.type in {"artifact.streaming", "artifact.chunk", "artifact.created"}
    ]
    assert relevant[0] == "artifact.streaming"
    assert relevant[-1] == "artifact.created"
    assert relevant.count("artifact.chunk") >= 1
    assert set(relevant[1:-1]) == {"artifact.chunk"}


@pytest.mark.asyncio
async def test_the_streamed_chunks_reassemble_into_the_real_source() -> None:
    """The stream carries the document's own fenced code, not a placeholder."""
    events = await run_plan(WITH_CODE)
    streamed = "".join(e.text for e in events if e.type == "artifact.chunk")

    assert streamed == WITH_CODE.tasks["1.1"].constraints[0].code
    created = next(e for e in events if e.type == "artifact.created")
    assert created.artifact.bytes == len(streamed.encode("utf-8"))
    assert created.artifact.lang == "python"


@pytest.mark.asyncio
async def test_every_chunk_belongs_to_an_opened_stream() -> None:
    events = await run_plan(WITH_CODE)
    opened: set[str] = set()
    for event in events:
        if event.type == "artifact.streaming":
            opened.add(event.artifact_id)
        elif event.type == "artifact.chunk":
            assert event.artifact_id in opened


# ---------------------------------------------------------------- reproducibility


def _stream(events: list[SeedEvent]) -> list[str]:
    return [e.model_dump_json(exclude={"run_id"}) for e in events]


@pytest.mark.asyncio
async def test_two_runs_at_one_seed_are_byte_identical() -> None:
    first = await run_plan(LINEAR, seed=1337)
    second = await run_plan(LINEAR, seed=1337)
    assert _stream(first) == _stream(second)


@pytest.mark.asyncio
async def test_a_run_with_concurrency_is_byte_identical_too() -> None:
    """Including how two agents' lines interleave with each other.

    This is only true because each task draws from its own generator. With one
    shared generator the pacing shifts with whatever the event loop did, and
    then so does everything downstream of it.
    """
    first = await run_plan(PARALLEL, seed=1337)
    second = await run_plan(PARALLEL, seed=1337)
    assert _stream(first) == _stream(second)


@pytest.mark.asyncio
async def test_a_different_seed_produces_a_different_run() -> None:
    first = await run_plan(LINEAR, seed=1337)
    second = await run_plan(LINEAR, seed=9999)
    assert [e.at for e in first] != [e.at for e in second]


@pytest.mark.asyncio
async def test_simulated_timestamps_do_not_change_with_speed() -> None:
    """Event contract rule 2. A run at 5x reports the same `at` as at 1x."""
    slow = await run_plan(LINEAR, speed=20)
    fast = await run_plan(LINEAR, speed=120)
    assert [e.at for e in slow] == [e.at for e in fast]


@pytest.mark.asyncio
async def test_concurrent_work_does_not_make_simulated_time_run_fast() -> None:
    """Two agents working at once is not two seconds per second.

    The run's reported duration must not exceed the sum of what the tasks on the
    longest path actually slept, which is what a single accumulating counter
    would produce.
    """
    events = await run_plan(PARALLEL)
    completed = next(e for e in events if e.type == "run.completed")
    per_task = {
        e.task_id: e.metrics.duration_ms for e in events if e.type == "task.completed"
    }
    assert completed.duration_ms < sum(per_task.values())


def _by_task(events: list[SeedEvent]) -> dict[str, list[str]]:
    """Each task's own events, in order, with everything run-wide excluded.

    ``at`` is excluded along with ``run_id`` and ``seq``, and for the same
    reason: it is assigned by the bus and describes the stream, not the task.
    Two concurrent runners emit at whatever moment their sleeps end, and when
    two emissions land close enough together the order they reach the bus in is
    a real-time race. That race was always there; before the run clock existed
    it was invisible here, because a task's timestamps came from its own hand.
    What must not move is the narration: the lines, their order within the task,
    and the numbers in them. That is what this compares. The run clock has its
    own tests, below and in test_events.py.
    """
    grouped: dict[str, list[str]] = {}
    for event in events:
        task_id = getattr(event, "task_id", None)
        if task_id is not None:
            grouped.setdefault(task_id, []).append(
                event.model_dump_json(exclude={"run_id", "seq", "at"})
            )
    return grouped


@pytest.mark.asyncio
async def test_each_task_narrates_identically_across_runs() -> None:
    """Holds under concurrency, because each task has its own generator.

    A single shared generator would break this: two agents running at once draw
    from it in whatever order the event loop schedules them, so the pacing and
    every timestamp would shift with real timing. See derive_rng.
    """
    assert _by_task(await run_plan(PARALLEL, seed=7)) == _by_task(
        await run_plan(PARALLEL, seed=7)
    )


@pytest.mark.asyncio
async def test_a_parallel_run_reports_the_same_duration_every_time() -> None:
    """The run clock is a function of the seed, not of how the loop scheduled."""
    first = await run_plan(PARALLEL, seed=7)
    second = await run_plan(PARALLEL, seed=7)

    def completed(events: list[SeedEvent]) -> tuple[int, list[str]]:
        done = next(e for e in events if e.type == "run.completed")
        return done.duration_ms, sorted(done.artifact_ids)

    assert completed(first) == completed(second)


@pytest.mark.asyncio
async def test_every_agent_says_the_same_lines_across_runs() -> None:
    """Including the numbers in them, which is what someone will check."""

    def per_agent(events: list[SeedEvent]) -> dict[str | None, list[str]]:
        grouped: dict[str | None, list[str]] = {}
        for event in events:
            if event.type == "log.emitted":
                grouped.setdefault(event.agent_id, []).append(event.message)
        return grouped

    assert per_agent(await run_plan(PARALLEL, seed=7)) == per_agent(
        await run_plan(PARALLEL, seed=7)
    )


@pytest.mark.asyncio
async def test_a_tasks_narration_does_not_depend_on_what_ran_beside_it() -> None:
    """Task 1.1 is written identically in both plans, so it must narrate alike.

    In LINEAR it runs alone; in PARALLEL two other tasks start the moment it
    finishes. This is the property a shared generator destroys, and it is the
    reason the demo can be rehearsed at all: a task's beats are a function of
    the seed and its own id, not of what the scheduler was doing at the time.
    """

    def lines(events: list[SeedEvent]) -> list[str]:
        return [
            e.message for e in events if e.type == "log.emitted" and e.task_id == "1.1"
        ]

    assert lines(await run_plan(LINEAR, seed=7)) == lines(await run_plan(PARALLEL, seed=7))


@pytest.mark.asyncio
async def test_simulated_time_never_goes_backwards_on_a_parallel_run() -> None:
    """Contract rule 2, and the whole reason the bus stamps `at`.

    Two agents work at once and their hands sit at different positions. Read `at`
    off the emitting hand and the log walks backwards every time the stream
    crosses between them. Read it off the run clock and it rises with `seq`,
    which is what a log has to do to be readable.
    """
    events = await run_plan(PARALLEL, seed=7)
    ats = [event.at for event in events]

    assert ats == sorted(ats)
    assert len({event.agent_id for event in events if event.type == "task.started"}) > 1


@pytest.mark.asyncio
async def test_a_task_that_starts_late_does_not_start_its_clock_at_zero() -> None:
    events = await run_plan(LINEAR)
    started = {e.task_id: e.at for e in events if e.type == "task.started"}

    assert started["1.1"] == 0
    assert started["1.2"] > 0
    assert started["1.3"] > started["1.2"]


# ---------------------------------------------------------------- failure


@pytest.mark.asyncio
async def test_a_runner_that_raises_fails_the_run_and_skips_what_waited() -> None:

    class Exploding(AgentRunner):
        def __init__(self, agent_id: AgentId) -> None:
            self.agent_id = agent_id

        async def run(
            self,
            task: Task,  # noqa: ARG002 - the signature is the interface
            ctx: AgentContext,  # noqa: ARG002
        ) -> AsyncIterator[SeedEvent]:
            raise RuntimeError("the extract was not there")
            # Unreachable on purpose: the yield is what makes this an async
            # generator, which the AgentRunner interface requires.
            yield  # type: ignore[unreachable]  # pragma: no cover

    registry = RunRegistry()
    record = registry.create_run(LINEAR.id, seed=1, speed=TEST_SPEED)
    orchestrator = Orchestrator(
        run_id=record.run_id,
        plan=LINEAR,
        bus=record.bus,
        clock=record.clock,
        rng=record.rng,
        kernel=record.kernel,
        runner_for=Exploding,
        seed=1,
    )
    await asyncio.wait_for(orchestrator.execute(), timeout=30)

    events = list(record.bus.history)
    assert events[-1].type == "run.failed"
    failed = next(e for e in events if e.type == "task.failed")
    assert failed.task_id == "1.1"
    assert failed.recoverable is False
    assert "the extract was not there" in failed.reason
    # 1.2 and 1.3 were waiting on it and are reported, not left silently pending.
    skipped = [e.message for e in events if e.type == "log.emitted" and "skipped" in e.message]
    assert len(skipped) == 2


@pytest.mark.asyncio
async def test_a_graph_that_cannot_progress_ends_the_run_rather_than_hanging() -> None:
    """Deadlock detection.

    The parser rejects cycles, so this builds the Plan directly. The loop must
    still refuse to wait forever if one ever reaches it.
    """
    stuck = Plan(
        id="plan_stuck",
        title="Stuck",
        source_markdown="",
        phases=[Phase(id="1", index=1, title="One", task_ids=["1.1", "1.2"])],
        tasks={
            "1.1": Task(
                id="1.1", phase_id="1", title="A", agent_id="architect",
                depends_on=["1.2"], steps=[], constraints=[], acceptance=[],
            ),
            "1.2": Task(
                id="1.2", phase_id="1", title="B", agent_id="architect",
                depends_on=["1.1"], steps=[], constraints=[], acceptance=[],
            ),
        },
        order=["1.1", "1.2"],
        warnings=[],
    )

    events = await run_plan(stuck, give_up_after=15)
    assert events[-1].type == "run.failed"
    assert "no task could start" in events[-1].error


# ---------------------------------------------------------------- control


@pytest.mark.asyncio
async def test_cancelling_a_run_propagates_and_leaves_no_task_behind() -> None:
    registry = RunRegistry()
    record = registry.create_run(LINEAR.id, seed=1337, speed=1)
    orchestrator = Orchestrator(
        run_id=record.run_id,
        plan=LINEAR,
        bus=record.bus,
        clock=record.clock,
        rng=record.rng,
        kernel=record.kernel,
        runner_for=default_runner_for,
        seed=1337,
    )

    task = asyncio.create_task(orchestrator.execute())
    await asyncio.sleep(0.3)
    record.clock.cancel()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    # Nothing left running, and the events so far are still replayable.
    leftover = [
        t for t in asyncio.all_tasks() if t.get_name().startswith("runner-") and not t.done()
    ]
    assert leftover == []
    assert len(record.bus.history) > 0


@pytest.mark.asyncio
async def test_pause_holds_the_run_and_resume_releases_it() -> None:
    registry = RunRegistry()
    record = registry.create_run(LINEAR.id, seed=1337, speed=2)
    orchestrator = Orchestrator(
        run_id=record.run_id,
        plan=LINEAR,
        bus=record.bus,
        clock=record.clock,
        rng=record.rng,
        kernel=record.kernel,
        runner_for=default_runner_for,
        seed=1337,
    )
    task = asyncio.create_task(orchestrator.execute())

    async def wait_past(count: int, limit: float = 8.0) -> int:
        """Poll instead of sleeping a guessed interval. Pacing is jittered."""
        deadline = asyncio.get_running_loop().time() + limit
        while asyncio.get_running_loop().time() < deadline:
            if len(record.bus.history) > count:
                return len(record.bus.history)
            await asyncio.sleep(0.02)
        pytest.fail(f"the run published nothing beyond {count} within {limit}s")

    await wait_past(3)
    record.clock.pause()
    await asyncio.sleep(0.3)  # let the slice already in flight finish

    held = len(record.bus.history)
    await asyncio.sleep(0.8)
    assert len(record.bus.history) == held, "the run kept going while paused"

    record.clock.resume()
    await wait_past(held)

    record.clock.cancel()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
