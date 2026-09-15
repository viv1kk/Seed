"""The closing document: every criterion from the requirement, with its result.

This is the most client-legible thing the run produces, and it is the one
artifact whose job is to be sceptical about the rest. It walks the acceptance
criteria the requirement document actually contains, puts the measured value
beside each, and names anything that missed.

Two kinds of line appear under a criterion.

**Checked.** A criterion that can be settled by arithmetic over figures the
pipeline measured, such as whether the dropped rows came in under the budget or
whether revenue by region sums to the headline total. These carry a verdict.

**Recorded.** A criterion that is a judgement rather than a calculation, such as
whether the dashboard layout follows from the contract. These carry the figures
that bear on it and no verdict, because asserting one would be the document
lying about how much it knows.

The distinction is the point. A verification note that marked everything green
would be worth nothing, and the one thing worse than a criterion that failed is
a report that hides it.
"""

from dataclasses import dataclass, field
from typing import Final

from app.core.types import Plan

Facts = dict[str, float | int | str]

# Fact keys, written by the agent that measured them and read here. Named once
# so that a typo is a failure to find the fact rather than a silently missing
# line in the finished document.
ROWS_IN: Final = "rows_in"
ROWS_CLEAN: Final = "rows_clean"
ROWS_DROPPED: Final = "rows_dropped"
DROP_BUDGET: Final = "drop_budget_rows"
DUPLICATES: Final = "duplicates_removed"
QTY_COERCED: Final = "qty_coerced"
DISCOUNT_NULL_RATE: Final = "discount_null_rate"
TIMESTAMP_FAILURES: Final = "timestamp_failures"
CONTRACT_COLUMNS: Final = "contract_columns"
SOURCE_COUNT: Final = "source_count"
PRODUCTS_MATCHED: Final = "products_matched"
PRODUCTS_UNMATCHED: Final = "products_unmatched"
CUSTOMERS_UNMATCHED: Final = "customers_unmatched"
REGION_CONFLICTS: Final = "region_conflicts"
DERIVED_ROWS: Final = "derived_rows"
NET_REVENUE: Final = "net_revenue"
ORDER_COUNT: Final = "order_count"
MARGIN_PCT: Final = "margin_pct"
RETURN_RATE: Final = "return_rate"
CATEGORY_TOTAL: Final = "category_total"
REGION_TOTAL: Final = "region_total"
CATEGORY_GROUPS: Final = "category_groups"
WEEK_POINTS: Final = "week_points"
TOP_PRODUCTS: Final = "top_products"
DASHBOARD_SURFACES: Final = "dashboard_surfaces"

# Two sums of the same money, in rupees. They are computed from the same column
# of the same frame, so anything above a fraction of a paisa is a real defect
# rather than float noise.
MONEY_TOLERANCE: Final[float] = 0.01


@dataclass(frozen=True)
class Check:
    """One line under a criterion. ``passed`` is None when nothing was asserted."""

    task_id: str
    label: str
    measured: str
    passed: bool | None = None

    @property
    def verdict(self) -> str:
        if self.passed is None:
            return "recorded"
        return "met" if self.passed else "MISSED"


@dataclass
class CheckReport:
    checks: list[Check] = field(default_factory=list)
    facts: Facts = field(default_factory=dict)

    def for_task(self, task_id: str) -> list[Check]:
        return [check for check in self.checks if check.task_id == task_id]

    @property
    def asserted(self) -> int:
        return sum(1 for check in self.checks if check.passed is not None)

    @property
    def passed(self) -> int:
        return sum(1 for check in self.checks if check.passed is True)

    @property
    def failed(self) -> int:
        return sum(1 for check in self.checks if check.passed is False)

    @property
    def recorded(self) -> int:
        return sum(1 for check in self.checks if check.passed is None)


def _number(facts: Facts, key: str) -> float:
    value = facts.get(key, 0)
    return float(value) if isinstance(value, int | float) else 0.0


