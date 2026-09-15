"""The ETL Engineer's scripts, including the failure and recovery beat.

Task 2.1 is the centrepiece of the demo and the one task written as a narration
rather than as a beat list, because its shape is a ``try`` and an ``except`` and
a beat list cannot express that honestly.

What is real here, in order:

* the exception. ``clean`` is called with the strict ISO strategy and Polars
  raises ``InvalidOperationError`` against the real file. Nothing checks first,
  nothing pretends.
* the failing count. Polars reports its own failure against the chunk it gave up
  on, so the count that reaches the log comes from a probe pass over all 12,847
  rows afterwards.
* the samples. Lifted out of the failing rows themselves. Somebody will check
  them against orders.csv, and they will find them.
* the day-first conclusion. The probe counts failing values whose leading number
  is above 12. A day cannot be a month, so those values rule out US ordering as
  a matter of arithmetic rather than assumption.
* the recovery. The second ``clean`` call genuinely succeeds and genuinely
  resolves every row.

The only scripted part is the English. Every number in it came back from the
kernel a moment earlier.

**Ordering note.** ``pipeline/clean.py`` streams *before* the strict parse runs,
not after. Watching the cleaner be written, watching it assert one timestamp
format, and then watching that assertion fail is the whole arc. Emitting the
artifact after the recovery would spend the failure with nothing on screen to
attach it to.
"""

from collections.abc import AsyncIterator, Sequence
from typing import Final

import polars as pl

from app.core.clock import Clock
from app.core.rng import jitter
from app.core.types import AgentId, SeedEvent, TaskMetrics
from app.pipeline.results import CleanResult, CleanStrategy, LoadResult, ProfileResult
from app.runners.scripts import artifacts
from app.runners.scripts.beats import (
    LINE_GAP_MS,
    Beat,
    BeatCtx,
    Emit,
    Performance,
    Say,
    Work,
    perform,
)

AGENT: Final[AgentId] = "etl"

SOURCES = ("orders", "products", "customers")
TIMESTAMP_COLUMN = "order_ts"
ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"

# What the ETL Engineer decides to do with the file, from the quality rules the
# Architect set in task 1.2. The timestamp field is the one that changes between
# the first attempt and the retry; everything else is settled before either.
BASE_STRATEGY = CleanStrategy(
    timestamp="iso-strict",
    dedupe_on="order_id",
    coerce={"qty": "int", "unit_price": "float"},
    fill_nulls={"discount_pct": 0.0},
)

MAX_ATTEMPTS = 3


def ingest_beats() -> Sequence[Beat]:
    """Everything in task 2.1 up to the point where the cleaner is invoked."""
    return [
        Say(
            lambda c: f"Task {c.task.id}. Sources listed: "
            + ", ".join(f"{name}.csv" for name in SOURCES)
        ),
        Work("load-orders", lambda k, _: k.load_csv("orders")),
        Say(
            lambda c: _read_line(c.get("load-orders", LoadResult)),
            runtime=True,
        ),
        Work("load-products", lambda k, _: k.load_csv("products")),
        Work("load-customers", lambda k, _: k.load_csv("customers")),
        Say(
            lambda c: "Reference tables loaded. "
            f"{c.get('load-products', LoadResult).rows} products, "
            f"{c.get('load-customers', LoadResult).rows:,} customers.",
        ),
        Emit(lambda c: artifacts.code(c, "pipeline/load.py", AGENT), stream=True),
        Say(lambda _: "Profiling the order extract before I commit to a schema."),
        Work("profile", lambda k, _: k.profile("orders")),
        Say(lambda c: _profile_line(c.get("profile", ProfileResult)), runtime=True),
        Say(lambda c: _quality_line(c.get("profile", ProfileResult))),
        Say(lambda _: "Writing the cleaning pass now, against the rules from 1.2."),
        # Streamed here, before the strict parse below runs. Watching the
        # cleaner be written and then watching it fail is the arc; emitting it
        # after the recovery would spend the failure with nothing on screen to
        # attach it to.
        Emit(lambda c: artifacts.code(c, "pipeline/clean.py", AGENT), stream=True),
    ]


async def ingest_and_clean(performance: Performance, clock: Clock) -> AsyncIterator[SeedEvent]:
    """Task 2.1. Load, profile, fail on the strict parse, recover, clean."""
    ctx = performance.ctx
    emit = performance.emitter

    async for event in perform(ingest_beats(), performance, clock):
        yield event

    yield emit.say(f"Parsing {TIMESTAMP_COLUMN} as ISO 8601. One format, strict.")
    await clock.sleep(jitter(ctx.rng, performance.base_step_ms))

    attempt = 1
    strategy = BASE_STRATEGY
    while True:
        try:
            result = ctx.kernel.clean("orders", strategy)
        except pl.exceptions.InvalidOperationError as exc:
            if attempt >= MAX_ATTEMPTS:
                raise
            async for event in _diagnose(performance, clock, exc, attempt):
                yield event
            attempt += 1
            strategy = BASE_STRATEGY.model_copy(update={"timestamp": "multi-format-day-first"})
            continue
        break

    yield emit.kernel_line(
        f"clean: {result.rows_in - result.failures:,} of {result.rows_in:,} timestamps resolved"
    )
    await clock.sleep(jitter(ctx.rng, LINE_GAP_MS))
    yield emit.kernel_line(
        f"clean: dropped {result.duplicates_removed} duplicate order_id, "
        f"coerced {result.coerced_counts.get('qty', 0):,} qty values, {result.clean_ms}ms"
    )
    await clock.sleep(jitter(ctx.rng, LINE_GAP_MS))

    dropped_pct = result.rows_dropped / result.rows_in * 100 if result.rows_in else 0.0
    null_rate = result.null_rates.get("discount_pct", 0.0) * 100
    yield emit.say(
        f"Clean pass complete. {result.rows_out:,} rows retained, "
        f"{dropped_pct:.2f}% dropped, discount null rate {null_rate:.2f}%.",
        level="success",
    )
    await clock.sleep(jitter(ctx.rng, LINE_GAP_MS))

    async for event in perform(
        [Emit(lambda c: artifacts.dataset(c, "data/orders_clean", "orders", AGENT))],
        performance,
        clock,
    ):
        yield event

    _record(ctx, result)


