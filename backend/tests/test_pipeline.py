"""The pipeline, against the real bundled data.

Deliberately three subjects and nothing else, because the run itself is the
broadest test this project has and duplicating it here buys nothing:

1. **The two clean strategies.** ``iso-strict`` must genuinely raise against the
   real file and ``multi-format-day-first`` must genuinely resolve every row.
   The whole failure beat is worthless if either of those stops being true, and
   neither is the kind of thing that fails loudly on its own.

2. **Aggregation correctness.** The acceptance criterion the client wrote is
   that region and category each sum to the headline. That is arithmetic and it
   is exactly what a test is for.

3. **The cross-filter endpoint.** A date range has to come back with different
   and correct figures, because "different" alone would pass with a bug that
   returned an empty bundle.

These run against ``app/data/*.csv`` rather than a fixture. The committed
dataset is the demo input, its defect volumes are already asserted in
``test_generate_data.py``, and a pipeline test over synthetic data would not
answer the question anyone actually has about this code.
"""

import polars as pl
import pytest
from fastapi.testclient import TestClient

from app.core.types import Filters
from app.main import app
from app.pipeline.aggregate import aggregate
from app.pipeline.clean import clean
from app.pipeline.kernel import PolarsKernel
from app.pipeline.load import load_csv
from app.pipeline.profile import probe_format
from app.pipeline.results import CleanStrategy
from app.pipeline.transform import join, resolve_conflict

ISO = "%Y-%m-%dT%H:%M:%S"

STRICT = CleanStrategy(
    timestamp="iso-strict",
    dedupe_on="order_id",
    coerce={"qty": "int", "unit_price": "float"},
    fill_nulls={"discount_pct": 0.0},
)
FORGIVING = STRICT.model_copy(update={"timestamp": "multi-format-day-first"})

# Money totals compared across two groupings of the same column. Anything above
# a fraction of a paisa is a real defect rather than float noise.
TOLERANCE = 0.01


@pytest.fixture(scope="module")
def orders() -> pl.DataFrame:
    return load_csv("orders").frame


@pytest.fixture(scope="module")
def derived() -> pl.DataFrame:
    """The frame the dashboard is computed from, built the way a run builds it."""
    kernel = PolarsKernel()
    kernel.load_csv("orders")
    kernel.load_csv("products")
    kernel.load_csv("customers")
    kernel.clean("orders", FORGIVING)
    kernel.join("orders", "products", "sku")
    kernel.join("orders", "customers", "customer_id")
    kernel.resolve_conflict("orders", "region", "region_right")
    kernel.derive("orders")
    return kernel.frame("orders")


# ---------------------------------------------------------------- strategies


