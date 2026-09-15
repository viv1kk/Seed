"""The work kernel: the seam between narration and real work.

``WorkKernel`` is the interface a runner is allowed to use. Every number a log
line or a metric carries has to come back from one of these calls, so that no
figure on screen was written into a string by hand.

``PolarsKernel`` is the implementation. It is a thin, stateful facade over the
pure functions in this package: the functions take frames and return frames, and
the kernel remembers which frame is which so that a runner can refer to "orders"
across four tasks without carrying a DataFrame through the event contract.

Frames advance in place under their name. ``clean("orders", ...)`` replaces the
orders frame with the cleaned one, ``derive("orders")`` replaces it with the
derived one. That is what makes the failure beat work without any special
handling: the pure function raises before it returns anything, so the assignment
never happens and the frame the retry starts from is the one the first attempt
started from.

Nothing here knows that a simulation exists. The same kernel backs a future
``LlmRunner`` unchanged.
"""

import json
from typing import Protocol

import polars as pl

from app.core.types import AggBundle, Artifact, ArtifactBody, Filters, TaskMetrics
from app.pipeline import aggregate as aggregate_module
from app.pipeline import clean as clean_module
from app.pipeline import load as load_module
from app.pipeline import profile as profile_module
from app.pipeline import transform as transform_module
from app.pipeline.results import (
    CleanResult,
    CleanStrategy,
    ConflictResult,
    DatasetPreview,
    DeriveResult,
    FormatProbe,
    JoinResult,
    LoadResult,
    ProfileResult,
)

# Rows carried on a dataset artifact's preview. Twenty is what the artifacts
# panel shows, per docs/06-UI-SPEC.md.
PREVIEW_ROWS = 20


class WorkKernel(Protocol):
    """What a runner may ask the pipeline to do.

    Frames are addressed by name. The kernel holds them; the runner holds only
    the names it already knows from the requirement document.
    """

    def load_csv(self, name: str) -> LoadResult: ...

    def profile(self, name: str) -> ProfileResult: ...

    def probe_format(self, name: str, column: str, spec: str) -> FormatProbe: ...

    def clean(self, name: str, strategy: CleanStrategy) -> CleanResult: ...

    def join(self, left: str, right: str, on: str) -> JoinResult: ...

    def resolve_conflict(self, name: str, column: str, losing: str) -> ConflictResult: ...

    def derive(self, name: str) -> DeriveResult: ...

    def aggregate(self, name: str, filters: Filters | None = None) -> AggBundle: ...

    def preview(self, name: str) -> DatasetPreview: ...

    def emit_artifact(self, artifact: Artifact) -> None: ...

    def put_body(self, artifact_id: str, body: ArtifactBody) -> None: ...

    def body(self, artifact_id: str) -> ArtifactBody | None: ...

    def record_metrics(self, task_id: str, metrics: TaskMetrics) -> None: ...

    def metrics_for(self, task_id: str) -> TaskMetrics | None: ...

    def note(self, key: str, value: float | int | str) -> None: ...

    @property
    def facts(self) -> dict[str, float | int | str]: ...

    @property
    def artifacts(self) -> dict[str, Artifact]: ...

    @property
    def derived(self) -> pl.DataFrame | None: ...


class FrameNotLoadedError(KeyError):
    """Asked for a frame that no task has produced yet."""