def run_checks(facts: Facts) -> CheckReport:
    """Settle what can be settled from the figures the run measured."""
    report = CheckReport(facts=dict(facts))
    add = report.checks.append

    if CONTRACT_COLUMNS in facts:
        add(
            Check(
                task_id="1.1",
                label="The contract names every column the sources carry",
                measured=(
                    f"{_number(facts, CONTRACT_COLUMNS):,.0f} columns recorded across "
                    f"{_number(facts, SOURCE_COUNT):,.0f} sources"
                ),
            )
        )

    rows_in = _number(facts, ROWS_IN)
    dropped = _number(facts, ROWS_DROPPED)
    budget = _number(facts, DROP_BUDGET)

    if rows_in:
        add(
            Check(
                task_id="2.1",
                label="Dropped rows stay inside the drop budget",
                measured=(
                    f"{dropped:,.0f} dropped of {rows_in:,.0f} read "
                    f"({dropped / rows_in * 100:.2f}%), budget {budget:,.0f} rows"
                ),
                passed=dropped <= budget,
            )
        )
        add(
            Check(
                task_id="2.1",
                label="No row dropped for a timestamp any reasonable rule can parse",
                measured=(
                    f"{_number(facts, TIMESTAMP_FAILURES):,.0f} rows unparseable "
                    "after the two-format pass"
                ),
                passed=_number(facts, TIMESTAMP_FAILURES) == 0,
            )
        )
        add(
            Check(
                # The criterion belongs to 1.2, which set the rules. The counts
                # come from 2.1, which applied them. The document is organised
                # by criterion, so the check goes where the criterion is.
                task_id="1.2",
                label="Every rule applied was applied with a count",
                measured=(
                    f"{_number(facts, DUPLICATES):,.0f} duplicates removed, "
                    f"{_number(facts, QTY_COERCED):,.0f} qty values coerced, "
                    f"discount null rate {_number(facts, DISCOUNT_NULL_RATE) * 100:.2f}%"
                ),
            )
        )

    if PRODUCTS_MATCHED in facts:
        add(
            Check(
                task_id="2.3",
                label="Every order line matches a product",
                measured=(
                    f"{_number(facts, PRODUCTS_MATCHED):,.0f} matched, "
                    f"{_number(facts, PRODUCTS_UNMATCHED):,.0f} unmatched"
                ),
                passed=_number(facts, PRODUCTS_UNMATCHED) == 0,
            )
        )
        add(
            Check(
                task_id="2.3",
                label="Region disagreements between order and customer are resolved and counted",
                measured=(
                    f"{_number(facts, REGION_CONFLICTS):,.0f} rows disagreed, "
                    "resolved in favour of the order-level region"
                ),
            )
        )

    net_revenue = _number(facts, NET_REVENUE)
    if NET_REVENUE in facts:
        for label, key in (
            ("Revenue by category sums to total net revenue", CATEGORY_TOTAL),
            ("Revenue by region sums to total net revenue", REGION_TOTAL),
        ):
            total = _number(facts, key)
            add(
                Check(
                    task_id="2.3",
                    label=label,
                    measured=f"{total:,.2f} against a headline of {net_revenue:,.2f}",
                    passed=abs(total - net_revenue) < MONEY_TOLERANCE,
                )
            )
        add(
            Check(
                task_id="2.3",
                label="Headline figures computed",
                measured=(
                    f"net revenue {net_revenue:,.2f}, "
                    f"{_number(facts, ORDER_COUNT):,.0f} orders, "
                    f"margin {_number(facts, MARGIN_PCT) * 100:.1f}%, "
                    f"return rate {_number(facts, RETURN_RATE) * 100:.1f}%"
                ),
            )
        )

    add(
        Check(
            task_id="3.2",
            label="Anything that failed is named rather than hidden",
            measured=(
                f"{sum(1 for c in report.checks if c.passed is False)} of "
                f"{sum(1 for c in report.checks if c.passed is not None)} checked criteria "
                "missed, each listed in place and again at the top"
            ),
        )
    )

    if DASHBOARD_SURFACES in facts:
        add(
            Check(
                task_id="3.1",
                label="Every surface is bound to a computed aggregate",
                measured=(
                    f"{_number(facts, DASHBOARD_SURFACES):,.0f} surfaces over "
                    f"{_number(facts, WEEK_POINTS):,.0f} weekly points, "
                    f"{_number(facts, CATEGORY_GROUPS):,.0f} categories, "
                    f"{_number(facts, TOP_PRODUCTS):,.0f} products"
                ),
            )
        )

    return report


def render(plan: Plan, report: CheckReport) -> str:
    """The verification document, walking the plan's own criteria in order."""
    lines = [
        "# Verification",
        "",
        f"Requirement: {plan.title}",
        "",
        "Every `>` criterion in the requirement document is restated below with what was "
        f"measured against it. {report.asserted} of them could be settled by arithmetic over "
        "figures the pipeline produced, and those carry a verdict. The rest carry the numbers "
        "that bear on them and no verdict, because asserting one would overstate what this "
        "check knows.",
        "",
    ]

    if report.failed:
        lines += [
            f"**{report.failed} criteria were not met.** They are listed here first and again "
            "in place below.",
            "",
        ]
        lines += [
            f"- {check.task_id}: {check.label}. {check.measured}"
            for check in report.checks
            if check.passed is False
        ]
        lines.append("")
    else:
        lines += [
            f"All {report.asserted} checked criteria were met. Nothing was hidden to get there: "
            "the criteria that could not be checked are named as unchecked.",
            "",
        ]

    for phase in plan.phases:
        lines += [f"## Phase {phase.index}. {phase.title}", ""]
        for task_id in phase.task_ids:
            task = plan.tasks.get(task_id)
            if task is None:
                continue
            lines += [f"### {task.id} {task.title}", ""]
            if not task.acceptance:
                lines += ["No acceptance criterion was written for this task.", ""]
            for criterion in task.acceptance:
                lines += [f"> {criterion}", ""]
            checks = report.for_task(task_id)
            if checks:
                lines += [
                    f"- **{check.verdict}**, {check.label}: {check.measured}" for check in checks
                ]
            else:
                lines.append("- No figure from this run bears on the criterion directly.")
            lines.append("")

    lines += ["## Figures recorded during the run", "", "| figure | value |", "| --- | ---: |"]
    for key, value in report.facts.items():
        lines.append(f"| {key} | {_format_fact(value)} |")
    lines.append("")

    return "\n".join(lines)


def _format_fact(value: float | int | str) -> str:
    if isinstance(value, bool | str):
        return str(value)
    if isinstance(value, int):
        return f"{value:,}"
    return f"{value:,.4f}"
