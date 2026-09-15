"""Join the extracts together and work out the money.

Two halves.

``join`` attaches a reference table and reports the match rate. The match rate is
computed every time, including when it ought to be 100%. A join that silently
drops a tenth of the rows looks exactly like a join that worked, right up until
someone adds the revenue up by hand, and the only defence is to measure it and
say the number out loud.

``derive`` adds the money columns. The three formulas are taken from the
requirement document verbatim, because they are the definitions the client
argues about and paraphrasing them is how a pipeline ends up computing something
nobody asked for:

    net_revenue = qty * unit_price * (1 - discount_pct)
    cogs        = qty * cost_price
    margin      = net_revenue - cogs

Returned orders carry a negative ``qty``, so their revenue comes out negative by
construction. That is deliberate and it is not corrected here. ``aggregate.py``
decides which statuses count towards revenue; this module's job is to describe
every row honestly and leave the policy to the step that owns it.
"""

import time
from dataclasses import dataclass

import polars as pl

from app.pipeline.results import DeriveResult, JoinResult

# Added by ``derive``, in the order they are computed. Reported back so a runner
# can say what it added without restating the list.
DERIVED_COLUMNS: tuple[str, ...] = (
    "gross_revenue",
    "net_revenue",
    "cogs",
    "margin",
    "margin_pct",
    "order_date",
    "order_week",
)


@dataclass(frozen=True)
class JoinOutput:
    frame: pl.DataFrame
    stats: JoinResult


@dataclass(frozen=True)
class DeriveOutput:
    frame: pl.DataFrame
    stats: DeriveResult


def join(left: pl.DataFrame, right: pl.DataFrame, on: str) -> JoinOutput:
    """Inner join, with the match rate measured rather than assumed.

    ``matched`` counts rows of ``left`` that found a partner and ``unmatched``
    counts those that did not. They are established before the join rather than
    inferred from its height, so a right side with duplicate keys, which would
    make the joined frame taller than the left one, cannot make an unmatched row
    look matched.
    """
    started = time.perf_counter()

    # A semi join counts the left rows that found a partner without letting a
    # duplicated key on the right multiply them, which is the number wanted.
    matched = left.join(right.select(on).unique(), on=on, how="semi").height

    joined = left.join(right, on=on, how="inner")

    return JoinOutput(
        frame=joined,
        stats=JoinResult(
            rows=joined.height,
            matched=matched,
            unmatched=left.height - matched,
            join_ms=round((time.perf_counter() - started) * 1000),
        ),
    )


def resolve_conflict(frame: pl.DataFrame, column: str, *, losing: str) -> tuple[pl.DataFrame, int]:
    """Drop a column a join duplicated, counting the rows where the two disagreed.

    Both sides carry ``region`` and they do not always agree. The order-level
    value wins: it describes where the order was placed, which is the question
    the dashboard asks, while the customer record describes where that customer
    currently sits and may have been updated since.

    The disagreement count is returned so the choice is reported rather than
    made quietly. Resolving a conflict without saying how often it occurred is
    the same defect as dropping a row without counting it.
    """
    if losing not in frame.columns:
        return frame, 0

    disagreements = int(frame.filter(pl.col(column) != pl.col(losing)).height)
    return frame.drop(losing), disagreements


def derive(frame: pl.DataFrame) -> DeriveOutput:
    """Add the revenue, cost and margin columns, plus the two date grains.

    ``cost_price`` is cast here because it arrives from the products extract,
    which is a reference table that never went through a cleaning pass. Casting
    it at the point of use keeps the cast visible next to the arithmetic that
    depends on it.
    """
    started = time.perf_counter()

    qty = pl.col("qty")
    unit_price = pl.col("unit_price")
    discount = pl.col("discount_pct")
    cost_price = pl.col("cost_price").cast(pl.Float64, strict=False)
    order_ts = pl.col("order_ts")

    gross_revenue = qty * unit_price
    net_revenue = qty * unit_price * (1 - discount)
    cogs = qty * cost_price
    margin = net_revenue - cogs

    derived = frame.with_columns(
        gross_revenue.alias("gross_revenue"),
        net_revenue.alias("net_revenue"),
        cogs.alias("cogs"),
        margin.alias("margin"),
        # Undefined rather than zero where there is no revenue to take a
        # percentage of. A margin percentage on a zero-revenue line is not a
        # number, and writing zero there would drag every average towards it.
        pl.when(net_revenue != 0)
        .then(margin / net_revenue)
        .otherwise(None)
        .alias("margin_pct"),
        order_ts.dt.date().alias("order_date"),
        # The Monday of the order's week, anchored explicitly. Polars can
        # truncate to a week, but its anchor comes from the epoch rather than
        # from the calendar, and a weekly chart that starts on a Thursday is the
        # kind of thing nobody notices until it is on a projector.
        (order_ts.dt.date() - pl.duration(days=order_ts.dt.weekday() - 1)).alias("order_week"),
    )

    return DeriveOutput(
        frame=derived,
        stats=DeriveResult(
            rows=derived.height,
            columns_added=list(DERIVED_COLUMNS),
            derive_ms=round((time.perf_counter() - started) * 1000),
        ),
    )
