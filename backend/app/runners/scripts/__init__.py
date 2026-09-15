"""Which script runs for which task, and the fallback when none does.

A script is looked up by **document, agent and task id**, all three.

Each part earns its place. The task id alone is far too loose: every
requirement document has a task 1.1, and a logistics document would get the
retail schema contract narrated over it, naming three extracts it has never
heard of. The agent stops a reassigned task from being narrated by the wrong
voice. And the document title scopes the whole set to the requirement it was
written for.

Matching on the title rather than the plan id is deliberate. The plan id is a
hash of the markdown, so keying on it would drop every task to the generic
fallback the moment anybody edited a single heading, and editing a heading live
is the fifteen seconds that settles whether this is a recording. The title
survives that edit. Changing the ``#`` line is a different document, and a
different document should narrate itself.

Anything unmatched, a new task, a renamed requirement, a pasted file, runs on
the generic beats in ``simulated.py``, over the same bundled dataset and through
the same kernel. The demo is scripted; the platform is not limited to the
script.
"""

from collections.abc import AsyncIterator, Callable, Sequence
from typing import Final

from app.core.clock import Clock
from app.core.types import AgentId, Plan, SeedEvent
from app.runners.scripts import analytics, architect, dashboard, etl
from app.runners.scripts.beats import Beat, Performance, perform

# What the runner ultimately calls: a coroutine generator yielding events for one
# task. Beat-list scripts are wrapped into this shape by ``from_beats`` so the
# runner has exactly one thing to call, whether a task is narrated declaratively
# or, as with the ETL failure beat, imperatively.
Narration = Callable[[Performance, Clock], AsyncIterator[SeedEvent]]

# A beat list is static: it says what happens, never what the numbers are.
# Everything measured reaches a beat through ``BeatCtx`` when the beat runs, so
# building the list needs no context at all.
BeatBuilder = Callable[[], Sequence[Beat]]


def from_beats(build: BeatBuilder) -> Narration:
    """Wrap a beat list so it is callable like any other narration."""

    async def narrate(performance: Performance, clock: Clock) -> AsyncIterator[SeedEvent]:
        async for event in perform(build(), performance, clock):
            yield event

    return narrate


# The requirement document these scripts were written for, as it titles itself.
RETAIL: Final[str] = "retail revenue analytics platform"

SCRIPTS: Final[dict[tuple[str, AgentId, str], Narration]] = {
    (RETAIL, "architect", "1.1"): from_beats(architect.schema_contract),
    (RETAIL, "architect", "1.2"): from_beats(architect.quality_rules),
    (RETAIL, "etl", "2.1"): etl.ingest_and_clean,
    (RETAIL, "dashboard", "2.2"): from_beats(dashboard.draft_layout),
    (RETAIL, "analytics", "2.3"): from_beats(analytics.build_metrics),
    (RETAIL, "dashboard", "3.1"): from_beats(dashboard.render_dashboard),
    (RETAIL, "architect", "3.2"): from_beats(architect.verify),
}


def document_key(plan: Plan) -> str:
    """The plan title, normalised, so casing and stray spacing do not matter."""
    return " ".join(plan.title.split()).casefold()


def script_for(plan: Plan, agent_id: AgentId, task_id: str) -> Narration | None:
    return SCRIPTS.get((document_key(plan), agent_id, task_id))


__all__ = ["RETAIL", "SCRIPTS", "Narration", "document_key", "from_beats", "script_for"]
