"""The work kernel: the seam between narration and real work.

``WorkKernel`` is the interface a runner is allowed to use. Every number a log
line or a metric carries has to come back from one of these calls, so that no
figure on screen was written into a string by hand.

Phase 2 ships ``StubKernel`` and nothing else. Phase 3 puts the real Polars
pipeline behind the same interface, and no runner, orchestrator or API changes.
"""

from typing import Protocol

from app.core.types import Artifact
from app.pipeline.results import (
    CleanResult,
    CleanStrategy,
    DeriveResult,
    JoinResult,
    LoadResult,
    ProfileResult,
)


class WorkKernel(Protocol):
    """What a runner may ask the pipeline to do.

    ``DataFrame`` arguments are absent in phase 2 because the stub holds no
    frames. Phase 3 threads a ``pl.DataFrame`` through these, keyed by the
    dataset name the runner already passes.
    """

    def load_csv(self, name: str) -> LoadResult: ...

    def profile(self, name: str) -> ProfileResult: ...

    def clean(self, name: str, strategy: CleanStrategy) -> CleanResult: ...

    def join(self, left: str, right: str, on: str) -> JoinResult: ...

    def derive(self, name: str) -> DeriveResult: ...

    def emit_artifact(self, artifact: Artifact) -> None: ...

    @property
    def artifacts(self) -> dict[str, Artifact]: ...
