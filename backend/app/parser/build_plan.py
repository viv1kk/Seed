"""Blocks to a Plan: phases, tasks, dependencies, and a topological order.

Errors are returned, never raised. A requirement document is user input, and a
broken `Depends on:` reference is an ordinary thing for a person to write. The
API renders the errors and refuses the run; it does not surface a traceback.

The plan is derived from the document and from nothing else. Editing a `###`
heading changes the graph, because there is no other source for it.
"""

import hashlib
from dataclasses import dataclass, field

from app.core.agents import DEFAULT_AGENT
from app.core.types import (
    AgentId,
    Constraint,
    ParseError,
    ParseFailed,
    ParseResult,
    ParseSucceeded,
    ParseWarning,
    Phase,
    Plan,
    Task,
    TaskStep,
)
from app.parser import rules
from app.parser.lexer import Block, Bullet, Fence, Heading, Paragraph, Quote, lex

UNTITLED = "Untitled requirement"


@dataclass
class _DraftTask:
    """A task under construction, before dependencies are resolved."""

    id: str
    phase_id: str
    title: str
    explicit_agent: AgentId | None = None
    unmatched_agent: str | None = None
    declared_dependencies: list[str] | None = None
    steps: list[TaskStep] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)
    acceptance: list[str] = field(default_factory=list)


@dataclass
class _DraftPhase:
    id: str
    index: int
    title: str
    task_ids: list[str] = field(default_factory=list)


def build_plan(markdown: str, plan_id: str | None = None) -> ParseResult:
    blocks = lex(markdown)

    title, phases, tasks, errors, warnings = _collect(blocks)

    if not tasks and not errors:
        errors.append(
            ParseError(
                code="no-tasks",
                message=(
                    "No tasks found. A task is a level 3 heading inside a level 2 phase."
                ),
            )
        )

    resolved = _resolve_dependencies(phases, tasks, errors, warnings)

    order: list[str] = []
    if not errors:
        order = _topological_order(phases, resolved, errors)

    if errors:
        return ParseFailed(errors=errors, warnings=warnings)

    return ParseSucceeded(
        plan=Plan(
            id=plan_id or _derive_plan_id(markdown),
            title=title,
            source_markdown=markdown,
            phases=[Phase(id=p.id, index=p.index, title=p.title, task_ids=p.task_ids)
                    for p in phases],
            tasks=resolved,
            order=order,
            warnings=warnings,
        )
    )


# ---------------------------------------------------------------- collection


def _collect(
    blocks: list[Block],
) -> tuple[str, list[_DraftPhase], dict[str, _DraftTask], list[ParseError], list[ParseWarning]]:
    title = UNTITLED
    phases: list[_DraftPhase] = []
    tasks: dict[str, _DraftTask] = {}
    errors: list[ParseError] = []
    warnings: list[ParseWarning] = []

    phase: _DraftPhase | None = None
    task: _DraftTask | None = None

    for block in blocks:
        match block:
            case Heading(level=1, text=text):
                if title == UNTITLED:
                    title = text
                # Content outside any phase is prose. It is ignored for
                # planning and still reaches the UI via source_markdown.
                phase = None
                task = None

            case Heading(level=2, text=text):
                phase = _DraftPhase(
                    id=str(len(phases) + 1),
                    index=len(phases) + 1,
                    title=rules.strip_phase_number(text),
                )
                phases.append(phase)
                task = None

            case Heading(level=3, text=text):
                if phase is None:
                    errors.append(
                        ParseError(
                            code="task-outside-phase",
                            message=(
                                f"Task {text!r} appears before any phase. "
                                "Put it under a level 2 phase heading."
                            ),
                        )
                    )
                    task = None
                    continue
                task_id = f"{phase.index}.{len(phase.task_ids) + 1}"
                task = _DraftTask(
                    id=task_id,
                    phase_id=phase.id,
                    title=rules.strip_task_number(text),
                )
                phase.task_ids.append(task_id)
                tasks[task_id] = task

            case Heading():
                # Level 4 and deeper carry no planning meaning.
                continue

            case Paragraph(text=text) if task is not None:
                _read_directives(task, text)

            case Bullet(text=text) if task is not None:
                task.steps.append(
                    TaskStep(id=f"{task.id}.{len(task.steps) + 1}", text=text)
                )

            case Fence(lang=lang, code=code) if task is not None:
                task.constraints.append(Constraint(lang=lang, code=code))

            case Quote(text=text) if task is not None:
                task.acceptance.append(text)

            case _:
                continue

    return title, phases, tasks, errors, warnings


