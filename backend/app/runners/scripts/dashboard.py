"""The Dashboard Engineer's scripts: the layout, then the delivered dashboard.

Task 2.2 runs early, off the schema contract alone, which is why it is the task
that proves the graph is a graph: it sits beside the ETL work rather than after
it, because nothing about choosing a layout depends on the data being clean. Its
narration says so, and it deliberately does not quote a revenue figure, because
at that point in the run nobody has computed one.

Task 3.1 renders the layout against the metrics. Its code artifact is the real
dashboard component from the frontend, and the dashboard artifact itself carries
the bundle the browser is about to draw.
"""

import json
from collections.abc import Sequence
from typing import Final

from app.core.types import AgentId, AggBundle, Artifact, TaskMetrics
from app.pipeline.kernel import WorkKernel, metrics_json
from app.pipeline.results import ProfileResult
from app.runners.scripts import artifacts, verification
from app.runners.scripts.beats import Beat, BeatCtx, Emit, Pause, Say, Work

AGENT: Final[AgentId] = "dashboard"

# The five surfaces from the requirement document, in the order they appear on
# the page. The spec artifact is built from this and the layout is bound to it,
# so the two cannot drift apart without somebody editing both.
SURFACES = (
    ("headline", "Five headline figures", "kpis"),
    ("revenue_over_time", "Revenue over time, weekly", "area"),
    ("revenue_by_category", "Revenue by category, sorted", "bar-horizontal"),
    ("revenue_by_region", "Revenue by region, with share", "bar-vertical"),
    ("top_products", "Top ten products", "table"),
)


# ---------------------------------------------------------------- 2.2


def draft_layout() -> Sequence[Beat]:
    """Task 2.2. Choose the layout from the contract, before the data is clean."""
    return [
        Say(lambda c: f"Task {c.task.id}. Working from the schema contract, not from the data. "
            "The layout should not wait on the cleaning pass."),
        Work("profile", lambda k, _: k.profile("orders")),
        Say(lambda c: _columns_line(c)),
        Say(
            lambda _: "Finance opens on totals, so the headline figures go top left: "
            "net revenue, orders, average order value, margin, return rate."
        ),
        Say(
            lambda _: "Time gets a chart because the shape matters. The product list gets a "
            "table because the ranking matters and a bar chart of ten names is unreadable."
        ),
        Pause(800),
        Say(lambda _: _surfaces_line()),
        Emit(
            lambda c: artifacts.written(
                c, "dashboard/spec.json", _spec_text(c), AGENT, kind="code"
            ),
            stream=True,
        ),
        Say(
            lambda _: f"Layout drafted. {len(SURFACES)} surfaces, every one bound to an "
            "aggregate the analytics task has to produce.",
            level="success",
        ),
    ]


def _columns_line(ctx: BeatCtx) -> str:
    profile = ctx.get("profile", ProfileResult)
    return (
        f"The contract gives me {len(profile.columns)} source columns to work from. "
        "Nothing here needs the cleaned frame yet."
    )


def _surfaces_line() -> str:
    """Names the three cuts that get a chart. No measurement, so no context."""
    return "Cuts that earn a chart: " + ", ".join(label for _, label, _ in SURFACES[1:4]) + "."


def _spec_text(ctx: BeatCtx) -> str:
    """The layout spec, built from the surfaces and the task's own steps."""
    spec = {
        "requirement": ctx.plan.title,
        "task": ctx.task.id,
        "currency": {"locale": "en-IN", "code": "INR"},
        "surfaces": [
            {
                "id": surface_id,
                "title": label,
                "chart": chart,
                "source": surface_id if surface_id != "headline" else "kpis",
            }
            for surface_id, label, chart in SURFACES
        ],
        "interactions": [
            "brush the time axis",
            "click a category bar",
            "click a region bar",
        ],
        "derived_from": [step.text for step in ctx.task.steps],
    }
    return json.dumps(spec, indent=2)


# ---------------------------------------------------------------- 3.1


def render_dashboard() -> Sequence[Beat]:
    """Task 3.1. Bind the layout from 2.2 to the metrics from 2.3."""
    return [
        Say(lambda c: f"Task {c.task.id}. Binding the layout from 2.2 to the metrics from 2.3."),
        Work("bundle", lambda k, _: k.aggregate("orders")),
        Say(lambda c: _bound_line(c), runtime=True),
        Emit(lambda c: artifacts.code(c, "dashboard/RevenueDashboard.tsx", AGENT), stream=True),
        Say(lambda c: _headline_line(c)),
        Say(lambda c: _region_line(c)),
        Say(lambda c: _product_line(c)),
        Emit(lambda c: _dashboard_artifact(c)),
        Say(
            lambda c: f"Dashboard delivered. Every figure on it came from the "
            f"{_bundle(c).rows:,} rows the pipeline produced, and the filters query them live.",
            level="success",
        ),
        Work("record", _record),
    ]


def _bundle(ctx: BeatCtx) -> AggBundle:
    return ctx.get("bundle", AggBundle)


def _bound_line(ctx: BeatCtx) -> str:
    bundle = _bundle(ctx)
    return (
        f"bind: {len(SURFACES)} surfaces, {len(bundle.revenue_over_time)} weekly points, "
        f"{len(bundle.revenue_by_category)} categories, {len(bundle.revenue_by_region)} regions, "
        f"{bundle.computed_ms}ms"
    )


def _headline_line(ctx: BeatCtx) -> str:
    kpis = _bundle(ctx).kpis
    return (
        f"Headline reads {kpis.net_revenue:,.0f} net revenue, "
        f"average order value {kpis.average_order_value:,.0f}."
    )


def _region_line(ctx: BeatCtx) -> str:
    regions = _bundle(ctx).revenue_by_region
    if not regions:
        return "No region has any revenue under the current selection."
    top = regions[0]
    return (
        f"{top.region} leads the regions on {top.net_revenue:,.0f}, "
        f"{top.share * 100:.1f}% of the total."
    )


def _product_line(ctx: BeatCtx) -> str:
    products = _bundle(ctx).top_products
    if not products:
        return "No product has any revenue under the current selection."
    top = products[0]
    return (
        f"Top product is {top.product_name} at {top.net_revenue:,.0f} "
        f"on {top.units:,} units, margin {top.margin_pct * 100:.1f}%."
    )


def _dashboard_artifact(ctx: BeatCtx) -> Artifact:
    """The dashboard itself, carrying the bundle the browser will draw."""
    return artifacts.written(
        ctx, "dashboard", metrics_json(_bundle(ctx)), AGENT, kind="dashboard"
    )


def _record(kernel: WorkKernel, ctx: BeatCtx) -> None:
    bundle = _bundle(ctx)
    kernel.note(verification.DASHBOARD_SURFACES, len(SURFACES))
    kernel.record_metrics(
        ctx.task.id,
        TaskMetrics(rows_in=bundle.rows, rows_out=bundle.kpis.order_count, duration_ms=0),
    )
