"""The parser is real.

Every assertion here is about the plan being derived from the document and from
nothing else. If any of these could pass with a filename-keyed shortcut behind
them, the test is not pulling its weight.
"""

import textwrap
from pathlib import Path

import pytest

from app.core.types import ParseFailed, ParseSucceeded
from app.parser import build_plan
from app.parser.lexer import Bullet, Fence, Heading, Paragraph, Quote, lex

DEMO = (
    Path(__file__).resolve().parents[2] / "examples" / "requirements" / "retail-analytics.md"
)


def parse_ok(markdown: str) -> ParseSucceeded:
    result = build_plan(textwrap.dedent(markdown))
    assert isinstance(result, ParseSucceeded), getattr(result, "errors", None)
    return result


def parse_failed(markdown: str) -> ParseFailed:
    result = build_plan(textwrap.dedent(markdown))
    assert isinstance(result, ParseFailed), "expected the document to be refused"
    return result


# ---------------------------------------------------------------- lexer


def test_the_lexer_flattens_the_five_block_kinds() -> None:
    blocks = lex(
        textwrap.dedent(
            """
            # Title

            ## Phase

            ### Task

            Some prose.

            - a step

            ```python
            x = 1
            ```

            > an acceptance criterion
            """
        )
    )
    kinds = [type(block) for block in blocks]
    assert kinds == [Heading, Heading, Heading, Paragraph, Bullet, Fence, Quote]


def test_a_paragraph_keeps_its_soft_breaks() -> None:
    """Agent: and Depends on: share one paragraph, and both must survive."""
    blocks = lex("Agent: ETL Engineer\nDepends on: 1.1, 1.2\n")
    assert blocks == [Paragraph(text="Agent: ETL Engineer\nDepends on: 1.1, 1.2")]


def test_a_fence_keeps_its_language_tag() -> None:
    assert lex("```yaml\nkey: value\n```\n") == [Fence(lang="yaml", code="key: value\n")]


# ---------------------------------------------------------------- the demo document


@pytest.fixture(scope="module")
def demo() -> ParseSucceeded:
    result = build_plan(DEMO.read_text(encoding="utf-8"))
    assert isinstance(result, ParseSucceeded)
    return result


def test_the_demo_document_gives_three_phases_and_seven_tasks(demo: ParseSucceeded) -> None:
    assert [phase.title for phase in demo.plan.phases] == ["Design", "Build", "Deliver"]
    assert len(demo.plan.tasks) == 7
    assert sorted(demo.plan.tasks) == ["1.1", "1.2", "2.1", "2.2", "2.3", "3.1", "3.2"]


def test_the_demo_document_has_the_right_owners(demo: ParseSucceeded) -> None:
    owners = {task_id: task.agent_id for task_id, task in demo.plan.tasks.items()}
    assert owners == {
        "1.1": "architect",
        "1.2": "architect",
        "2.1": "etl",
        "2.2": "dashboard",
        "2.3": "analytics",
        "3.1": "dashboard",
        "3.2": "architect",
    }


def test_the_demo_document_has_the_right_dependencies(demo: ParseSucceeded) -> None:
    deps = {task_id: task.depends_on for task_id, task in demo.plan.tasks.items()}
    assert deps == {
        "1.1": [],
        "1.2": ["1.1"],
        "2.1": ["1.1", "1.2"],
        "2.2": ["1.1"],
        "2.3": ["2.1"],
        "3.1": ["2.2", "2.3"],
        "3.2": ["3.1"],
    }


def test_the_demo_document_parses_without_a_single_warning(demo: ParseSucceeded) -> None:
    """It is the reference document. It should need no interpretation."""
    assert demo.plan.warnings == []


def test_the_demo_document_keeps_steps_constraints_and_acceptance(
    demo: ParseSucceeded,
) -> None:
    task = demo.plan.tasks["2.1"]
    assert len(task.steps) == 6
    assert task.steps[0].text.startswith("Load all three source files")
    assert task.acceptance == [
        "All rows are retained except those the quality rules explicitly allow us to "
        "drop, and the dropped count stays inside the drop budget."
    ]
    assert demo.plan.tasks["1.1"].constraints[0].lang == "yaml"


def test_the_title_comes_from_the_level_one_heading(demo: ParseSucceeded) -> None:
    assert demo.plan.title == "Retail revenue analytics platform"


def test_the_source_markdown_is_returned_verbatim(demo: ParseSucceeded) -> None:
    """The UI renders the document beside the graph, so it must be unmodified."""
    assert demo.plan.source_markdown == DEMO.read_text(encoding="utf-8")


