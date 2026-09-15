"""The five aggregations the dashboard draws, computed in one pass.

Run once at the end of the pipeline and again on every cross-filter, over the
same derived frame. A filtered bundle and an unfiltered one come out of the same
code, which is what makes brushing a date range on the dashboard a real query
rather than a second, parallel implementation that has to be kept honest.

## What counts as revenue

Two policy decisions live here, and only here. ``transform.py`` describes every
row; this module decides which rows are money.

**Cancelled orders are excluded.** Nothing was sold and nothing was returned.
They are out of every figure including the return rate, which measures returns
against orders that actually completed the sale.

**Returns are counted separately, not folded into revenue.** A returned order
carries a negative quantity, so letting it through would quietly net it off the
revenue total and there would be no way to see how much had been returned. So
every revenue measure is taken over completed orders, and returns appear as the
return rate instead.

The consequence is the property the requirement document asks for: revenue by
region and revenue by category are the same total sliced two ways, and both sum
to the headline net revenue. If they ever do not, the pipeline is wrong.

## A dimension chart is not filtered by itself

Filtering the category chart by the selected category would leave it showing one
bar, which is the only value it could still draw. That breaks the interaction it
exists for: the point of clicking a category is to see the rest of the dashboard
under it *while still seeing the other categories*, so the selection reads as one
bar among its peers and the next one is a click away.

So the category cut is computed with every active filter except the category,
and the region cut with every filter except the region. Everything else, the
headline, the weekly series and the top products, takes all of them. This is the
ordinary cross-filter semantic, and with nothing selected it changes nothing:
the excluded filter is absent, so both cuts still sum to the headline.

One consequence to keep in mind when reading a filtered bundle: with a category
selected, ``revenue_by_category`` no longer sums to ``kpis.net_revenue``, and
``revenue_by_region``'s shares are shares of the region cut's own total rather
than of the headline. That is what makes the percentages answer "of the revenue
this chart is showing", which is the question a share label is asked.

## Why every group_by passes maintain_order=True

Polars does not promise an order from a grouped result. Without the flag the
rows come back in whatever order the hash table produced, which can differ
between runs of the same data, and then the top-ten table and the category chart
reshuffle for no reason anybody can reproduce. Sorting afterwards does not fix
it either, because ties break on the incoming order. The flag costs very little
on a frame this size and it is the difference between a run that can be diffed
against the last one and a run that cannot.
"""

import time
from datetime import date
from typing import Final

import polars as pl

from app.core.types import (
    AggBundle,
    CategoryRow,
    Filters,
    Kpis,
    ProductRow,
    RegionRow,
    WeekPoint,
)

# The status that means money changed hands and stayed changed.
REVENUE_STATUS: Final[str] = "completed"
RETURNED_STATUS: Final[str] = "returned"

TOP_PRODUCT_LIMIT: Final[int] = 10


def _as_date(value: str | None) -> date | None:
    """An ISO date from the query string, or None if it is absent or unreadable.

    A filter nobody can parse is dropped rather than raised on. The dashboard
    sends these from a brush interaction, and the worst outcome of a malformed
    one should be an unfiltered chart, not a failed request in front of an
    audience.
    """
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def apply_filters(frame: pl.DataFrame, filters: Filters) -> pl.DataFrame:
    """Narrow the derived frame to what the dashboard asked for.

    Both date bounds are inclusive, which is what someone brushing a chart
    means: the week they dragged to is the week they expect to see.
    """
    date_from = _as_date(filters.date_from)
    if date_from is not None:
        frame = frame.filter(pl.col("order_date") >= date_from)

    date_to = _as_date(filters.date_to)
    if date_to is not None:
        frame = frame.filter(pl.col("order_date") <= date_to)

    if filters.category:
        frame = frame.filter(pl.col("category") == filters.category)

    if filters.region:
        frame = frame.filter(pl.col("region") == filters.region)

    return frame


def _ratio(numerator: float, denominator: float) -> float:
    """Guarded division. An empty filter selection is a real thing to ask for."""
    return numerator / denominator if denominator else 0.0


def _kpis(revenue: pl.DataFrame, returned_count: int) -> Kpis:
    net_revenue = float(revenue["net_revenue"].sum())
    margin = float(revenue["margin"].sum())
    order_count = revenue.height

    return Kpis(
        net_revenue=net_revenue,
        order_count=order_count,
        average_order_value=_ratio(net_revenue, order_count),
        # Weighted by revenue, not an average of the per-order percentages. The
        # mean of a ratio is not the ratio of the means, and the second is the
        # one finance is asking about.
        margin_pct=_ratio(margin, net_revenue),
        return_rate=_ratio(returned_count, order_count + returned_count),
    )


