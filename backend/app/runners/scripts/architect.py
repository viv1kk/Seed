"""The Architect's scripts: the opening contract, the rules, the closing verify.

The Architect bookends the run. It reads the extracts before anyone writes code
so that the contract describes columns that exist, and it comes back at the end
to check the finished work against the criteria the document actually asked for.

Both documents it writes are generated at run time from real material: the
schema contract from the profiles of the three source files, and the
verification note from the acceptance criteria in the plan plus the figures
every other agent measured on the way past.
"""

from collections.abc import Sequence
from typing import Final

from app.core.types import AgentId
from app.pipeline.results import LoadResult, ProfileResult
from app.runners.scripts import artifacts, verification
from app.runners.scripts.beats import Beat, BeatCtx, Emit, Pause, Say, Work

AGENT: Final[AgentId] = "architect"

SOURCES = ("orders", "products", "customers")


# ---------------------------------------------------------------- 1.1


def schema_contract() -> Sequence[Beat]:
    """Task 1.1. Read all three extracts and agree the shape before any code."""
    return [
        Say(lambda c: _opening(c)),
        Say(lambda _: "Reading all three extracts first. I am not designing against a guess."),
        Work("load-orders", lambda k, _: k.load_csv("orders")),
        Work("load-products", lambda k, _: k.load_csv("products")),
        Work("load-customers", lambda k, _: k.load_csv("customers")),
        Say(lambda c: _sources_line(c), runtime=True),
        Work("profile-orders", lambda k, _: k.profile("orders")),
        Say(lambda c: _grain_line(c)),
        Say(
            lambda _: "Join keys follow from the constraint block: sku to products, "
            "customer_id to customers."
        ),
        Pause(700),
        Say(lambda _: "Writing the contract. Everything downstream refers back to it."),
        Emit(
            lambda c: artifacts.written(c, "design/schema_contract.md", _contract_text(c), AGENT),
            stream=True,
        ),
        Say(
            lambda c: f"Contract covers {_total_columns(c)} columns across three sources.",
            level="success",
        ),
    ]


def _opening(ctx: BeatCtx) -> str:
    plan = ctx.plan
    constrained = sum(1 for task in plan.tasks.values() if task.constraints)
    return (
        f"Reading the requirement. {len(plan.phases)} phases, {len(plan.tasks)} tasks, "
        f"{constrained} with explicit constraints."
    )


def _sources_line(ctx: BeatCtx) -> str:
    shapes = []
    for name in SOURCES:
        loaded = ctx.get(f"load-{name}", LoadResult)
        shapes.append(f"{name} {loaded.rows:,}x{len(loaded.columns)}")
    return "read_csv: " + ", ".join(shapes)


def _grain_line(ctx: BeatCtx) -> str:
    profile = ctx.get("profile-orders", ProfileResult)
    ids = next((c for c in profile.columns if c.name == "order_id"), None)
    if ids is None:
        return f"Orders profile: {len(profile.columns)} columns over {profile.rows:,} rows."
    repeats = profile.rows - ids.distinct
    if repeats == 0:
        return f"order_id is unique across all {profile.rows:,} rows. Grain confirmed."
    return (
        f"order_id is not unique: {profile.rows:,} rows, {ids.distinct:,} distinct. "
        f"{repeats} repeats to rule on before anyone joins to this."
    )


def _total_columns(ctx: BeatCtx) -> int:
    total = sum(len(ctx.get(f"load-{name}", LoadResult).columns) for name in SOURCES)
    ctx.kernel.note(verification.CONTRACT_COLUMNS, total)
    ctx.kernel.note(verification.SOURCE_COUNT, len(SOURCES))
    return total


