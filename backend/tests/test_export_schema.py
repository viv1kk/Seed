"""The exported schema is what the frontend types are generated from.

These assertions exist because the failure they guard against is silent. If the
discriminant stops being a required string literal, the generated union stops
discriminating, the store's exhaustive switch quietly accepts anything, and
assertNever stops catching unhandled events. Nothing breaks until a new event
type is ignored at runtime, in front of the client.
"""

from typing import Any

from app.core.types import SeedEvent
from scripts.export_schema import ROOTS, build_schema

EVENT_VARIANTS = SeedEvent.__origin__.__args__  # type: ignore[attr-defined]


def _definitions() -> dict[str, Any]:
    definitions: dict[str, Any] = build_schema()["definitions"]
    return definitions


def test_every_root_is_defined_and_referenced() -> None:
    schema = build_schema()
    for name in ROOTS:
        assert name in schema["definitions"]
        assert schema["properties"][name] == {"$ref": f"#/definitions/{name}"}


def test_the_union_lists_every_event_variant() -> None:
    union = _definitions()["SeedEvent"]
    refs = {option["$ref"] for option in union["oneOf"]}
    assert refs == {f"#/definitions/{variant.__name__}" for variant in EVENT_VARIANTS}


def test_the_union_carries_a_discriminator_on_type() -> None:
    union = _definitions()["SeedEvent"]
    assert union["discriminator"]["propertyName"] == "type"
    assert len(union["discriminator"]["mapping"]) == len(EVENT_VARIANTS)


def test_the_discriminant_is_a_required_const_on_every_variant() -> None:
    definitions = _definitions()
    for variant in EVENT_VARIANTS:
        definition = definitions[variant.__name__]
        assert "const" in definition["properties"]["type"], variant.__name__
        assert "type" in definition["required"], variant.__name__


def test_property_titles_are_stripped() -> None:
    """A titled property becomes a named alias in TypeScript, which hides the
    literal the union discriminates on. See _strip_property_titles."""
    for definition in _definitions().values():
        for name, prop in definition.get("properties", {}).items():
            assert "title" not in prop, name


def test_the_wire_stays_snake_case() -> None:
    """docs/03-EVENT-CONTRACT.md: no camelCase conversion layer, either side."""
    for definition in _definitions().values():
        for name in definition.get("properties", {}):
            assert name == name.lower(), name


def test_the_scalar_contract_types_are_exported_by_name() -> None:
    """The store needs TaskStatus by name, and it must come from Python."""
    definitions = _definitions()
    assert definitions["TaskStatus"]["enum"] == [
        "pending",
        "ready",
        "running",
        "retrying",
        "completed",
        "failed",
        "skipped",
    ]
    assert set(definitions["AgentId"]["enum"]) == {"architect", "etl", "analytics", "dashboard"}


def test_the_schema_is_stable_across_calls() -> None:
    """Regeneration must produce no diff, or the committed file churns."""
    assert build_schema() == build_schema()
