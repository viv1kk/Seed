"""The agent roster, from ``docs/04-AGENT-RUNTIME.md``.

Four agents, no more. Two agents working at once reads as parallel; four reads
as noise, which is why ``MAX_PARALLEL`` is 2 and why this list is short.

This lives in ``core`` rather than in ``parser`` or ``runners`` because both
need it and neither should import the other. The parser matches an ``Agent:``
line against it, and from phase 2 the runners are keyed by it.

``keywords`` are capability keywords, used only when a task carries no
``Agent:`` line. See ``parser/rules.py`` for how the fallback resolves.
"""

from dataclasses import dataclass
from typing import Final

from app.core.types import AgentId


@dataclass(frozen=True)
class AgentProfile:
    id: AgentId
    display_name: str
    keywords: tuple[str, ...]


ROSTER: Final[tuple[AgentProfile, ...]] = (
    AgentProfile(
        id="architect",
        display_name="Architect",
        keywords=("plan", "design", "schema", "contract", "review", "verify"),
    ),
    AgentProfile(
        id="etl",
        display_name="ETL Engineer",
        keywords=("ingest", "extract", "load", "clean", "source", "csv", "quality"),
    ),
    AgentProfile(
        id="analytics",
        display_name="Analytics Engineer",
        keywords=("transform", "join", "aggregate", "metric", "model", "kpi"),
    ),
    AgentProfile(
        id="dashboard",
        display_name="Dashboard Engineer",
        keywords=("dashboard", "chart", "visual", "report", "ui"),
    ),
)

BY_ID: Final[dict[AgentId, AgentProfile]] = {profile.id: profile for profile in ROSTER}

# The agent a task falls back to when nothing else resolves it. The Architect
# owns design and review, so an unclassifiable task landing there is the least
# surprising outcome.
DEFAULT_AGENT: Final[AgentId] = "architect"


def display_name(agent_id: AgentId) -> str:
    return BY_ID[agent_id].display_name