def _contract_text(ctx: BeatCtx) -> str:
    """The schema contract, written from what the files actually contain."""
    profile = ctx.get("profile-orders", ProfileResult)
    lines = [
        "# Schema contract",
        "",
        f"Agreed for: {ctx.plan.title}",
        "",
        "Every column named here was read from the extract, not assumed. Nothing",
        "downstream may read a column that is not in this document.",
        "",
        "## Sources",
        "",
        "| source | rows | columns |",
        "| --- | ---: | ---: |",
    ]
    for name in SOURCES:
        loaded = ctx.get(f"load-{name}", LoadResult)
        lines.append(f"| {name}.csv | {loaded.rows:,} | {len(loaded.columns)} |")

    lines += ["", "## Columns present", ""]
    for name in SOURCES:
        loaded = ctx.get(f"load-{name}", LoadResult)
        lines.append(f"- **{name}**: {', '.join(loaded.columns)}")

    lines += [
        "",
        "## Orders, profiled",
        "",
        "| column | nulls | distinct | reads as |",
        "| --- | ---: | ---: | --- |",
    ]
    for column in profile.columns:
        formats = f" ({len(column.formats)} formats)" if column.formats else ""
        lines.append(
            f"| {column.name} | {column.nulls:,} | {column.distinct:,} "
            f"| {column.inferred_type}{formats} |"
        )

    lines += [
        "",
        "## Join keys",
        "",
        "- orders.sku -> products.sku",
        "- orders.customer_id -> customers.customer_id",
        "",
        "## Derived columns the analytical table must carry",
        "",
        "- gross_revenue, net_revenue, cogs, margin, margin_pct",
        "- order_date, order_week",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------- 1.2


def quality_rules() -> Sequence[Beat]:
    """Task 1.2. Decide in advance what happens to bad rows, with counts."""
    return [
        Say(lambda _: "Setting the quality rules now, before anyone is mid-pipeline."),
        Work("profile", lambda k, _: k.profile("orders")),
        Say(lambda c: _duplicate_rule(c)),
        Say(lambda c: _null_rule(c)),
        Say(lambda c: _timestamp_rule(c), runtime=True),
        Say(
            lambda _: "Normalisation target is UTC, and the drop budget is half a percent "
            "of input rows. Anything dropped gets counted against it."
        ),
        Say(
            lambda c: _budget_line(c),
            level="success",
        ),
    ]


def _duplicate_rule(ctx: BeatCtx) -> str:
    profile = ctx.get("profile", ProfileResult)
    ids = next((c for c in profile.columns if c.name == "order_id"), None)
    repeats = profile.rows - ids.distinct if ids else 0
    return (
        f"{repeats} duplicate order_id values in the extract. "
        "Rule: keep the most recent, log the count."
    )


def _null_rule(ctx: BeatCtx) -> str:
    profile = ctx.get("profile", ProfileResult)
    discount = next((c for c in profile.columns if c.name == "discount_pct"), None)
    if discount is None or not discount.nulls:
        return "No missing discounts in this extract. The rule still stands: treat as zero."
    rate = discount.nulls / profile.rows * 100
    return (
        f"discount_pct is empty on {discount.nulls:,} rows, {rate:.1f}%. "
        "Rule: treat as zero, report the rate."
    )


def _timestamp_rule(ctx: BeatCtx) -> str:
    profile = ctx.get("profile", ProfileResult)
    timestamps = next((c for c in profile.columns if c.name == "order_ts"), None)
    if timestamps is None or not timestamps.formats:
        return "profile: order_ts -> single format"
    shapes = ", ".join(timestamps.formats)
    return f"profile: order_ts -> {len(timestamps.formats)} formats present, {shapes}"


def _budget_line(ctx: BeatCtx) -> str:
    profile = ctx.get("profile", ProfileResult)
    budget = round(profile.rows * 0.005)
    ctx.kernel.note("drop_budget_rows", budget)
    return (
        f"Rules recorded. Drop budget is {budget} rows out of {profile.rows:,}. "
        "No row may be dropped for a timestamp we can parse by any reasonable rule."
    )


# ---------------------------------------------------------------- 3.2


def verify() -> Sequence[Beat]:
    """Task 3.2. Walk the document's criteria and record what was measured."""
    return [
        Say(lambda _: "Going back through the document, criterion by criterion."),
        Say(lambda c: _criteria_line(c)),
        Work("checks", lambda k, _: verification.run_checks(k.facts)),
        Say(lambda c: _checks_line(c), runtime=True),
        Say(_passed_line, level="success", when=lambda c: not _report(c).failed),
        Say(_failed_line, level="warn", when=lambda c: _report(c).failed > 0),
        Emit(
            lambda c: artifacts.written(c, "design/verification.md", _verification_text(c), AGENT),
            stream=True,
        ),
    ]


def _criteria_line(ctx: BeatCtx) -> str:
    total = sum(len(task.acceptance) for task in ctx.plan.tasks.values())
    return f"{total} acceptance criteria written across {len(ctx.plan.tasks)} tasks. Checking each."


def _checks_line(ctx: BeatCtx) -> str:
    report = ctx.get("checks", verification.CheckReport)
    return (
        f"verify: {report.asserted} criteria machine-checkable, "
        f"{report.passed} passed, {report.failed} failed"
    )


def _report(ctx: BeatCtx) -> verification.CheckReport:
    return ctx.get("checks", verification.CheckReport)


def _passed_line(ctx: BeatCtx) -> str:
    report = _report(ctx)
    return (
        f"All {report.asserted} machine-checkable criteria met. "
        f"{report.recorded} more are recorded with their measured values."
    )


def _failed_line(ctx: BeatCtx) -> str:
    report = _report(ctx)
    return (
        f"{report.failed} of {report.asserted} checks did not meet the criterion. "
        "They go in the document as failures, named."
    )


def _verification_text(ctx: BeatCtx) -> str:
    return verification.render(ctx.plan, _report(ctx))