def _read_directives(task: _DraftTask, paragraph: str) -> None:
    """Pull `Agent:` and `Depends on:` out of a paragraph, line by line.

    They usually share one paragraph, separated by a soft break, so the whole
    paragraph cannot be tested as a single string.
    """
    for line in paragraph.splitlines():
        if (match := rules.AGENT_LINE.match(line)) is not None:
            name = match.group(1)
            resolved = rules.match_agent_name(name)
            if resolved is None:
                task.unmatched_agent = name
            else:
                task.explicit_agent = resolved
            continue

        if (match := rules.DEPENDS_LINE.match(line)) is not None:
            task.declared_dependencies = rules.parse_dependency_ids(match.group(1))


# ---------------------------------------------------------------- dependencies


def _resolve_dependencies(
    phases: list[_DraftPhase],
    drafts: dict[str, _DraftTask],
    errors: list[ParseError],
    warnings: list[ParseWarning],
) -> dict[str, Task]:
    tasks: dict[str, Task] = {}
    tasks_by_phase_index = {phase.index: phase.task_ids for phase in phases}

    for draft in drafts.values():
        agent_id = _resolve_agent(draft, warnings)
        depends_on = _resolve_task_dependencies(
            draft, drafts, tasks_by_phase_index, errors, warnings
        )

        if not draft.steps:
            warnings.append(
                ParseWarning(
                    code="empty-task",
                    task_id=draft.id,
                    message=(
                        f"Task {draft.id} has no steps. Progress for it will be "
                        "reported in one jump."
                    ),
                )
            )

        tasks[draft.id] = Task(
            id=draft.id,
            phase_id=draft.phase_id,
            title=draft.title,
            agent_id=agent_id,
            depends_on=depends_on,
            steps=draft.steps,
            constraints=draft.constraints,
            acceptance=draft.acceptance,
        )

    return tasks


def _resolve_agent(draft: _DraftTask, warnings: list[ParseWarning]) -> AgentId:
    if draft.explicit_agent is not None:
        return draft.explicit_agent

    if draft.unmatched_agent is not None:
        warnings.append(
            ParseWarning(
                code="unassigned-agent",
                task_id=draft.id,
                message=(
                    f"No agent named {draft.unmatched_agent!r} is on the roster. "
                    f"Task {draft.id} went to the Architect."
                ),
            )
        )
        return DEFAULT_AGENT

    # No Agent: line. Match on capability keywords over everything the task says.
    haystack = " ".join([draft.title, *(step.text for step in draft.steps)])
    inferred = rules.infer_agent(haystack)
    if inferred is not None:
        return inferred

    warnings.append(
        ParseWarning(
            code="unassigned-agent",
            task_id=draft.id,
            message=(
                f"Task {draft.id} has no Agent line and no clear keyword match. "
                "It went to the Architect."
            ),
        )
    )
    return DEFAULT_AGENT


def _resolve_task_dependencies(
    draft: _DraftTask,
    drafts: dict[str, _DraftTask],
    tasks_by_phase_index: dict[int, list[str]],
    errors: list[ParseError],
    warnings: list[ParseWarning],
) -> list[str]:
    if draft.declared_dependencies is None:
        return _implicit_dependencies(draft, tasks_by_phase_index, warnings)

    resolved: list[str] = []
    for dependency in draft.declared_dependencies:
        if dependency == draft.id:
            errors.append(
                ParseError(
                    code="self-dependency",
                    task_id=draft.id,
                    message=f"Task {draft.id} depends on itself.",
                )
            )
            continue
        if dependency not in drafts:
            errors.append(
                ParseError(
                    code="unknown-dependency",
                    task_id=draft.id,
                    message=(
                        f"Task {draft.id} depends on {dependency!r}, which is not a "
                        "task in this document."
                    ),
                )
            )
            continue
        resolved.append(dependency)
    return resolved