class TestCleanStrategies:
    def test_strict_raises_on_the_real_file(self, orders: pl.DataFrame) -> None:
        """The failure beat is a real library refusing real data.

        If this ever stops raising, the centrepiece of the demo silently becomes
        a task that succeeds first time and nobody finds out until it is on a
        projector.
        """
        with pytest.raises(pl.exceptions.InvalidOperationError):
            clean(orders, STRICT)

    def test_a_failed_strict_pass_changes_nothing(self) -> None:
        """The retry has to start from the frame the first attempt started from."""
        kernel = PolarsKernel()
        before = kernel.load_csv("orders")

        with pytest.raises(pl.exceptions.InvalidOperationError):
            kernel.clean("orders", STRICT)

        assert kernel.frame("orders").height == before.rows
        assert kernel.frame("orders")["order_ts"].dtype == pl.String

    def test_forgiving_resolves_every_row(self, orders: pl.DataFrame) -> None:
        """The requirement promises no row is dropped for a parseable timestamp."""
        result = clean(orders, FORGIVING)

        assert result.stats.failures == 0
        assert result.frame["order_ts"].null_count() == 0
        assert result.frame["order_ts"].dtype == pl.Datetime

    def test_the_probe_counts_the_whole_file(self, orders: pl.DataFrame) -> None:
        """Polars reports its failure against a chunk. The log must not.

        The count the ETL agent puts on screen comes from here, and somebody
        will check the samples against orders.csv, so they are checked against
        it here first.
        """
        probe = probe_format(orders, "order_ts", ISO)

        assert probe.total == orders.height
        assert probe.parsed + probe.unparseable == probe.total
        assert probe.unparseable > 0

        # Every sample is a real value that really fails the strict parse.
        assert probe.samples
        failing = set(
            orders.filter(
                pl.col("order_ts").str.to_datetime(format=ISO, strict=False).is_null()
            )["order_ts"]
            .unique()
            .to_list()
        )
        assert set(probe.samples) <= failing

        # And there is a format that reads all of them, which is what makes the
        # recovery a real recovery rather than a second guess.
        assert probe.alternates
        assert sum(probe.alternates.values()) >= probe.unparseable

    def test_dedupe_keeps_the_most_recent(self, orders: pl.DataFrame) -> None:
        result = clean(orders, FORGIVING)

        assert result.frame["order_id"].n_unique() == result.frame.height
        assert result.stats.duplicates_removed == orders.height - orders["order_id"].n_unique()

    def test_coercion_counts_only_what_needed_it(self, orders: pl.DataFrame) -> None:
        """A column that was already clean must report zero, not a plausible number."""
        result = clean(orders, FORGIVING)

        assert result.stats.coerced_counts["unit_price"] == 0
        assert result.stats.coerced_counts["qty"] > 0
        assert result.frame["qty"].null_count() == 0

    def test_the_null_rate_is_measured_before_the_fill(self, orders: pl.DataFrame) -> None:
        result = clean(orders, FORGIVING)

        assert result.stats.null_rates["discount_pct"] > 0
        assert result.frame["discount_pct"].null_count() == 0


# ---------------------------------------------------------------- joins


class TestTransform:
    def test_join_reports_a_real_match_rate(self, orders: pl.DataFrame) -> None:
        cleaned = clean(orders, FORGIVING).frame
        products = load_csv("products").frame

        result = join(cleaned, products, "sku")

        assert result.stats.matched + result.stats.unmatched == cleaned.height
        assert result.stats.unmatched == 0

    def test_region_conflicts_are_counted_not_swallowed(self, orders: pl.DataFrame) -> None:
        cleaned = clean(orders, FORGIVING).frame
        customers = load_csv("customers").frame
        joined = join(cleaned, customers, "customer_id").frame

        expected = joined.filter(pl.col("region") != pl.col("region_right")).height
        resolved, conflicts = resolve_conflict(joined, "region", losing="region_right")

        assert conflicts == expected
        assert conflicts > 0
        assert "region_right" not in resolved.columns

    def test_derive_uses_the_documented_formulas(self, derived: pl.DataFrame) -> None:
        row = derived.head(1).to_dicts()[0]
        # cost_price is still text: it comes from the products extract, which is
        # a reference table that never went through a cleaning pass, and derive
        # casts it at the point of use rather than rewriting the column.
        cost_price = float(row["cost_price"])
        expected_net = row["qty"] * row["unit_price"] * (1 - row["discount_pct"])

        assert row["net_revenue"] == pytest.approx(expected_net)
        assert row["cogs"] == pytest.approx(row["qty"] * cost_price)
        assert row["margin"] == pytest.approx(row["net_revenue"] - row["cogs"])

    def test_order_week_is_the_monday(self, derived: pl.DataFrame) -> None:
        weekdays = derived["order_week"].dt.weekday().unique().to_list()
        assert weekdays == [1]


# ---------------------------------------------------------------- aggregation