def test_the_order_is_a_valid_topological_sort(demo: ParseSucceeded) -> None:
    position = {task_id: index for index, task_id in enumerate(demo.plan.order)}
    assert len(position) == len(demo.plan.tasks)
    for task in demo.plan.tasks.values():
        for dependency in task.depends_on:
            assert position[dependency] < position[task.id], f"{task.id} before {dependency}"


def test_parsing_is_stable(demo: ParseSucceeded) -> None:
    """Same document, same plan id and same order. Runs must be reproducible."""
    again = build_plan(DEMO.read_text(encoding="utf-8"))
    assert isinstance(again, ParseSucceeded)
    assert again.plan == demo.plan


# ---------------------------------------------------------------- editing the document


def test_editing_a_task_heading_changes_the_plan() -> None:
    """The gate. The plan comes from the document, so this has to be true."""
    source = DEMO.read_text(encoding="utf-8")
    edited = source.replace(
        "### 2.1 Ingest and clean the order data",
        "### 2.1 Ingest and reconcile the order data",
    )
    assert edited != source

    before = build_plan(source)
    after = build_plan(edited)
    assert isinstance(before, ParseSucceeded)
    assert isinstance(after, ParseSucceeded)

    assert before.plan.tasks["2.1"].title == "Ingest and clean the order data"
    assert after.plan.tasks["2.1"].title == "Ingest and reconcile the order data"


def test_adding_a_task_heading_extends_the_graph() -> None:
    plan = parse_ok(
        """
        # T

        ## Phase one

        ### First

        Agent: Architect

        - do a thing

        ### Second

        Agent: ETL Engineer
        Depends on: 1.1

        - do another thing
        """
    ).plan
    assert plan.phases[0].task_ids == ["1.1", "1.2"]
    assert plan.tasks["1.2"].depends_on == ["1.1"]


# ---------------------------------------------------------------- ids and titles


def test_task_ids_come_from_position_not_from_the_heading_text() -> None:
    """A document that misnumbers itself still produces a coherent graph."""
    plan = parse_ok(
        """
        # T

        ## One

        ### 9.9 Mislabelled

        - step

        ## Two

        ### Also mislabelled

        - step
        """
    ).plan
    assert sorted(plan.tasks) == ["1.1", "2.1"]
    assert plan.tasks["1.1"].title == "Mislabelled"


def test_a_phase_keeps_its_name_without_the_numbering() -> None:
    plan = parse_ok(
        """
        # T

        ## Phase 2: Build

        ### A task

        - step
        """
    ).plan
    assert plan.phases[0].title == "Build"
    assert plan.phases[0].index == 1, "index is document order, not the number written"


# ---------------------------------------------------------------- agent assignment


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("Architect", "architect"),
        ("architect", "architect"),
        ("ETL Engineer", "etl"),
        ("etl engineer", "etl"),
        ("ETL ENGINEER", "etl"),
        ("etl", "etl"),
        ("Analytics Engineer", "analytics"),
        ("Dashboard Engineer", "dashboard"),
    ],
)
def test_an_agent_line_is_matched_case_insensitively(written: str, expected: str) -> None:
    plan = parse_ok(
        f"""
        # T

        ## P

        ### Task

        Agent: {written}

        - step
        """
    ).plan
    assert plan.tasks["1.1"].agent_id == expected


def test_an_unknown_agent_falls_back_with_a_warning() -> None:
    plan = parse_ok(
        """
        # T

        ## P

        ### Task

        Agent: Chief Vibes Officer

        - step
        """
    ).plan
    assert plan.tasks["1.1"].agent_id == "architect"
    assert [w.code for w in plan.warnings] == ["unassigned-agent"]
    assert "Chief Vibes Officer" in plan.warnings[0].message


def test_a_task_with_no_agent_line_is_assigned_by_keyword() -> None:
    plan = parse_ok(
        """
        # T

        ## P

        ### Load the source extracts

        - ingest the csv files and clean them
        """
    ).plan
    assert plan.tasks["1.1"].agent_id == "etl"
    assert plan.warnings == []


def test_an_ambiguous_task_goes_to_the_architect_with_a_warning() -> None:
    plan = parse_ok(
        """
        # T

        ## P

        ### Something else entirely

        - a step about nothing in particular
        """
    ).plan
    assert plan.tasks["1.1"].agent_id == "architect"
    assert [w.code for w in plan.warnings] == ["unassigned-agent"]


def test_a_keyword_tie_is_treated_as_ambiguous() -> None:
    """One keyword each from two agents. Guessing would be worse than saying so."""
    plan = parse_ok(
        """
        # T

        ## P

        ### Work

        - ingest the extract and build the chart
        """
    ).plan
    assert plan.tasks["1.1"].agent_id == "architect"
    assert [w.code for w in plan.warnings] == ["unassigned-agent"]