async def _diagnose(
    performance: Performance,
    clock: Clock,
    exc: pl.exceptions.InvalidOperationError,
    attempt: int,
) -> AsyncIterator[SeedEvent]:
    """The failure beat. Everything reported here is measured after the raise."""
    ctx = performance.ctx
    emit = performance.emitter
    rng = ctx.rng

    yield emit.kernel_line(f"clean: strict parse raised {type(exc).__name__}", level="error")
    await clock.sleep(jitter(rng, LINE_GAP_MS))

    probe = ctx.kernel.probe_format("orders", TIMESTAMP_COLUMN, ISO_FORMAT)

    yield emit.kernel_line(
        f"probe: {probe.unparseable:,} of {probe.total:,} values unparseable under {probe.spec}"
    )
    await clock.sleep(jitter(rng, LINE_GAP_MS))
    yield emit.say(
        f"That is {probe.failure_rate * 100:.0f}% of the file, too many to drop. "
        "Inspecting the failures."
    )
    # The long pause before the samples. It reads as looking at something.
    await clock.sleep(jitter(rng, performance.base_step_ms))

    yield emit.kernel_line("sample: " + ", ".join(f'"{value}"' for value in probe.samples))
    await clock.sleep(jitter(rng, LINE_GAP_MS))

    yield emit.say(_ordering_line(probe.alternates, probe.day_first_evidence))
    await clock.sleep(jitter(rng, LINE_GAP_MS))

    reason = f"{TIMESTAMP_COLUMN}: {len(probe.alternates) + 1} timestamp formats in one column"
    yield emit.failed(reason, recoverable=True)
    # The node holds on the fault colour for a beat before it flips to retrying.
    # Worth the wait: it is the only moment in the run where something is wrong.
    await clock.sleep(jitter(rng, 1_200))

    yield emit.retried(attempt + 1, "multi-format parse with day-first fallback")
    yield emit.say("Retrying with a coalesced two-format parse. No row gets dropped for this.")
    await clock.sleep(jitter(rng, LINE_GAP_MS))


def _ordering_line(alternates: dict[str, int], day_first_evidence: int) -> str:
    """Narrate what the probe found, and only what it found.

    With no alternate format there is nothing to claim, and with no value above
    12 the day-first reading is a guess rather than a finding. In both cases the
    line says less. An agent asserting an ordering the data does not support
    would be the one genuinely dishonest line in the run.
    """
    if not alternates:
        return "No other format reads these values. This needs a rule I do not have."

    spec, count = next(iter(alternates.items()))
    if day_first_evidence == 0:
        return (
            f"A second format is present: {spec} reads all {count:,} of them. "
            "Day and month order is ambiguous in this sample, so I follow the source system."
        )
    return (
        f"Second format present, {spec}. Day-first, not month-first: "
        f"{day_first_evidence:,} of the failures lead with a number above 12, "
        "which rules out US ordering."
    )


def _read_line(result: LoadResult) -> str:
    return (
        f"read_csv: {result.name}.csv {result.rows:,} rows, "
        f"{len(result.columns)} columns, {result.parse_ms}ms"
    )


def _profile_line(result: ProfileResult) -> str:
    """Report what the fingerprinting actually found in the timestamp column."""
    for column in result.columns:
        if column.name == TIMESTAMP_COLUMN and column.formats:
            return (
                f"profile: {column.name} -> {len(column.formats)} distinct formats detected, "
                f"{result.profile_ms}ms"
            )
    return f"profile: {len(result.columns)} columns, {result.rows:,} rows, {result.profile_ms}ms"


def _quality_line(result: ProfileResult) -> str:
    """The agent's own reading of the profile, in counts it can point at."""
    nulls = {column.name: column.nulls for column in result.columns if column.nulls}
    if not nulls:
        return f"No nulls anywhere in {result.rows:,} rows. I still want to see the timestamps."
    worst = max(nulls.items(), key=lambda item: item[1])
    return (
        f"{worst[0]} is missing on {worst[1]:,} rows, {worst[1] / result.rows * 100:.1f}%. "
        "Within the budget, so I fill it and report the rate."
    )


def _record(ctx: BeatCtx, result: CleanResult) -> None:
    """File the task's metrics and the figures the verification pass restates."""
    ctx.kernel.record_metrics(
        ctx.task.id,
        TaskMetrics(
            rows_in=result.rows_in,
            rows_out=result.rows_out,
            rows_dropped=result.rows_dropped,
            null_rates=result.null_rates,
            duration_ms=0,  # The orchestrator owns the duration and overwrites this.
        ),
    )
    ctx.kernel.note("rows_in", result.rows_in)
    ctx.kernel.note("rows_clean", result.rows_out)
    ctx.kernel.note("rows_dropped", result.rows_dropped)
    ctx.kernel.note("duplicates_removed", result.duplicates_removed)
    ctx.kernel.note("qty_coerced", result.coerced_counts.get("qty", 0))
    ctx.kernel.note("discount_null_rate", result.null_rates.get("discount_pct", 0.0))
    ctx.kernel.note("timestamp_failures", result.failures)
