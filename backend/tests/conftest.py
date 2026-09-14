"""Shared fixture loading.

The fixture files are the contract's regression net and are read by the
TypeScript tests too, so the loader validates them against the Pydantic models
rather than trusting the JSON. A malformed fixture fails here first, with a
Pydantic error naming the field, instead of failing in Node with a type error
that is much harder to read.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from app.core.types import SeedEvent

FIXTURE_DIR = Path(__file__).parent / "fixtures"

_events_adapter = TypeAdapter(list[SeedEvent])


@dataclass(frozen=True)
class EventFixture:
    name: str
    description: str
    events: list[SeedEvent]
    expected: dict[str, Any]

    @property
    def label(self) -> str:
        return f"{self.name} ({self.description})"


def load_fixture(filename: str) -> EventFixture:
    raw = json.loads((FIXTURE_DIR / filename).read_text(encoding="utf-8"))
    return EventFixture(
        name=raw["name"],
        description=raw["description"],
        events=_events_adapter.validate_python(raw["events"]),
        expected=raw["expected"],
    )


FIXTURE_FILES = (
    "phase0_events.json",
    "phase0_events_full.json",
    "phase0_events_failed.json",
)


@pytest.fixture(params=FIXTURE_FILES)
def event_fixture(request: pytest.FixtureRequest) -> EventFixture:
    filename: str = request.param
    return load_fixture(filename)