def _revenue_over_time(revenue: pl.DataFrame) -> list[WeekPoint]:
    weekly = (
        revenue.group_by("order_week", maintain_order=True)
        .agg(
            pl.col("net_revenue").sum().alias("net_revenue"),
            pl.len().alias("order_count"),
        )
        .sort("order_week")
    )
    return [
        WeekPoint(
            week=row["order_week"].isoformat(),
            net_revenue=float(row["net_revenue"]),
            order_count=int(row["order_count"]),
        )
        for row in weekly.iter_rows(named=True)
    ]


def _revenue_by_category(revenue: pl.DataFrame) -> list[CategoryRow]:
    by_category = (
        revenue.group_by("category", maintain_order=True)
        .agg(
            pl.col("net_revenue").sum().alias("net_revenue"),
            pl.col("margin").sum().alias("margin"),
        )
        # The category name is a secondary sort key so that two categories with
        # identical revenue cannot swap places between runs.
        .sort(["net_revenue", "category"], descending=[True, False])
    )
    return [
        CategoryRow(
            category=str(row["category"]),
            net_revenue=float(row["net_revenue"]),
            margin_pct=_ratio(float(row["margin"]), float(row["net_revenue"])),
        )
        for row in by_category.iter_rows(named=True)
    ]


def _revenue_rows(frame: pl.DataFrame, filters: Filters) -> pl.DataFrame:
    """The rows that count as revenue under a given set of filters."""
    return apply_filters(frame, filters).filter(pl.col("status") == REVENUE_STATUS)


def _released(filters: Filters, field: str) -> Filters:
    """The same filters with one dimension let go. See the module docstring."""
    return filters.model_copy(update={field: None})


def _revenue_by_region(revenue: pl.DataFrame, total: float) -> list[RegionRow]:
    by_region = (
        revenue.group_by("region", maintain_order=True)
        .agg(pl.col("net_revenue").sum().alias("net_revenue"))
        .sort(["net_revenue", "region"], descending=[True, False])
    )
    return [
        RegionRow(
            region=str(row["region"]),
            net_revenue=float(row["net_revenue"]),
            share=_ratio(float(row["net_revenue"]), total),
        )
        for row in by_region.iter_rows(named=True)
    ]


def _top_products(revenue: pl.DataFrame) -> list[ProductRow]:
    by_sku = (
        revenue.group_by("sku", maintain_order=True)
        .agg(
            pl.col("product_name").first().alias("product_name"),
            pl.col("net_revenue").sum().alias("net_revenue"),
            pl.col("margin").sum().alias("margin"),
            pl.col("qty").sum().alias("units"),
        )
        .sort(["net_revenue", "sku"], descending=[True, False])
        .head(TOP_PRODUCT_LIMIT)
    )
    return [
        ProductRow(
            sku=str(row["sku"]),
            product_name=str(row["product_name"]),
            net_revenue=float(row["net_revenue"]),
            units=int(row["units"]),
            margin_pct=_ratio(float(row["margin"]), float(row["net_revenue"])),
        )
        for row in by_sku.iter_rows(named=True)
    ]


def aggregate(frame: pl.DataFrame, filters: Filters | None = None) -> AggBundle:
    """Compute every dashboard surface from one derived frame.

    ``rows`` on the bundle is the row count the filters admitted, before the
    revenue statuses narrow it further. It answers "how much of the dataset am I
    looking at", which is a different and more useful question than the order
    count inside the headline figures.
    """
    started = time.perf_counter()
    active = filters or Filters()

    selected = apply_filters(frame, active)
    revenue = selected.filter(pl.col("status") == REVENUE_STATUS)
    returned_count = selected.filter(pl.col("status") == RETURNED_STATUS).height

    kpis = _kpis(revenue, returned_count)

    # Each dimension chart drops its own filter, so it keeps every value and the
    # selected one reads as a bar among its peers. With that dimension
    # unselected these are the same frame, and the extra pass does not run.
    by_category = (
        revenue
        if active.category is None
        else _revenue_rows(frame, _released(active, "category"))
    )
    by_region = (
        revenue if active.region is None else _revenue_rows(frame, _released(active, "region"))
    )
    region_total = (
        kpis.net_revenue
        if active.region is None
        else float(by_region["net_revenue"].sum())
    )

    return AggBundle(
        kpis=kpis,
        revenue_over_time=_revenue_over_time(revenue),
        revenue_by_category=_revenue_by_category(by_category),
        revenue_by_region=_revenue_by_region(by_region, region_total),
        top_products=_top_products(revenue),
        rows=selected.height,
        computed_ms=round((time.perf_counter() - started) * 1000),
        filters=active,
    )
