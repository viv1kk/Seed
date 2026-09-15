"""The Analytics Engineer's script: joins, derived money, and the aggregates.

Task 2.3 does the arithmetic the whole dashboard rests on, so its narration is
almost entirely numbers. Two details are worth pointing at during a demo.

The match rate is stated before the join is trusted. "Expecting 1:1, will
verify" is a real habit and the verification is a real count, so if the products
extract ever loses a sku the log says so in the same breath as the join.

The region disagreement is reported rather than resolved quietly. The two
extracts disagree on a few hundred rows, the order-level value wins, and the
count of rows that disagreed goes on the log and into the verification note.
"""

from collections.abc import Sequence
from typing import Final

from app.core.types import AgentId, AggBundle, TaskMetrics
from app.pipeline.kernel import WorkKernel, metrics_json
from app.pipeline.results import ConflictResult, DeriveResult, JoinResult
from app.runners.scripts import artifacts, verification
from app.runners.scripts.beats import Beat, BeatCtx, Emit, Pause, Say, Work

AGENT: Final[AgentId] = "analytics"


def build_metrics() -> Sequence[Beat]:
    """Task 2.3. Join, resolve, derive, aggregate."""
    return [
        Say(lambda c: f"Task {c.task.id}. Joining orders to products on sku. Expecting 1:1, "
            "and I will verify rather than assume."),
        Work("join-products", lambda k, _: k.join("orders", "products", "sku")),
        Say(lambda c: _join_line(c, "join-products", "products", "sku"), runtime=True),
        Say(lambda c: _match_line(c, "join-products")),
        Work("join-customers", lambda k, _: k.join("orders", "customers", "customer_id")),
        Say(lambda c: _join_line(c, "join-customers", "customers", "customer_id"), runtime=True),
        Say(lambda _: "Both extracts carry a region. They will not always agree."),
        Work("region", lambda k, _: k.resolve_conflict("orders", "region", "region_right")),
        Say(lambda c: _conflict_line(c), level="warn", when=_has_conflicts),
        Say(lambda c: _no_conflict_line(c), when=lambda c: not _has_conflicts(c)),
        Emit(lambda c: artifacts.code(c, "pipeline/transform.py", AGENT), stream=True),
        Say(lambda _: "Deriving the money columns from the formulas in the document."),
        Work("derive", lambda k, _: k.derive("orders")),
        Say(lambda c: _derive_line(c), runtime=True),
        Emit(lambda c: artifacts.dataset(c, "data/orders_enriched", "orders", AGENT)),
        Pause(600),
        Say(lambda _: "Aggregating. Cancelled orders are out, returns are counted separately."),
        Emit(lambda c: artifacts.code(c, "pipeline/aggregate.py", AGENT), stream=True),
        Work("aggregate", lambda k, _: k.aggregate("orders")),
        Say(lambda c: _aggregate_line(c), runtime=True),
        Say(lambda c: _headline_line(c)),
        Say(lambda c: _balance_line(c), level="success"),
        Emit(
            lambda c: artifacts.written(
                c, "analytics/metrics.json", metrics_json(_bundle(c)), AGENT, kind="table"
            )
        ),
        Work("record", _record),
    ]


def _bundle(ctx: BeatCtx) -> AggBundle:
    return ctx.get("aggregate", AggBundle)


def _has_conflicts(ctx: BeatCtx) -> bool:
    return ctx.get("region", ConflictResult).conflicts > 0


def _join_line(ctx: BeatCtx, step: str, right: str, key: str) -> str:
    result = ctx.get(step, JoinResult)
    return (
        f"join: orders x {right} on {key} -> {result.rows:,} rows, "
        f"{result.matched:,} matched, {result.unmatched:,} unmatched, {result.join_ms}ms"
    )


def _match_line(ctx: BeatCtx, step: str) -> str:
    result = ctx.get(step, JoinResult)
    total = result.matched + result.unmatched
    if result.unmatched == 0:
        return f"Every one of the {total:,} order lines found its product. The join is clean."
    return (
        f"{result.unmatched:,} order lines have no product behind them. "
        "That is a gap in the catalogue extract, not in the join."
    )


