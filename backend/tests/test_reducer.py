"""The phase 0 gate, Python half.

Replays each fixture through the pure reducer and asserts the hand-written
terminal state. frontend/src/state/replay.test.ts does the same over the same
files, and the two must agree.
"""

from typing import Any

import pytest

from app.core.reducer import apply_event, apply_events, initial_state, summarise
from app.core.types import RunStarted, SeedEvent
from tests.conftest import FIXTURE_FILES, EventFixture, load_fixture


def test_fixture_replays_to_its_expected_state(event_fixture: EventFixture) -> None:
    state = apply_events(initial_state(), event_fixture.events)
    assert summarise(state) == event_fixture.expected, event_fixture.label


def test_ten_event_gate_fixture_is_exactly_ten_events() -> None:
    # The gate in docs/07-IMPLEMENTATION-PLAN.md says ten. If this file grows,
    # add a new fixture rather than widening this one.
    assert len(load_fixture("phase0_events.json").events) == 10


def test_the_retry_beat_happens_exactly_once() -> None:
    """The failure and retry is the demo's spine. Assert it directly."""
    fixture = load_fixture("phase0_events.json")
    state = apply_events(initial_state(), fixture.events)

    assert state.retry_count == 1
    assert state.task_attempts["1.1"] == 2
    assert state.task_status["1.1"] == "completed"


def test_a_recoverable_failure_reads_as_retrying_not_failed() -> None:
    """Contract rule 4. A node awaiting its retry must not look dead."""
    fixture = load_fixture("phase0_events.json")
    up_to_failure = [event for event in fixture.events if event.seq <= 6]
    state = apply_events(initial_state(), up_to_failure)

    assert state.task_status["1.1"] == "retrying"


def test_apply_event_does_not_mutate_the_state_it_is_given() -> None:
    before = apply_events(initial_state(), load_fixture("phase0_events.json").events)
    snapshot = summarise(before)

    apply_event(
        before,
        RunStarted(run_id="other", seq=99, at=0, requirement_title="x", seed=1, speed=1),
    )

    assert summarise(before) == snapshot


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_fixture_seq_numbers_are_monotonic_from_zero(filename: str) -> None:
    """Contract rule 1. A fixture that breaks it is not a valid run."""
    events = load_fixture(filename).events
    assert [event.seq for event in events] == list(range(len(events)))


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_fixture_simulated_time_never_goes_backwards(filename: str) -> None:
    ats = [event.at for event in load_fixture(filename).events]
    assert ats == sorted(ats)


def test_every_event_variant_is_covered_by_the_fixtures() -> None:
    """A new event type must arrive with a fixture that exercises it.

    The Python reducer fails to compile against an unhandled variant only via
    assert_never at type-check time; this catches the case where the variant is
    handled but never actually replayed.
    """
    seen: set[str] = set()
    for filename in FIXTURE_FILES:
        for event in load_fixture(filename).events:
            seen.add(event.type)

    declared = {
        variant.model_fields["type"].default
        for variant in SeedEvent.__origin__.__args__  # type: ignore[attr-defined]
    }
    assert seen == declared


def test_summarise_keys_are_snake_case() -> None:
    """The TypeScript summarise() deliberately emits these same keys.

    See the note at the top of frontend/src/state/summarise.ts. Renaming one
    here without renaming it there breaks the parity net silently, because both
    sides would still pass their own half.
    """
    summary: dict[str, Any] = summarise(initial_state())
    assert all(key == key.lower() and " " not in key for key in summary)
    assert not any("-" in key for key in summary)
