"""The bundled dataset, and the defects the demo depends on.

These assertions are not about the generator being tidy. Each deliberate defect
is the reason an agent has something true to say, and the timestamp defect
carries the failure and retry beat, which is the single most important moment in
the run. If the data stops being wrong in exactly the right way, the demo
quietly becomes a progress bar.

The timestamp tests at the bottom belong in the pipeline's own test file. The
pipeline does not exist until phase 3, so they live here for now and move with
``clean.py`` when it arrives. They assert the exact expressions from
``docs/05-DATA-AND-PIPELINE.md``, against the committed file rather than a
fixture, because what matters is the real bytes on disk.
"""

import filecmp
from pathlib import Path

import polars as pl
import pytest

from scripts.generate_data import (
    CATEGORIES,
    DAY_FIRST_TIMESTAMPS,
    DIRTY_QTY_ROWS,
    DUPLICATE_ORDERS,
    EMPTY_DISCOUNT_ROWS,
    PRODUCT_ROWS,
    REGION_MISMATCH_ROWS,
    TOTAL_ORDER_ROWS,
    generate_all,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "app" / "data"

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"
DAY_FIRST_FORMAT = "%d/%m/%Y %H:%M"


def _read(name: str) -> pl.DataFrame:
    """Read the way the pipeline will: everything as Utf8, no inference.

    Inferring types here would paper over the very defects under test.
    """
    return pl.read_csv(DATA_DIR / name, infer_schema_length=0)


@pytest.fixture(scope="module")
def orders() -> pl.DataFrame:
    return _read("orders.csv")


@pytest.fixture(scope="module")
def products() -> pl.DataFrame:
    return _read("products.csv")


@pytest.fixture(scope="module")
def customers() -> pl.DataFrame:
    return _read("customers.csv")


# ---------------------------------------------------------------- shape


def test_the_committed_files_exist() -> None:
    for name in ("orders.csv", "products.csv", "customers.csv"):
        assert (DATA_DIR / name).exists(), f"{name} is missing. Run: python tasks.py data"


def test_row_counts(orders: pl.DataFrame, products: pl.DataFrame, customers: pl.DataFrame) -> None:
    assert orders.height == TOTAL_ORDER_ROWS == 12_847
    assert products.height == PRODUCT_ROWS == 180
    assert customers.height == 2_400


def test_columns_match_the_specification(
    orders: pl.DataFrame, products: pl.DataFrame, customers: pl.DataFrame
) -> None:
    assert orders.columns == [
        "order_id", "order_ts", "customer_id", "region", "channel",
        "sku", "qty", "unit_price", "discount_pct", "status",
    ]
    assert products.columns == ["sku", "product_name", "category", "cost_price"]
    assert customers.columns == ["customer_id", "signup_date", "segment", "region"]


def test_every_foreign_key_resolves(
    orders: pl.DataFrame, products: pl.DataFrame, customers: pl.DataFrame
) -> None:
    """The join match rate is reported as measured, but it should be total.

    An unresolvable key would be a defect nobody asked for, and would muddy the
    ones that are deliberate.
    """
    assert set(orders["sku"].unique()) <= set(products["sku"])
    assert set(orders["customer_id"].unique()) <= set(customers["customer_id"])


def test_products_span_eight_categories(products: pl.DataFrame) -> None:
    assert set(products["category"]) == set(CATEGORIES)
    assert len(CATEGORIES) == 8


# ---------------------------------------------------------------- defects


def test_duplicate_order_ids(orders: pl.DataFrame) -> None:
    """19 rows repeat an order_id. The ETL agent dedupes keeping the latest."""
    assert orders.height - orders["order_id"].n_unique() == DUPLICATE_ORDERS == 19


def test_a_duplicate_pair_differs_in_timestamp(orders: pl.DataFrame) -> None:
    """Otherwise "keep the most recent" is a rule with nothing to choose."""
    repeated = (
        orders.group_by("order_id", maintain_order=True)
        .len()
        .filter(pl.col("len") > 1)["order_id"]
        .to_list()
    )
    assert len(repeated) == DUPLICATE_ORDERS

    for order_id in repeated:
        rows = orders.filter(pl.col("order_id") == order_id)
        assert rows["order_ts"].n_unique() == rows.height, order_id


def test_day_first_timestamp_count(orders: pl.DataFrame) -> None:
    assert orders.filter(pl.col("order_ts").str.contains("/")).height == DAY_FIRST_TIMESTAMPS


def test_dirty_quantity_count(orders: pl.DataFrame) -> None:
    """Whitespace padding or a trailing .0, as a spreadsheet export leaves them."""
    dirty = orders.filter(
        (pl.col("qty") != pl.col("qty").str.strip_chars()) | pl.col("qty").str.contains(r"\.")
    )
    assert dirty.height == DIRTY_QTY_ROWS


def test_empty_discount_count(orders: pl.DataFrame) -> None:
    assert orders["discount_pct"].null_count() == EMPTY_DISCOUNT_ROWS


def test_region_mismatch_count(orders: pl.DataFrame, customers: pl.DataFrame) -> None:
    """About 3% of orders disagree with the customer record on region.

    The Analytics Engineer resolves these in favour of the order-level region.
    """
    joined = orders.join(
        customers.select("customer_id", pl.col("region").alias("customer_region")),
        on="customer_id",
        how="left",
    )
    mismatched = joined.filter(pl.col("region") != pl.col("customer_region"))
    assert mismatched.height == REGION_MISMATCH_ROWS


def test_returns_carry_a_negative_quantity_and_nothing_else_does(orders: pl.DataFrame) -> None:
    quantities = orders.with_columns(
        pl.col("qty").str.strip_chars().cast(pl.Float64).alias("q")
    )
    assert quantities.filter((pl.col("status") == "returned") & (pl.col("q") >= 0)).height == 0
    assert quantities.filter((pl.col("status") != "returned") & (pl.col("q") < 0)).height == 0


def test_every_status_is_one_of_the_three(orders: pl.DataFrame) -> None:
    assert set(orders["status"]) == {"completed", "returned", "cancelled"}


def test_cost_price_leaves_a_real_margin_spread(products: pl.DataFrame) -> None:
    """Margin must vary across the catalogue, or the category chart is flat."""
    costs = products["cost_price"].cast(pl.Float64)
    assert costs.min() is not None
    assert costs.n_unique() > PRODUCT_ROWS // 2


# ---------------------------------------------------------------- reproducibility


def test_regenerating_reproduces_the_committed_files_byte_for_byte(tmp_path: Path) -> None:
    """Seeded and deterministic, or the committed dataset drifts under us.

    Every number on the dashboard is computed from these exact bytes.
    """
    generate_all(tmp_path)

    for name in ("orders.csv", "products.csv", "customers.csv"):
        assert filecmp.cmp(tmp_path / name, DATA_DIR / name, shallow=False), (
            f"{name} changed. If the generator was edited deliberately, "
            f"rerun `python tasks.py data` and commit the result."
        )


def test_the_files_use_unix_line_endings() -> None:
    """Byte-identical across platforms depends on this."""
    assert b"\r\n" not in (DATA_DIR / "orders.csv").read_bytes()


# ---------------------------------------------------------------- the failure beat
#
# Moves to tests/test_clean.py in phase 3, alongside pipeline/clean.py.


def test_the_strict_iso_parse_genuinely_raises_on_the_committed_file(
    orders: pl.DataFrame,
) -> None:
    """The failure beat is a real library raising on real malformed data.

    This is the `iso-strict` strategy from docs/05-DATA-AND-PIPELINE.md, exactly
    as the pipeline will run it. If this ever stops raising, the ETL agent's
    retry has nothing to recover from and the centre of the demo is gone.

    Do not "fix" this by pre-checking or by passing strict=False. The runner is
    supposed to catch it.
    """
    with pytest.raises(pl.exceptions.InvalidOperationError):
        orders.with_columns(
            pl.col("order_ts").str.to_datetime(format=ISO_FORMAT, strict=True)
        )


def test_the_coalesced_two_format_parse_resolves_every_row(orders: pl.DataFrame) -> None:
    """The `multi-format-day-first` strategy, which is the recovery.

    The requirement document promises that no row is dropped for a timestamp we
    can parse by any reasonable rule, so zero nulls is the acceptance criterion,
    not merely a good result.
    """
    parsed = orders.with_columns(
        pl.coalesce(
            pl.col("order_ts").str.to_datetime(format=ISO_FORMAT, strict=False),
            pl.col("order_ts").str.to_datetime(format=DAY_FIRST_FORMAT, strict=False),
        ).alias("order_ts")
    )

    assert parsed["order_ts"].null_count() == 0
    assert parsed.height == orders.height


def test_the_non_strict_probe_reports_the_real_failing_count(orders: pl.DataFrame) -> None:
    """The count the ETL agent puts in its log line comes from this pass."""
    probe = orders.select(
        pl.col("order_ts").str.to_datetime(format=ISO_FORMAT, strict=False).alias("parsed")
    )
    assert probe["parsed"].null_count() == DAY_FIRST_TIMESTAMPS == 771


def test_no_timestamp_is_parsed_leniently_into_the_wrong_date(orders: pl.DataFrame) -> None:
    """The defect must be a hard parse failure, not a quiet misreading.

    Two things are asserted. Every day-first row fails the ISO format outright,
    so the failing count equals the day-first count exactly and nothing slips
    through as a plausible wrong date. And enough day-first rows carry a day
    above 12 that reading them as month-first is impossible rather than merely
    unlikely, which is what makes the two formats genuinely distinguishable.
    """
    day_first_rows = orders.filter(pl.col("order_ts").str.contains("/"))
    assert day_first_rows.height == DAY_FIRST_TIMESTAMPS

    # Not one of them is readable as ISO.
    assert (
        day_first_rows.select(
            pl.col("order_ts").str.to_datetime(format=ISO_FORMAT, strict=False)
        )
        .to_series()
        .null_count()
        == day_first_rows.height
    )

    # And the day component is unambiguous on a real share of them.
    unambiguous = day_first_rows.filter(
        pl.col("order_ts").str.slice(0, 2).cast(pl.Int32) > 12
    )
    assert unambiguous.height > 300, (
        f"only {unambiguous.height} day-first rows have a day above 12; "
        "the two formats are not reliably distinguishable"
    )


def test_every_order_falls_in_calendar_year_2025(orders: pl.DataFrame) -> None:
    parsed = orders.select(
        pl.coalesce(
            pl.col("order_ts").str.to_datetime(format=ISO_FORMAT, strict=False),
            pl.col("order_ts").str.to_datetime(format=DAY_FIRST_FORMAT, strict=False),
        ).alias("ts")
    )["ts"]

    assert parsed.min() is not None
    assert parsed.dt.year().min() == 2025
    assert parsed.dt.year().max() == 2025
