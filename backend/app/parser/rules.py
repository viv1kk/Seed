"""The parser rules table from ``docs/02-ARCHITECTURE.md``, as code.

That table is authoritative. This module implements exactly it and holds no
opinions of its own, so that reading one next to the other is enough to check
the parser is right.
"""

import re
from typing import Final

from app.core.agents import DEFAULT_AGENT, ROSTER
from app.core.types import AgentId

# `Agent: <name>` and `Depends on: 1.2, 1.3`, matched case-insensitively and
# anchored to a line so they cannot be picked up mid-sentence.
AGENT_LINE: Final[re.Pattern[str]] = re.compile(r"^\s*Agent:\s*(.+?)\s*$", re.IGNORECASE)
DEPENDS_LINE: Final[re.Pattern[str]] = re.compile(r"^\s*Depends on:\s*(.+?)\s*$", re.IGNORECASE)

# A leading enumerator on a heading, as in "### 1.1 Define the schema contract"
# or "## Phase 1: Design". Ids and phase numbers are derived from document
# order, so the number in the text is a human convenience that would otherwise
# be shown twice.
TASK_NUMBER_PREFIX: Final[re.Pattern[str]] = re.compile(r"^\d+(?:\.\d+)*[.):]?\s+")
PHASE_NUMBER_PREFIX: Final[re.Pattern[str]] = re.compile(
    r"^(?:phase\s+)?\d+\s*[.):-]?\s+", re.IGNORECASE
)

# A task id as it appears in a `Depends on:` line.
TASK_ID: Final[re.Pattern[str]] = re.compile(r"^\d+\.\d+$")


def match_agent_name(name: str) -> AgentId | None:
    """Resolve an explicit ``Agent:`` value against the roster.

    Both the id and the display name are accepted, case-insensitively, so
    "etl", "ETL Engineer" and "ETL ENGINEER" all land on the same agent.
    """
    needle = name.strip().casefold()
    for profile in ROSTER:
        if needle in {profile.id.casefold(), profile.display_name.casefold()}:
            return profile.id
    return None


def infer_agent(text: str) -> AgentId | None:
    """Assign by capability keyword when a task carries no ``Agent:`` line.

    Returns None when the answer is ambiguous, meaning no keyword matched or two
    agents tied. The caller falls back to the Architect and records a warning;
    guessing between a tie would be worse than saying so.
    """
    haystack = text.casefold()
    scores = {
        profile.id: sum(1 for keyword in profile.keywords if keyword in haystack)
        for profile in ROSTER
    }
    best = max(scores.values())
    if best == 0:
        return None

    winners = [agent_id for agent_id, score in scores.items() if score == best]
    if len(winners) != 1:
        return None
    return winners[0]


def strip_task_number(heading: str) -> str:
    """"1.1 Define the schema contract" -> "Define the schema contract"."""
    stripped = TASK_NUMBER_PREFIX.sub("", heading).strip()
    return stripped or heading.strip()


def strip_phase_number(heading: str) -> str:
    """"Phase 1: Design" -> "Design"."""
    stripped = PHASE_NUMBER_PREFIX.sub("", heading).strip()
    stripped = stripped.removeprefix(":").strip()
    return stripped or heading.strip()


def parse_dependency_ids(value: str) -> list[str]:
    """Split a ``Depends on:`` value, keeping document order and dropping repeats.

    Ids that are not shaped like a task id are returned as they were written, so
    that the caller can report them as unknown rather than silently ignoring a
    typo.
    """
    seen: list[str] = []
    for raw in value.split(","):
        candidate = raw.strip()
        if candidate and candidate not in seen:
            seen.append(candidate)
    return seen


def looks_like_task_id(value: str) -> bool:
    return bool(TASK_ID.match(value))


__all__ = [
    "AGENT_LINE",
    "DEFAULT_AGENT",
    "DEPENDS_LINE",
    "infer_agent",
    "looks_like_task_id",
    "match_agent_name",
    "parse_dependency_ids",
    "strip_phase_number",
    "strip_task_number",
]
