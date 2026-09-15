"""Turn a text frame into a typed one, counting everything it costs.

This module is the one most likely to be read by somebody deciding whether to
believe the rest. It is written for that.

The shape of it: a strategy comes in describing what to do, four steps are
applied in a fixed order, and a count is recorded for each. Nothing is silently
corrected. If a row is dropped, the count says so; if a value is coerced, the
count says so; if a null is filled, the rate before filling is reported
alongside it. "A silent drop is a defect" is a line from the requirement
document, and this is where it is honoured or not.

The order is deliberate and the steps are not commutative:

1. **Timestamps**, because deduplication needs them to know which row is latest.
2. **Deduplicate**, before any counting of values, so the counts describe the
   rows that survive rather than rows about to be thrown away.
3. **Coerce**, turning text into numbers and recording how many values needed it.
4. **Fill nulls**, recording the rate before the fill, because afterwards there
   is nothing left to measure.

## On the strict timestamp parse

``iso-strict`` raises against the real orders extract. That is not a bug being
worked around here, and this module must not defend against it: no pre-check, no
internal try/except, no flag that quietly falls back. The caller catches the
exception and decides what to do, which is the only place that decision belongs.

The two strategies are the same parse expressed two ways. The strict one asserts
a single format and fails loudly when the file disagrees. The coalescing one
tries formats in order and takes the first that reads a given value, which
means a mixed-format column resolves without any row being dropped for it.
"""

import time
from dataclasses import dataclass
from typing import Final

import polars as pl

from app.pipeline.results import CleanResult, CleanStrategy

# The one format the strict strategy will accept.
ISO_TIMESTAMP: Final[str] = "%Y-%m-%dT%H:%M:%S"

# Tried in order by the coalescing strategy. The first that reads a value wins,
# so a mixed column resolves row by row rather than being forced into one shape.
FALLBACK_TIMESTAMPS: Final[tuple[str, ...]] = ("%d/%m/%Y %H:%M",)

TIMESTAMP_COLUMN: Final[str] = "order_ts"

# Target types a strategy may ask for by name.
COERCIONS: Final[dict[str, pl.DataType]] = {
    "int": pl.Int64(),
    "float": pl.Float64(),
}


@dataclass(frozen=True)
class CleanOutput:
    """The cleaned frame and the record of what cleaning it took."""

    frame: pl.DataFrame
    stats: CleanResult


def parse_timestamps(frame: pl.DataFrame, strategy_name: str) -> pl.DataFrame:
    """Parse the timestamp column under one of the two strategies.

    ``iso-strict`` asserts that every value is ISO 8601 and lets Polars raise
    ``InvalidOperationError`` when one is not. Read that as the assertion it is:
    the pipeline is stating a belief about the file and finding out it is wrong.

    ``multi-format-day-first`` coalesces the ISO parse with each fallback in
    turn. Every parse inside the coalesce is non-strict, so a value that a given
    format cannot read becomes null and falls through to the next one instead of
    ending the run. A value no format reads stays null and is counted later as a
    failure rather than disappearing.
    """
    if strategy_name == "iso-strict":
        return frame.with_columns(
            pl.col(TIMESTAMP_COLUMN).str.to_datetime(format=ISO_TIMESTAMP, strict=True)
        )

    return frame.with_columns(
        pl.coalesce(
            pl.col(TIMESTAMP_COLUMN).str.to_datetime(format=ISO_TIMESTAMP, strict=False),
            *(
                pl.col(TIMESTAMP_COLUMN).str.to_datetime(format=spec, strict=False)
                for spec in FALLBACK_TIMESTAMPS
            ),
        ).alias(TIMESTAMP_COLUMN)
    )


def deduplicate(frame: pl.DataFrame, key: str) -> tuple[pl.DataFrame, int]:
    """Keep the most recent row per key. Returns the frame and how many went.

    "Most recent" is decided by the timestamp parsed in the previous step, which
    is why that step comes first. Sorting and keeping the last occurrence is the
    plain reading of the rule from the requirement document, and it keeps the
    surviving row whole rather than merging fields across duplicates.

    ``maintain_order=True`` on the uniqueness pass is what makes the result the
    same frame every run. Without it the retained rows come back in whatever
    order the hash table produced, and every downstream figure that depends on
    row order, including the samples quoted in the log, drifts between runs.
    """
    before = frame.height
    kept = frame.sort(TIMESTAMP_COLUMN).unique(subset=[key], keep="last", maintain_order=True)
    return kept, before - kept.height


def coerce_column(frame: pl.DataFrame, column: str, target: str) -> tuple[pl.DataFrame, int]:
    """Cast a text column to a number, reporting how many values needed help.

    "Needed help" is measured rather than assumed: a value counts only if a
    plain cast of the raw text fails and a cast of the tidied text succeeds.
    That excludes values which were already clean, and it excludes values which
    are beyond saving, so the number is exactly the repair work done.

    The tidying is whitespace and a redundant decimal tail, which is what a
    spreadsheet export does to an integer column.
    """
    dtype = COERCIONS[target]
    raw = pl.col(column)
    tidied = raw.str.strip_chars().str.replace(r"\.0+$", "")

    needed = frame.select(
        (raw.cast(dtype, strict=False).is_null() & tidied.cast(dtype, strict=False).is_not_null())
        .sum()
        .alias("needed")
    ).item()

    return frame.with_columns(tidied.cast(dtype, strict=False).alias(column)), int(needed)


def clean(frame: pl.DataFrame, strategy: CleanStrategy) -> CleanOutput:
    """Apply a cleaning strategy and return the frame with a full account of it.

    Raises whatever the timestamp parse raises. See the module docstring.
    """
    started = time.perf_counter()
    rows_in = frame.height

    working = parse_timestamps(frame, strategy.timestamp)

    duplicates_removed = 0
    if strategy.dedupe_on is not None:
        working, duplicates_removed = deduplicate(working, strategy.dedupe_on)

    coerced_counts: dict[str, int] = {}
    for column, target in strategy.coerce.items():
        working, coerced_counts[column] = coerce_column(working, column, target)

    # Measured before the fill, because a filled column has no null rate left to
    # report and the rate is the thing the quality rules asked us to record.
    null_rates: dict[str, float] = {}
    for column, value in strategy.fill_nulls.items():
        null_rates[column] = (
            working[column].null_count() / working.height if working.height else 0.0
        )
        working = working.with_columns(
            pl.col(column).cast(pl.Float64, strict=False).fill_null(value).alias(column)
        )

    # A row whose timestamp no format could read. Dropped, and counted, so the
    # drop shows up against the budget instead of vanishing.
    failures = int(working[TIMESTAMP_COLUMN].null_count())
    if failures:
        working = working.filter(pl.col(TIMESTAMP_COLUMN).is_not_null())

    return CleanOutput(
        frame=working,
        stats=CleanResult(
            rows_in=rows_in,
            rows_out=working.height,
            rows_dropped=rows_in - working.height,
            duplicates_removed=duplicates_removed,
            coerced_counts=coerced_counts,
            null_rates=null_rates,
            failures=failures,
            clean_ms=round((time.perf_counter() - started) * 1000),
        ),
    )
