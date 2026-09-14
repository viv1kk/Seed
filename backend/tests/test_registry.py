"""The in-memory run registry."""

import pytest

from app.core.registry import RunNotFoundError, RunRegistry


def test_create_run_assembles_bus_clock_and_rng_together() -> None:
    record = RunRegistry().create_run("plan_1", seed=42, speed=5)

    assert record.bus.run_id == record.run_id
    assert record.clock.speed == 5
    assert record.seed == 42


def test_run_ids_are_unique() -> None:
    registry = RunRegistry()
    ids = {registry.create_run("plan_1").run_id for _ in range(50)}
    assert len(ids) == 50


def test_the_same_seed_gives_two_runs_the_same_generator_state() -> None:
    registry = RunRegistry()
    first = registry.create_run("plan_1", seed=1337)
    second = registry.create_run("plan_1", seed=1337)
    assert first.rng.random() == second.rng.random()


def test_get_returns_none_for_an_unknown_run() -> None:
    assert RunRegistry().get("nope") is None


def test_require_raises_for_an_unknown_run() -> None:
    with pytest.raises(RunNotFoundError):
        RunRegistry().require("nope")


def test_list_runs_is_oldest_first() -> None:
    registry = RunRegistry()
    created = [registry.create_run(f"plan_{index}").run_id for index in range(4)]
    assert [record.run_id for record in registry.list_runs()] == created


def test_remove_is_forgiving_of_an_unknown_run() -> None:
    registry = RunRegistry()
    record = registry.create_run("plan_1")
    registry.remove(record.run_id)
    registry.remove(record.run_id)
    assert registry.get(record.run_id) is None