def _conflict_line(ctx: BeatCtx) -> str:
    result = ctx.get("region", ConflictResult)
    rate = result.conflicts / result.rows * 100 if result.rows else 0.0
    return (
        f"Order and customer disagree on region for {result.conflicts:,} rows, {rate:.1f}%. "
        "Taking the order-level value: it says where the sale happened."
    )


def _no_conflict_line(ctx: BeatCtx) -> str:
    result = ctx.get("region", ConflictResult)
    return f"Region agrees on all {result.rows:,} rows. Nothing to resolve."


def _derive_line(ctx: BeatCtx) -> str:
    result = ctx.get("derive", DeriveResult)
    return (
        f"derive: {len(result.columns_added)} columns over {result.rows:,} rows "
        f"({', '.join(result.columns_added)}), {result.derive_ms}ms"
    )


def _aggregate_line(ctx: BeatCtx) -> str:
    bundle = _bundle(ctx)
    return (
        f"aggregate: {len(bundle.revenue_over_time)} weeks, "
        f"{len(bundle.revenue_by_category)} categories, "
        f"{len(bundle.revenue_by_region)} regions, "
        f"{len(bundle.top_products)} top products, {bundle.computed_ms}ms"
    )


def _headline_line(ctx: BeatCtx) -> str:
    kpis = _bundle(ctx).kpis
    return (
        f"Net revenue {kpis.net_revenue:,.0f} over {kpis.order_count:,} completed orders. "
        f"Margin {kpis.margin_pct * 100:.1f}%, return rate {kpis.return_rate * 100:.1f}%."
    )


def _balance_line(ctx: BeatCtx) -> str:
    """The acceptance criterion from the document, checked out loud.

    Both totals are summed here from the bundle that is about to be handed to
    the dashboard, so the line is a check rather than a claim.
    """
    bundle = _bundle(ctx)
    by_category = sum(row.net_revenue for row in bundle.revenue_by_category)
    by_region = sum(row.net_revenue for row in bundle.revenue_by_region)
    headline = bundle.kpis.net_revenue
    if (
        abs(by_category - headline) < verification.MONEY_TOLERANCE
        and abs(by_region - headline) < verification.MONEY_TOLERANCE
    ):
        return (
            f"Category and region both sum to {headline:,.2f}, matching the headline. "
            "The cuts agree with the total."
        )
    return (
        f"The cuts do not reconcile: category {by_category:,.2f}, region {by_region:,.2f}, "
        f"headline {headline:,.2f}. That is a defect and it goes in the verification."
    )


def _record(kernel: WorkKernel, ctx: BeatCtx) -> None:
    """File the task metrics and everything the verification pass restates.

    Nothing here recomputes a figure. Every number is read back out of a result
    an earlier Work beat already filed, which is what keeps the verification
    document a restatement of the run rather than a second opinion about it.
    """
    bundle = _bundle(ctx)
    kpis = bundle.kpis
    products = ctx.get("join-products", JoinResult)
    customers = ctx.get("join-customers", JoinResult)
    region = ctx.get("region", ConflictResult)
    derived = ctx.get("derive", DeriveResult)

    kernel.record_metrics(
        ctx.task.id,
        TaskMetrics(
            rows_in=derived.rows,
            rows_out=derived.rows,
            columns_added=derived.columns_added,
            duration_ms=0,  # The orchestrator owns the duration and overwrites this.
        ),
    )

    note = kernel.note
    note(verification.PRODUCTS_MATCHED, products.matched)
    note(verification.PRODUCTS_UNMATCHED, products.unmatched)
    note(verification.CUSTOMERS_UNMATCHED, customers.unmatched)
    note(verification.REGION_CONFLICTS, region.conflicts)
    note(verification.DERIVED_ROWS, derived.rows)
    note(verification.NET_REVENUE, kpis.net_revenue)
    note(verification.ORDER_COUNT, kpis.order_count)
    note(verification.MARGIN_PCT, kpis.margin_pct)
    note(verification.RETURN_RATE, kpis.return_rate)
    note(verification.CATEGORY_TOTAL, sum(row.net_revenue for row in bundle.revenue_by_category))
    note(verification.REGION_TOTAL, sum(row.net_revenue for row in bundle.revenue_by_region))
    note(verification.CATEGORY_GROUPS, len(bundle.revenue_by_category))
    note(verification.WEEK_POINTS, len(bundle.revenue_over_time))
    note(verification.TOP_PRODUCTS, len(bundle.top_products))