# ---------------------------------------------------------------- dependencies


def test_a_missing_depends_on_line_implies_the_previous_phase() -> None:
    plan = parse_ok(
        """
        # T

        ## One

        ### A

        Agent: Architect

        - step

        ### B

        Agent: Architect

        - step

        ## Two

        ### C

        Agent: ETL Engineer

        - step
        """
    ).plan
    assert plan.tasks["2.1"].depends_on == ["1.1", "1.2"]
    assert [w.code for w in plan.warnings] == ["implicit-dependency"]


def test_a_first_phase_task_with_no_dependencies_is_not_warned_about() -> None:
    """There is nothing to depend on, so nothing was assumed."""
    plan = parse_ok(
        """
        # T

        ## One

        ### A

        Agent: Architect

        - step
        """
    ).plan
    assert plan.tasks["1.1"].depends_on == []
    assert plan.warnings == []


def test_a_broken_dependency_reference_is_a_returned_error() -> None:
    """The gate: break a Depends on reference, see the error, run refused."""
    failed = parse_failed(
        """
        # T

        ## One

        ### A

        Agent: Architect

        - step

        ### B

        Agent: Architect
        Depends on: 1.7

        - step
        """
    )
    assert [e.code for e in failed.errors] == ["unknown-dependency"]
    assert failed.errors[0].task_id == "1.2"
    assert "1.7" in failed.errors[0].message


def test_a_cycle_is_caught_at_parse_time() -> None:
    failed = parse_failed(
        """
        # T

        ## One

        ### A

        Agent: Architect
        Depends on: 1.2

        - step

        ### B

        Agent: Architect
        Depends on: 1.1

        - step
        """
    )
    assert [e.code for e in failed.errors] == ["dependency-cycle"]
    assert "1.1 and 1.2" in failed.errors[0].message
    assert "Remove one of the Depends on references" in failed.errors[0].message


def test_a_cycle_message_names_the_loop_not_everything_behind_it() -> None:
    """A document is not "all broken" because two headings reference each other.

    Everything downstream of a cycle also becomes unorderable. Listing all of it
    buries the two tasks the person actually has to fix.
    """
    failed = parse_failed(
        """
        # T

        ## One

        ### A

        Agent: Architect
        Depends on: 1.2

        - step

        ### B

        Agent: Architect
        Depends on: 1.1

        - step

        ### C

        Agent: Architect
        Depends on: 1.1

        - step

        ### D

        Agent: Architect
        Depends on: 1.3

        - step
        """
    )
    message = failed.errors[0].message
    assert "1.1 and 1.2" in message
    assert "1.3" not in message, "tasks merely blocked by the loop should not be named"
    assert "2 further tasks wait behind it" in message


def test_a_self_dependency_is_an_error() -> None:
    failed = parse_failed(
        """
        # T

        ## One

        ### A

        Agent: Architect
        Depends on: 1.1

        - step
        """
    )
    assert [e.code for e in failed.errors] == ["self-dependency"]


def test_every_broken_reference_is_reported_not_just_the_first() -> None:
    """Fixing one at a time is a miserable way to repair a document."""
    failed = parse_failed(
        """
        # T

        ## One

        ### A

        Agent: Architect
        Depends on: 9.1

        - step

        ### B

        Agent: Architect
        Depends on: 9.2

        - step
        """
    )
    assert len(failed.errors) == 2


def test_errors_are_returned_rather_than_raised() -> None:
    """Parse failures are data. The API renders them; it does not 500."""
    result = build_plan("### Orphan task\n")
    assert isinstance(result, ParseFailed)
    assert [e.code for e in result.errors] == ["task-outside-phase"]


def test_a_document_with_no_tasks_is_refused() -> None:
    failed = parse_failed(
        """
        # Just some prose

        Nothing here describes any work.
        """
    )
    assert [e.code for e in failed.errors] == ["no-tasks"]


def test_a_task_with_no_steps_warns() -> None:
    plan = parse_ok(
        """
        # T

        ## P

        ### Empty

        Agent: Architect
        """
    ).plan
    assert "empty-task" in [w.code for w in plan.warnings]


def test_prose_outside_a_phase_is_ignored_for_planning() -> None:
    plan = parse_ok(
        """
        # T

        Some preamble that is not a task.

        - a bullet that belongs to nothing

        > a quote outside any task

        ## P

        ### A

        Agent: Architect

        - a real step
        """
    ).plan
    assert len(plan.tasks) == 1
    assert len(plan.tasks["1.1"].steps) == 1
