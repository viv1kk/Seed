"""Export the frozen contract as one JSON Schema document, on stdout.

    uv run python -m scripts.export_schema > ../frontend/src/types/events.schema.json
    npm --prefix frontend run gen:types

The output is a single document with every model hoisted into ``$defs`` and a
top-level object referencing each root, because json-schema-to-typescript emits
an interface per reachable definition and names it from the key.

Two details are load-bearing:

* ``SeedEvent`` is an annotated union, not a model, so its ``oneOf`` is lifted
  into ``$defs`` by hand. Its ``discriminator`` is what makes the generated
  TypeScript a *discriminated* union, which is in turn what makes the store
  switch exhaustive and ``assertNever`` meaningful.
* the document is emitted as draft-07 with ``definitions`` as well as ``$defs``.
  Pydantic speaks 2020-12; json-schema-to-typescript is happiest on draft-07.
  Emitting both keeps one generator input valid for either reading.

Phase note: ``AggBundle`` joins ``ROOTS`` in phase 3, when the aggregations it
describes exist. Adding it here is the whole change on this side.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Final

from pydantic import TypeAdapter

from app.core.types import (
    AgentId,
    Artifact,
    ArtifactKind,
    LogLevel,
    Plan,
    SeedEvent,
    TaskStatus,
)

JsonObject = dict[str, Any]

# The roots the frontend needs names for. Everything they reference is pulled in
# automatically and named from its own model.
#
# The four scalar unions are here because Pydantic inlines a Literal rather than
# referencing it, so without an explicit root they exist in the output only as
# anonymous unions repeated inside each interface. TaskStatus in particular has
# no home on the wire at all: it is the vocabulary the store uses for a node's
# state, and it has to come from Python like everything else rather than being
# hand-written in TypeScript.
ROOTS: Final[dict[str, Any]] = {
    "SeedEvent": SeedEvent,
    "Plan": Plan,
    "Artifact": Artifact,
    "AgentId": AgentId,
    "TaskStatus": TaskStatus,
    "LogLevel": LogLevel,
    "ArtifactKind": ArtifactKind,
}

REF_TEMPLATE: Final[str] = "#/definitions/{model}"


def _strip_property_titles(node: object) -> None:
    """Drop the auto-generated ``title`` Pydantic puts on every property.

    Pydantic titles each property ("Run Id", "Task Id"), and the TypeScript
    generator turns any titled subschema into a named type alias. Left alone,
    the contract comes out as ``type?: Type``, ``run_id: RunId`` and eighty more
    aliases, and the string literal that discriminates the union disappears
    behind a name. Titles on the definitions themselves are kept; those are the
    model names and they are what the interfaces are called.
    """
    if isinstance(node, dict):
        for value in node.get("properties", {}).values():
            if isinstance(value, dict):
                value.pop("title", None)
        for value in node.values():
            _strip_property_titles(value)
    elif isinstance(node, list):
        for item in node:
            _strip_property_titles(item)


def _require_discriminants(definitions: JsonObject) -> None:
    """Mark the ``type`` discriminant required on every event variant.

    Pydantic leaves ``type`` out of ``required`` because it carries a default.
    That is wrong about the wire: ``model_dump`` always emits it, so every event
    that reaches the frontend has one. Correcting it here is what makes the
    generated union discriminated rather than a set of interfaces with an
    optional tag, which in turn is what makes the store switch exhaustive.
    """
    for definition in definitions.values():
        if not isinstance(definition, dict):
            continue
        discriminant = definition.get("properties", {}).get("type")
        if not isinstance(discriminant, dict) or "const" not in discriminant:
            continue
        required: list[str] = definition.setdefault("required", [])
        if "type" not in required:
            required.append("type")


def build_schema() -> JsonObject:
    definitions: JsonObject = {}

    for name, root in ROOTS.items():
        schema: JsonObject = TypeAdapter(root).json_schema(ref_template=REF_TEMPLATE)
        # Nested models land in $defs; merge them and keep the root under its
        # own name, so definitions["SeedEvent"] is the union and
        # definitions["Plan"] the object rather than either being inlined and
        # left unnamed.
        definitions.update(schema.pop("$defs", {}))
        definitions[name] = schema

    _strip_property_titles(definitions)
    _require_discriminants(definitions)

    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "SeedContract",
        "description": (
            "Generated from backend/app/core/types.py. "
            "See docs/03-EVENT-CONTRACT.md. Do not hand-edit the TypeScript."
        ),
        "type": "object",
        "additionalProperties": False,
        "properties": {name: {"$ref": REF_TEMPLATE.format(model=name)} for name in ROOTS},
        "required": list(ROOTS),
        "definitions": definitions,
    }


def render() -> str:
    return json.dumps(build_schema(), indent=2) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--out",
        type=Path,
        default=None,
        help=(
            "Write here instead of stdout, as UTF-8 with newline endings. "
            "Prefer this over a shell redirect: PowerShell writes a BOM, which "
            "the generator will not parse."
        ),
    )
    args = parser.parse_args(argv)
    schema = render()

    if args.out is None:
        sys.stdout.write(schema)
        return

    out: Path = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(schema, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