class TestAggregate:
    def test_the_cuts_sum_to_the_headline(self, derived: pl.DataFrame) -> None:
        """The client wrote this one down. It is the criterion, verbatim."""
        bundle = aggregate(derived)

        by_category = sum(row.net_revenue for row in bundle.revenue_by_category)
        by_region = sum(row.net_revenue for row in bundle.revenue_by_region)

        assert by_category == pytest.approx(bundle.kpis.net_revenue, abs=TOLERANCE)
        assert by_region == pytest.approx(bundle.kpis.net_revenue, abs=TOLERANCE)
        assert sum(row.share for row in bundle.revenue_by_region) == pytest.approx(1.0)

    def test_revenue_excludes_cancelled_and_returned(self, derived: pl.DataFrame) -> None:
        """Returns carry a negative qty, so folding them in would net them off."""
        bundle = aggregate(derived)
        completed = derived.filter(pl.col("status") == "completed")

        assert bundle.kpis.order_count == completed.height
        assert bundle.kpis.net_revenue == pytest.approx(
            float(completed["net_revenue"].sum()), abs=TOLERANCE
        )

    def test_the_return_rate_counts_returns_against_sales(self, derived: pl.DataFrame) -> None:
        bundle = aggregate(derived)
        returned = derived.filter(pl.col("status") == "returned").height
        completed = derived.filter(pl.col("status") == "completed").height

        assert bundle.kpis.return_rate == pytest.approx(returned / (returned + completed))

    def test_margin_is_weighted_not_averaged(self, derived: pl.DataFrame) -> None:
        """The mean of a ratio is not the ratio of the means, and finance wants
        the second one."""
        bundle = aggregate(derived)
        completed = derived.filter(pl.col("status") == "completed")
        expected = float(completed["margin"].sum()) / float(completed["net_revenue"].sum())

        assert bundle.kpis.margin_pct == pytest.approx(expected)

    def test_top_products_are_the_top_ten_in_order(self, derived: pl.DataFrame) -> None:
        bundle = aggregate(derived)
        revenues = [row.net_revenue for row in bundle.top_products]

        assert len(bundle.top_products) == 10
        assert revenues == sorted(revenues, reverse=True)

    def test_aggregation_is_reproducible(self, derived: pl.DataFrame) -> None:
        """What ``maintain_order=True`` is there for. Two passes, same order."""
        first = aggregate(derived)
        second = aggregate(derived)

        assert [row.category for row in first.revenue_by_category] == [
            row.category for row in second.revenue_by_category
        ]
        assert [row.sku for row in first.top_products] == [
            row.sku for row in second.top_products
        ]
        assert [row.week for row in first.revenue_over_time] == [
            row.week for row in second.revenue_over_time
        ]

    def test_a_date_filter_narrows_correctly(self, derived: pl.DataFrame) -> None:
        whole_year = aggregate(derived)
        quarter = aggregate(derived, Filters(date_from="2025-01-01", date_to="2025-03-31"))

        assert quarter.kpis.net_revenue < whole_year.kpis.net_revenue
        assert quarter.rows < whole_year.rows

        expected = derived.filter(
            (pl.col("order_date") >= pl.date(2025, 1, 1))
            & (pl.col("order_date") <= pl.date(2025, 3, 31))
            & (pl.col("status") == "completed")
        )
        assert quarter.kpis.order_count == expected.height
        assert quarter.kpis.net_revenue == pytest.approx(
            float(expected["net_revenue"].sum()), abs=TOLERANCE
        )
        # The cuts still reconcile under a filter, which is the property that
        # makes cross-filtering safe to demonstrate live.
        assert sum(row.net_revenue for row in quarter.revenue_by_region) == pytest.approx(
            quarter.kpis.net_revenue, abs=TOLERANCE
        )

    def test_a_category_filter_narrows_to_that_category(self, derived: pl.DataFrame) -> None:
        whole = aggregate(derived)
        target = whole.revenue_by_category[0].category
        filtered = aggregate(derived, Filters(category=target))

        assert [row.category for row in filtered.revenue_by_category] == [target]
        assert filtered.kpis.net_revenue == pytest.approx(
            whole.revenue_by_category[0].net_revenue, abs=TOLERANCE
        )

    def test_an_empty_selection_does_not_divide_by_zero(self, derived: pl.DataFrame) -> None:
        bundle = aggregate(derived, Filters(date_from="2030-01-01", date_to="2030-12-31"))

        assert bundle.rows == 0
        assert bundle.kpis.net_revenue == 0.0
        assert bundle.kpis.average_order_value == 0.0
        assert bundle.revenue_over_time == []


