"""Liveness, and an honest statement of what this process is.

``mode`` is not decoration. Simulation Mode is disclosed in the UI, and the
value the badge reads comes from here rather than from a constant in the
frontend, so there is one source of truth for the claim.
"""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.version import VERSION


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    mode: Literal["simulation"]


router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=VERSION, mode="simulation")
