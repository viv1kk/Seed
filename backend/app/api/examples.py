"""The bundled requirement documents.

These are ordinary markdown files on disk, not fixtures. The parser reads them
the same way it reads anything pasted in, which is what makes "edit a heading
and reload" a real demonstration rather than a trick.
"""

from pathlib import Path
from typing import Final

from fastapi import APIRouter, HTTPException

from app.core.types import ExampleSummary

# backend/app/api/examples.py -> backend/app/api -> backend/app -> backend -> repo root
EXAMPLES_DIR: Final[Path] = (
    Path(__file__).resolve().parents[3] / "examples" / "requirements"
)

router = APIRouter(prefix="/api", tags=["examples"])


def _title_of(markdown: str, fallback: str) -> str:
    """The first level 1 heading, which is the requirement title."""
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def list_examples() -> list[ExampleSummary]:
    """Sorted by id, so the order on screen is stable between reloads."""
    if not EXAMPLES_DIR.is_dir():
        return []
    return [
        ExampleSummary(
            id=path.stem,
            title=_title_of(path.read_text(encoding="utf-8"), path.stem),
        )
        for path in sorted(EXAMPLES_DIR.glob("*.md"))
    ]


def load_example(example_id: str) -> str | None:
    """Read one example, or None if there is no such id.

    The id is matched against the stems already on disk rather than joined onto
    the path, so a crafted id cannot reach outside the examples directory.
    """
    for path in sorted(EXAMPLES_DIR.glob("*.md")):
        if path.stem == example_id:
            return path.read_text(encoding="utf-8")
    return None


@router.get("/examples")
async def get_examples() -> list[ExampleSummary]:
    return list_examples()


@router.get("/examples/{example_id}")
async def get_example(example_id: str) -> ExampleSummary:
    markdown = load_example(example_id)
    if markdown is None:
        raise HTTPException(status_code=404, detail=f"No example with id {example_id!r}")
    return ExampleSummary(id=example_id, title=_title_of(markdown, example_id))
