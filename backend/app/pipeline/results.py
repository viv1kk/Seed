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


class Filters(BaseModel):
    """Cross-filter applied to the retained derived frame. Phase 3."""

    date_from: str | None = None
    date_to: str | None = None
    category: str | None = None
    region: str | None = None


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