def _implicit_dependencies(
    draft: _DraftTask,
    tasks_by_phase_index: dict[int, list[str]],
    warnings: list[ParseWarning],
) -> list[str]:
    """No `Depends on:` line means every task in the previous phase."""
    previous_index = int(draft.phase_id) - 1
    previous = tasks_by_phase_index.get(previous_index, [])
    if not previous:
        # Nothing to depend on, so nothing was assumed and there is nothing to
        # warn about. A first-phase task with no dependencies is just correct.
        return []

    warnings.append(
        ParseWarning(
            code="implicit-dependency",
            task_id=draft.id,
            message=(
                f"Task {draft.id} has no Depends on line. It was given every task "
                f"in phase {previous_index}: {', '.join(previous)}."
            ),
        )
    )
    return list(previous)


# ---------------------------------------------------------------- ordering


def _topological_order(
    phases: list[_DraftPhase],
    tasks: dict[str, Task],
    errors: list[ParseError],
) -> list[str]:
    """Kahn's algorithm, in document order, with cycle detection.

    Ready tasks are taken in document order rather than from a set, so the same
    document always produces the same order. The orchestrator schedules off this
    and two runs at one seed have to agree.
    """
    document_order = [task_id for phase in phases for task_id in phase.task_ids]
    remaining = {task_id: set(tasks[task_id].depends_on) for task_id in document_order}
    ordered: list[str] = []

    while remaining:
        ready = [task_id for task_id in document_order
                 if task_id in remaining and not remaining[task_id]]
        if not ready:
            errors.append(_cycle_error(remaining, document_order))
            return []

        for task_id in ready:
            ordered.append(task_id)
            del remaining[task_id]
        for dependencies in remaining.values():
            dependencies.difference_update(ready)

    return ordered


def _cycle_error(
    remaining: dict[str, set[str]],
    document_order: list[str],
) -> ParseError:
    """Name the tasks actually in the loop, not everything stuck behind it.

    When a cycle forms, every task downstream of it also becomes unorderable. A
    message listing all of them tells someone their whole document is broken and
    leaves them to find the two headings that are really at fault. So the loop
    members are separated out, and the rest are counted rather than named.
    """
    in_cycle = sorted(
        (task_id for task_id in document_order if _reaches_itself(task_id, remaining)),
        key=document_order.index,
    )
    blocked = len(remaining) - len(in_cycle)

    if not in_cycle:  # pragma: no cover - a stall always has a loop behind it
        return ParseError(
            code="dependency-cycle",
            message=f"These tasks cannot be ordered: {', '.join(sorted(remaining))}.",
        )

    message = (
        f"{' and '.join(in_cycle) if len(in_cycle) == 2 else ', '.join(in_cycle)} "
        f"depend on each other in a loop. Remove one of the Depends on references "
        f"to break it."
    )
    if blocked:
        message += f" {blocked} further task{'s' if blocked != 1 else ''} wait behind it."
    return ParseError(code="dependency-cycle", message=message)


def _reaches_itself(start: str, remaining: dict[str, set[str]]) -> bool:
    """Whether following dependencies from a task leads back to that task."""
    seen: set[str] = set()
    stack = list(remaining.get(start, ()))
    while stack:
        current = stack.pop()
        if current == start:
            return True
        if current in seen or current not in remaining:
            continue
        seen.add(current)
        stack.extend(remaining[current])
    return False


def _derive_plan_id(markdown: str) -> str:
    """Stable for a given document, so reparsing the same text is idempotent."""
    digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    return f"plan_{digest[:12]}"
