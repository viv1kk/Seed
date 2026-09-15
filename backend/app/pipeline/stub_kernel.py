"""TEMPORARY. Delete this file in phase 3.

The only sanctioned stub in the project, and it exists for one phase so that the
orchestrator, the runners, the event stream and the frontend can be built and
watched end to end before the real Polars pipeline lands.

It returns plausibly shaped results instantly. **Every number it returns is
invented**, which is exactly what CLAUDE.md rule 4 calls a defect, and the only
reason it is tolerable today is that it is scheduled for deletion:

    phase 3 replaces this with pipeline/load.py, profile.py, clean.py,
    transform.py and aggregate.py, reading backend/app/data/*.csv for real.

The real dataset already exists and its defects are already verified by
tests/test_generate_data.py, so nothing here is guessing at what the real
numbers will be shaped like. Do not let a figure from this file reach a demo.
"""

from typing import Final

from app.core.types import Artifact
from app.pipeline.results import (
    CleanResult,
    CleanStrategy,
    ColumnProfile,
    DeriveResult,
    JoinResult,
    LoadResult,
    ProfileResult,
)

# Named so that no reader mistakes them for measurements. They are shaped after
# the real dataset, so the narration reads correctly today and keeps reading
# correctly when phase 3 makes the figures true.
_PLACEHOLDER_ROWS: Final[dict[str, int]] = {
    "orders": 12_847,
    "products": 180,
    "customers": 2_400,
}
_PLACEHOLDER_COLUMNS: Final[dict[str, list[str]]] = {
    "orders": [
        "order_id", "order_ts", "customer_id", "region", "channel",
        "sku", "qty", "unit_price", "discount_pct", "status",
    ],
    "products": ["sku", "product_name", "category", "cost_price"],
    "customers": ["customer_id", "signup_date", "segment", "region"],
}
_PLACEHOLDER_DUPLICATES: Final[int] = 19
_PLACEHOLDER_DAY_FIRST: Final[int] = 771


class StubKernel:
    """A WorkKernel that does no work. See the module docstring."""

    def __init__(self) -> None:
        self._artifacts: dict[str, Artifact] = {}

    @property
    def artifacts(self) -> dict[str, Artifact]:
        return self._artifacts

    def _rows(self, name: str) -> int:
        return _PLACEHOLDER_ROWS.get(name, 1_000)

    def _columns(self, name: str) -> list[str]:
        return _PLACEHOLDER_COLUMNS.get(name, ["id", "value"])

    def load_csv(self, name: str) -> LoadResult:
        return LoadResult(
            name=name,
            rows=self._rows(name),
            columns=self._columns(name),
            parse_ms=0,
        )

    def profile(self, name: str) -> ProfileResult:
        rows = self._rows(name)
        return ProfileResult(
            rows=rows,
            columns=[
                ColumnProfile(
                    name=column,
                    nulls=0,
                    distinct=rows,
                    inferred_type="str",
                    formats=(
                        {"%Y-%m-%dT%H:%M:%S": rows - _PLACEHOLDER_DAY_FIRST,
                         "%d/%m/%Y %H:%M": _PLACEHOLDER_DAY_FIRST}
                        if column == "order_ts"
                        else None
                    ),
                )
                for column in self._columns(name)
            ],
            profile_ms=0,
        )

    def clean(self, name: str, strategy: CleanStrategy) -> CleanResult:
        rows = self._rows(name)
        dropped = _PLACEHOLDER_DUPLICATES if strategy.dedupe_on else 0
        return CleanResult(
            rows_in=rows,
            rows_out=rows - dropped,
            rows_dropped=dropped,
            duplicates_removed=dropped,
            coerced_counts=dict.fromkeys(strategy.coerce, 0),
            null_rates=dict.fromkeys(strategy.fill_nulls, 0.0),
            failures=0,
            clean_ms=0,
        )

    def join(self, left: str, right: str, on: str) -> JoinResult:  # noqa: ARG002
        # right and on are unused only because nothing is really joined yet.
        # The signature is the WorkKernel one, and phase 3 uses all three.
        rows = self._rows(left)
        return JoinResult(rows=rows, matched=rows, unmatched=0, join_ms=0)

    def derive(self, name: str) -> DeriveResult:
        return DeriveResult(
            rows=self._rows(name),
            columns_added=["net_revenue", "cogs", "margin", "margin_pct"],
            derive_ms=0,
        )

    def emit_artifact(self, artifact: Artifact) -> None:
        self._artifacts[artifact.id] = artifact
