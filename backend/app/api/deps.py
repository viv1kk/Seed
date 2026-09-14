"""Shared API dependencies.

One process, one registry, held in memory for the life of it. There is no
persistence in this project by design: a run is a live thing, and the demo
starts from a clean slate every time it is launched.
"""

from typing import Annotated

from fastapi import Depends

from app.core.registry import RunRegistry

_registry = RunRegistry()


def get_registry() -> RunRegistry:
    return _registry


Registry = Annotated[RunRegistry, Depends(get_registry)]
