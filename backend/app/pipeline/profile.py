"""Look at a frame before deciding anything about it.

Two jobs, and the second is the interesting one.

**Profiling** counts nulls and distinct values per column and works out what
each column really holds, given that ``load.py`` read everything as text.

**Format fingerprinting** goes further. For a text column it matches every value
against a set of known shapes and counts how many fit each one. That is how a
mixed-format column becomes a fact rather than a suspicion: ``order_ts`` does not
come back as "a string", it comes back as two formats with a count against each.

``probe_format`` is the diagnostic pass. When a strict parse has already failed,
it answers the three questions worth asking next: how many values failed, what do
they actually look like, and is there a format that reads them. Every one of
those answers is measured against the frame in hand. None of it is arranged in
advance, which is the point: the same probe run against a clean file reports
zero failures and no alternate format.
"""

import re
import time
from dataclasses import dataclass
from typing import Final

import polars as pl

from app.pipeline.results import ColumnProfile, FormatProbe, ProfileResult

# How many example values to carry back. Enough to see a pattern, few enough to
# fit on one log line.
SAMPLE_SIZE: Final[int] = 3


@dataclass(frozen=True)
class FormatCandidate:
    """A strptime format and the shape of a value that would satisfy it."""

    spec: str
    pattern: str


# Ordered by how specific they are, so a value that could satisfy two candidates
# is counted against the narrower one.
TIMESTAMP_FORMATS: Final[tuple[FormatCandidate, ...]] = (
    FormatCandidate("%Y-%m-%dT%H:%M:%S", r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$"),
    FormatCandidate("%Y-%m-%d %H:%M:%S", r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"),
    FormatCandidate("%d/%m/%Y %H:%M", r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}$"),
    FormatCandidate("%Y-%m-%d", r"^\d{4}-\d{2}-\d{2}$"),
)

_INTEGER = re.compile(r"^\s*[-+]?\d+\s*$")
_DECIMAL = re.compile(r"^\s*[-+]?\d*\.\d+\s*$|^\s*[-+]?\d+\.\d*\s*$")


def fingerprint(series: pl.Series) -> dict[str, int]:
    """Count how many values in a text column fit each known timestamp shape.

    A value is counted once, against the first candidate it satisfies. Anything
    matching nothing is left out rather than bucketed as "other": the caller
    can subtract from the column length if it wants that number, and an empty
    result is the honest answer for a column that carries no timestamps.
    """
    counts: dict[str, int] = {}
    unclaimed = series.drop_nulls()

    for candidate in TIMESTAMP_FORMATS:
        if unclaimed.is_empty():
            break
        matches = unclaimed.str.contains(candidate.pattern)
        hits = int(matches.sum())
        if hits:
            counts[candidate.spec] = hits
            unclaimed = unclaimed.filter(~matches)

    return counts


def _infer_type(series: pl.Series) -> str:
    """Name what a text column is really carrying.

    Everything arrives as ``str`` from ``load.py``, so this reports what the
    values look like rather than what Polars was told. An all-empty column is
    ``empty`` rather than a guess.
    """
    values = series.drop_nulls()
    if values.is_empty():
        return "empty"
    if fingerprint(values):
        return "datetime"
    if bool(values.str.contains(_INTEGER.pattern).all()):
        return "int"
    if bool(values.str.contains(f"{_INTEGER.pattern}|{_DECIMAL.pattern}").all()):
        return "float"
    return "str"


def _samples(series: pl.Series, count: int = SAMPLE_SIZE) -> list[str]:
    """The first few distinct values, in the order they appear in the frame.

    ``maintain_order=True`` is not optional here even though this only feeds a
    log line: without it the samples shuffle between runs and two runs at the
    same seed stop producing identical logs.
    """
    distinct = series.drop_nulls().unique(maintain_order=True).head(count)
    return [str(value) for value in distinct.to_list()]


def profile(frame: pl.DataFrame) -> ProfileResult:
    """Describe every column of a frame. All counts measured, none assumed."""
    started = time.perf_counter()

    columns: list[ColumnProfile] = []
    for name in frame.columns:
        series = frame[name]
        formats = fingerprint(series) if series.dtype == pl.String else {}
        columns.append(
            ColumnProfile(
                name=name,
                nulls=series.null_count(),
                distinct=series.n_unique(),
                inferred_type=(
                    _infer_type(series) if series.dtype == pl.String else str(series.dtype)
                ),
                formats=formats or None,
                samples=_samples(series),
            )
        )

    return ProfileResult(
        rows=frame.height,
        columns=columns,
        profile_ms=round((time.perf_counter() - started) * 1000),
    )


def probe_format(frame: pl.DataFrame, column: str, spec: str) -> FormatProbe:
    """Measure what a strict parse of ``spec`` cannot read, and what would.

    Run after the strict parse has raised. Polars reports its own failure
    against a sample of the column ("9 out of 100 values"), which is true of the
    chunk it gave up on and not of the file, so the count worth telling anyone
    has to be established here, over every row.

    The samples are pulled from the failing rows themselves. They are the values
    a sceptic would grep the source file for.
    """
    values = frame[column]
    parsed = values.str.to_datetime(format=spec, strict=False)
    failing = frame.filter(parsed.is_null() & values.is_not_null())[column]

    alternates: dict[str, int] = {}
    for candidate in TIMESTAMP_FORMATS:
        if candidate.spec == spec or failing.is_empty():
            continue
        read_by_candidate = failing.str.to_datetime(format=candidate.spec, strict=False)
        reads = int(read_by_candidate.is_not_null().sum())
        if reads:
            alternates[candidate.spec] = reads

    return FormatProbe(
        column=column,
        spec=spec,
        total=values.len(),
        parsed=int(parsed.is_not_null().sum()),
        unparseable=failing.len(),
        samples=_samples(failing),
        alternates=alternates,
        day_first_evidence=_day_first_evidence(failing),
    )


def _day_first_evidence(failing: pl.Series) -> int:
    """Failing values whose leading number is greater than 12.

    This is what separates ``%d/%m`` from ``%m/%d`` on evidence rather than on
    convention. A value beginning 29 cannot be a month, so a single one of these
    settles the ordering; zero of them means the ordering is genuinely ambiguous
    and the agent has no business asserting either way.
    """
    if failing.is_empty():
        return 0
    leading = failing.str.extract(r"^(\d{1,2})[/-]", 1).cast(pl.Int32, strict=False)
    return int((leading > 12).sum())
