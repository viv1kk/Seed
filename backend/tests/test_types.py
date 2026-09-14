"""The frozen contract itself."""

import pytest
from pydantic import TypeAdapter, ValidationError

from app.core.types import SeedEvent, TaskCompleted, TaskMetrics

_adapter: TypeAdapter[SeedEvent] = TypeAdapter(SeedEvent)


def test_an_event_round_trips_through_json() -> None:
    event = TaskCompleted(
        run_id="r1",
        seq=3,
        at=100,
        task_id="1.1",
        agent_id="etl",
        metrics=TaskMetrics(rows_in=10, rows_out=9, duration_ms=5),
    )
    assert _adapter.validate_json(event.model_dump_json()) == event


def test_the_discriminator_selects_the_variant() -> None:
    parsed = _adapter.validate_python(
        {"type": "task.ready", "run_id": "r1", "seq": 1, "at": 2, "task_id": "1.1"}
    )
    assert parsed.type == "task.ready"


def test_an_unknown_event_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _adapter.validate_python({"type": "task.invented", "run_id": "r", "seq": 0, "at": 0})


def test_an_unknown_agent_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _adapter.validate_python(
            {"type": "agent.idle", "run_id": "r", "seq": 0, "at": 0, "agent_id": "designer"}
        )


def test_type_is_always_serialised_even_though_it_has_a_default() -> None:
    """The generated TypeScript declares `type` required on the strength of this.

    See _require_discriminants in scripts/export_schema.py. If Pydantic ever
    stopped emitting a defaulted field, the schema would be lying and the
    frontend union would stop discriminating.
    """
    dumped = TaskCompleted(
        run_id="r1", seq=0, at=0, task_id="1.1", agent_id="etl", metrics=TaskMetrics(duration_ms=1)
    ).model_dump()
    assert dumped["type"] == "task.completed"
