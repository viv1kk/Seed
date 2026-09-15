"""What the work kernel returns.

These shapes are the contract between the pipeline and everything that narrates
it. They are fixed now, in phase 2, so that phase 3 replaces the *bodies* of the
kernel methods without touching a single caller.

Every field here is something that can be genuinely measured. Nothing is a
placeholder for a number a runner would like to say: if a log line wants a
figure, that figure has to appear in one of these, computed.
"""

from typing import Literal

from pydantic import BaseModel

CleanStrategyName = Literal["iso-strict", "multi-format-day-first"]


class CleanStrategy(BaseModel):
    """How to clean, decided by the agent and applied by the pipeline.

    ``iso-strict`` is expected to raise on the real orders extract. That is the
    failure beat, and the runner catches it. See docs/05-DATA-AND-PIPELINE.md.
    """

    timestamp: CleanStrategyName
    dedupe_on: str | None = None
    coerce: dict[str, str] = {}
    fill_nulls: dict[str, float] = {}


class LoadResult(BaseModel):
    name: str
    rows: int
    columns: list[str]
    parse_ms: int


class ColumnProfile(BaseModel):
    name: str
    nulls: int
    distinct: int
    inferred_type: str
    # For string columns: how many values match each detected shape. The
    # timestamp format detection the ETL agent uses to diagnose its failure
    # reads this.
    formats: dict[str, int] | None = None
    samples: list[str] | None = None


class ProfileResult(BaseModel):
    rows: int
    columns: list[ColumnProfile]
    profile_ms: int


class CleanResult(BaseModel):
    rows_in: int
    rows_out: int
    rows_dropped: int
    duplicates_removed: int
    coerced_counts: dict[str, int]
    null_rates: dict[str, float]
    failures: int
    clean_ms: int


class JoinResult(BaseModel):
    rows: int
    matched: int
    unmatched: int
    join_ms: int


class DeriveResult(BaseModel):
    rows: int
    columns_added: list[str]
    derive_ms: int


class ConflictResult(BaseModel):
    """What a join's duplicated column disagreed about, and which side won."""

    column: str
    resolved_to: str
    conflicts: int
    rows: int


class FormatProbe(BaseModel):
    """What a failed strict parse was actually looking at.

    Built after the exception has been raised, from the real frame. Polars
    reports its own failure against the chunk it gave up on ("9 out of 100
    values"), which is true of that chunk and not of the file, so the count
    worth telling anyone is established here, over every row.

    ``samples`` are values lifted out of the failing rows themselves. They are
    what a sceptic greps the source file for, so they have to be real.
    """

    column: str
    spec: str
    total: int
    parsed: int
    unparseable: int
    samples: list[str] = []
    # Candidate formats that read the values the strict parse could not, and how
    # many each one reads. Empty means nothing available would have helped.
    alternates: dict[str, int] = {}
    # Failing values whose first component is greater than 12. A day cannot be
    # read as a month, so one of these rules out month-first ordering outright.
    day_first_evidence: int = 0

    @property
    def failure_rate(self) -> float:
        return self.unparseable / self.total if self.total else 0.0


class DatasetPreview(BaseModel):
    """A handful of real rows off the front of a frame, for a dataset artifact.

    ``bytes`` is the whole frame's footprint as Polars measures it, not the
    preview's. A dataset artifact reporting the size of its own twenty-row
    sample would be describing the wrong thing entirely.
    """

    rows: int
    columns: list[str]
    bytes: int
    sample: list[list[str]]