class PolarsKernel:
    """The real pipeline, behind the kernel interface. One instance per run."""

    def __init__(self) -> None:
        self._frames: dict[str, pl.DataFrame] = {}
        self._artifacts: dict[str, Artifact] = {}
        self._bodies: dict[str, ArtifactBody] = {}
        self._metrics: dict[str, TaskMetrics] = {}
        self._facts: dict[str, float | int | str] = {}
        self._derived: pl.DataFrame | None = None

    # ------------------------------------------------------------ frames

    def frame(self, name: str) -> pl.DataFrame:
        try:
            return self._frames[name]
        except KeyError as exc:
            raise FrameNotLoadedError(name) from exc

    def load_csv(self, name: str) -> LoadResult:
        output = load_module.load_csv(name)
        self._frames[name] = output.frame
        return output.stats

    def profile(self, name: str) -> ProfileResult:
        return profile_module.profile(self.frame(name))

    def probe_format(self, name: str, column: str, spec: str) -> FormatProbe:
        return profile_module.probe_format(self.frame(name), column, spec)

    def clean(self, name: str, strategy: CleanStrategy) -> CleanResult:
        """Clean a frame in place under its name.

        Propagates whatever the pure function raises, which for the strict
        timestamp strategy against the real orders extract is
        ``polars.exceptions.InvalidOperationError``. The assignment below is not
        reached in that case, so a failed attempt leaves the frame untouched and
        a retry starts from the same place the first attempt did.
        """
        output = clean_module.clean(self.frame(name), strategy)
        self._frames[name] = output.frame
        return output.stats

    def join(self, left: str, right: str, on: str) -> JoinResult:
        output = transform_module.join(self.frame(left), self.frame(right), on)
        self._frames[left] = output.frame
        return output.stats

    def resolve_conflict(self, name: str, column: str, losing: str) -> ConflictResult:
        frame, conflicts = transform_module.resolve_conflict(
            self.frame(name), column, losing=losing
        )
        self._frames[name] = frame
        return ConflictResult(
            column=column, resolved_to=name, conflicts=conflicts, rows=frame.height
        )

    def derive(self, name: str) -> DeriveResult:
        """Add the money columns, and retain the result for the query endpoint.

        The derived frame is kept on the kernel after the run ends, which is
        what lets the dashboard keep cross-filtering once every agent has gone
        idle. It is the same frame the run computed its own figures from, so a
        filtered query cannot disagree with the delivered dashboard.
        """
        output = transform_module.derive(self.frame(name))
        self._frames[name] = output.frame
        self._derived = output.frame
        return output.stats

    def aggregate(self, name: str, filters: Filters | None = None) -> AggBundle:
        return aggregate_module.aggregate(self.frame(name), filters)

    def preview(self, name: str) -> DatasetPreview:
        """The head of a frame as strings, for a dataset artifact."""
        frame = self.frame(name)
        head = frame.head(PREVIEW_ROWS)
        return DatasetPreview(
            rows=frame.height,
            columns=frame.columns,
            bytes=int(frame.estimated_size()),
            sample=[[_cell(value) for value in row] for row in head.iter_rows()],
        )

    @property
    def derived(self) -> pl.DataFrame | None:
        return self._derived

    # ------------------------------------------------------------ artifacts

    @property
    def artifacts(self) -> dict[str, Artifact]:
        return self._artifacts

    def emit_artifact(self, artifact: Artifact) -> None:
        self._artifacts[artifact.id] = artifact

    def put_body(self, artifact_id: str, body: ArtifactBody) -> None:
        self._bodies[artifact_id] = body

    def body(self, artifact_id: str) -> ArtifactBody | None:
        return self._bodies.get(artifact_id)

    # ------------------------------------------------------------ bookkeeping

    def record_metrics(self, task_id: str, metrics: TaskMetrics) -> None:
        """Hand the orchestrator the numbers to put on ``task.completed``.

        The orchestrator owns the event and the duration; the runner owns the
        row counts, because it is the one that made the kernel calls. This is
        where the two meet without the orchestrator learning anything about what
        a particular task does.
        """
        self._metrics[task_id] = metrics

    def metrics_for(self, task_id: str) -> TaskMetrics | None:
        return self._metrics.get(task_id)

    def note(self, key: str, value: float | int | str) -> None:
        """Record a measured figure under a label, for the verification document.

        The label is written by the agent that measured it. The value is not: it
        always comes from a kernel return value a moment earlier. The ledger
        exists because the Architect writes the closing verification artifact
        and has to restate numbers the ETL and Analytics Engineers established
        in earlier tasks.
        """
        self._facts[key] = value

    @property
    def facts(self) -> dict[str, float | int | str]:
        return self._facts


def _cell(value: object) -> str:
    """One frame value as display text, with nulls shown rather than blanked."""
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def metrics_json(bundle: AggBundle) -> str:
    """The aggregate bundle as the ``analytics/metrics.json`` artifact body."""
    return json.dumps(bundle.model_dump(mode="json"), indent=2)
