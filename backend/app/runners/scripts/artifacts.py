"""Building the artifacts a run produces.

The rule here is that a code artifact is **the file that ran**. Not a rendering
of it, not a sample of it, not a version of it written for the demo. The ETL
Engineer's ``pipeline/clean.py`` is read off disk from ``app/pipeline/clean.py``
at the moment it is emitted, which is the module the kernel just called. So when
somebody asks whether the data work is real, the answer is to open the artifact
and read the code that did it.

That has a consequence worth stating: those modules are client-facing. They are
commented and named the way they are because someone is going to put them on a
projector and read them out.

Datasets are the same idea applied to frames. A dataset artifact carries a real
row count, the real column list and the first twenty real rows, taken from the
frame in the kernel at that moment rather than from a fixture.
"""

from pathlib import Path
from typing import Final

from app.core.types import AgentId, Artifact, ArtifactBody, ArtifactKind
from app.pipeline.highlight import highlight
from app.runners.scripts.beats import BeatCtx

# backend/app/runners/scripts/artifacts.py -> ... -> backend/app, and the repo root.
_APP_DIR: Final[Path] = Path(__file__).resolve().parents[2]
_REPO_ROOT: Final[Path] = _APP_DIR.parent.parent

# Where an artifact path is actually served from. A code artifact whose path is
# not under one of these has no real file behind it and must not be claimed as
# code, so ``source_for`` raises rather than inventing one.
SOURCE_ROOTS: Final[dict[str, Path]] = {
    "pipeline/": _APP_DIR / "pipeline",
    "dashboard/": _REPO_ROOT / "frontend" / "src" / "ui" / "dashboard",
}

_LANG_BY_SUFFIX: Final[dict[str, str]] = {
    ".py": "python",
    ".tsx": "typescript",
    ".ts": "typescript",
    ".json": "json",
    ".sql": "sql",
    ".yaml": "yaml",
    ".md": "markdown",
}


def artifact_id(ctx: BeatCtx, path: str) -> str:
    """Stable across runs of the same document, unique across documents.

    Keyed by the plan id, which is a hash of the markdown, so two runs of the
    same requirement file produce the same artifact ids and a diff of two runs
    stays readable. Keying on the run id instead would make every id new on
    every run and nothing would be comparable.
    """
    slug = path.replace("/", "_").replace(".", "_")
    return f"art_{ctx.plan.id}_{ctx.task.id.replace('.', '_')}_{slug}"


def source_for(path: str) -> str:
    """Read the real file behind a code artifact path."""
    for prefix, root in SOURCE_ROOTS.items():
        if path.startswith(prefix):
            resolved = root / path[len(prefix) :]
            if resolved.is_file():
                return resolved.read_text(encoding="utf-8")
            break
    raise FileNotFoundError(f"No source file behind the artifact path {path!r}")


def lang_for(path: str) -> str:
    return _LANG_BY_SUFFIX.get(Path(path).suffix, "text")


def code(ctx: BeatCtx, path: str, agent_id: AgentId) -> Artifact:
    """A code artifact backed by a real file, highlighted server side."""
    source = source_for(path)
    lang = lang_for(path)
    artifact = Artifact(
        id=artifact_id(ctx, path),
        kind="code",
        path=path,
        produced_by=agent_id,
        task_id=ctx.task.id,
        bytes=len(source.encode("utf-8")),
        lang=lang,
    )
    ctx.kernel.put_body(
        artifact.id,
        ArtifactBody(
            id=artifact.id,
            kind="code",
            path=path,
            lang=lang,
            text=source,
            html=highlight(source, lang),
            lines=source.count("\n") + 1,
        ),
    )
    return artifact


def dataset(ctx: BeatCtx, path: str, frame_name: str, agent_id: AgentId) -> Artifact:
    """A dataset artifact carrying a real preview of a frame in the kernel."""
    preview = ctx.kernel.preview(frame_name)
    artifact = Artifact(
        id=artifact_id(ctx, path),
        kind="dataset",
        path=path,
        produced_by=agent_id,
        task_id=ctx.task.id,
        bytes=preview.bytes,
        rows=preview.rows,
        columns=preview.columns,
        preview=preview.sample,
    )
    ctx.kernel.put_body(
        artifact.id,
        ArtifactBody(
            id=artifact.id,
            kind="dataset",
            path=path,
            rows=preview.rows,
            columns=preview.columns,
            preview=preview.sample,
        ),
    )
    return artifact


def written(
    ctx: BeatCtx,
    path: str,
    text: str,
    agent_id: AgentId,
    kind: ArtifactKind = "doc",
) -> Artifact:
    """An artifact generated during the run: a document, a spec, a table.

    Unlike ``code``, the text is produced rather than read, so the caller passes
    it in. It is still real: every generator that uses this builds its text from
    the plan and from kernel results.
    """
    lang = lang_for(path) if kind in {"code", "table"} else None
    artifact = Artifact(
        id=artifact_id(ctx, path),
        kind=kind,
        path=path,
        produced_by=agent_id,
        task_id=ctx.task.id,
        bytes=len(text.encode("utf-8")),
        lang=lang,
    )
    ctx.kernel.put_body(
        artifact.id,
        ArtifactBody(
            id=artifact.id,
            kind=kind,
            path=path,
            lang=lang,
            text=text,
            html=highlight(text, lang) if lang else None,
            lines=text.count("\n") + 1,
        ),
    )
    return artifact
