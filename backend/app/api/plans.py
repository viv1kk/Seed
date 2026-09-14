"""Parse a requirement document into a plan.

A parse failure is a normal outcome, not an HTTP error: the document belongs to
the person using this, and a broken `Depends on:` reference is an ordinary thing
to write. So the endpoint answers 200 with a discriminated result the frontend
renders either way, and the run is refused by there being no plan id to start
one with. A 4xx here would push the frontend into an error path when what it
should do is show the person which line to fix.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, model_validator

from app.api.deps import Registry
from app.api.examples import load_example
from app.core.types import ParseResult
from app.parser import build_plan

router = APIRouter(prefix="/api", tags=["plans"])


class PlanRequest(BaseModel):
    """Either raw markdown or the id of a bundled example. Exactly one."""

    markdown: str | None = None
    example_id: str | None = None

    @model_validator(mode="after")
    def exactly_one_source(self) -> "PlanRequest":
        if (self.markdown is None) == (self.example_id is None):
            raise ValueError("Provide either markdown or example_id, not both and not neither.")
        return self


@router.post("/plans")
async def create_plan(request: PlanRequest, registry: Registry) -> ParseResult:
    if request.example_id is not None:
        markdown = load_example(request.example_id)
        if markdown is None:
            raise HTTPException(
                status_code=404, detail=f"No example with id {request.example_id!r}"
            )
    else:
        markdown = request.markdown or ""

    result = build_plan(markdown)

    # Retain successful plans so POST /api/runs can find one by id in phase 2.
    # A rejected document has nothing to retain, which is how the run is refused.
    if result.status == "ok":
        registry.put_plan(result.plan)

    return result