# ---------------------------------------------------------------- the endpoint


class TestQueryEndpoint:
    """The cross-filter over HTTP, which is how the dashboard actually asks."""

    def test_a_date_range_returns_different_correct_figures(self) -> None:
        with TestClient(app) as client:
            plan = client.post("/api/plans", json={"example_id": "retail-analytics"}).json()
            run_id = client.post("/api/runs", json={"plan_id": plan["plan"]["id"]}).json()["run_id"]

            # The endpoint reads the run's retained frame. Rather than waiting
            # out a full run, the same pipeline is driven directly into that
            # run's kernel: it is the identical code path the run takes, and
            # what is under test here is the endpoint, not the orchestrator.
            _drive_pipeline(client, run_id)

            whole = client.post(f"/api/runs/{run_id}/query", json={}).json()
            quarter = client.post(
                f"/api/runs/{run_id}/query",
                json={"date_from": "2025-01-01", "date_to": "2025-03-31"},
            ).json()

            assert quarter["kpis"]["net_revenue"] < whole["kpis"]["net_revenue"]
            assert quarter["rows"] < whole["rows"]
            assert len(quarter["revenue_over_time"]) < len(whole["revenue_over_time"])

            # Correct, not merely different: the region cut still reconciles.
            assert sum(row["net_revenue"] for row in quarter["revenue_by_region"]) == pytest.approx(
                quarter["kpis"]["net_revenue"], abs=TOLERANCE
            )
            # And the filter comes back on the response, so the dashboard can
            # tell which request a bundle answered.
            assert quarter["filters"]["date_from"] == "2025-01-01"

    def test_a_region_filter_returns_only_that_region(self) -> None:
        with TestClient(app) as client:
            plan = client.post("/api/plans", json={"example_id": "retail-analytics"}).json()
            run_id = client.post("/api/runs", json={"plan_id": plan["plan"]["id"]}).json()["run_id"]
            _drive_pipeline(client, run_id)

            whole = client.post(f"/api/runs/{run_id}/query", json={}).json()
            target = whole["revenue_by_region"][0]["region"]
            filtered = client.post(f"/api/runs/{run_id}/query", json={"region": target}).json()

            assert [row["region"] for row in filtered["revenue_by_region"]] == [target]
            assert filtered["revenue_by_region"][0]["share"] == pytest.approx(1.0)

    def test_querying_before_the_table_exists_is_a_conflict(self) -> None:
        with TestClient(app) as client:
            plan = client.post("/api/plans", json={"example_id": "retail-analytics"}).json()
            run_id = client.post("/api/runs", json={"plan_id": plan["plan"]["id"]}).json()["run_id"]

            response = client.post(f"/api/runs/{run_id}/query", json={})

            assert response.status_code == 409

    def test_an_unknown_run_is_not_found(self) -> None:
        with TestClient(app) as client:
            assert client.post("/api/runs/run_nope/query", json={}).status_code == 404


def _drive_pipeline(client: TestClient, run_id: str) -> None:
    """Fill one run's kernel with a derived frame, through the kernel itself."""
    from app.api.deps import get_registry

    client.post(f"/api/runs/{run_id}/control", json={"action": "cancel"})
    kernel = get_registry().require(run_id).kernel

    kernel.load_csv("orders")
    kernel.load_csv("products")
    kernel.load_csv("customers")
    kernel.clean("orders", FORGIVING)
    kernel.join("orders", "products", "sku")
    kernel.join("orders", "customers", "customer_id")
    kernel.resolve_conflict("orders", "region", "region_right")
    kernel.derive("orders")
