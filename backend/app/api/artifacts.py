"""Artifact bodies, fetched on demand rather than carried on the stream.

A 400-line source file on an event would bloat the stream and stall the log, so
``artifact.created`` carries metadata only and the panel fetches the body when
somebody opens it. That also means the body is fetched once per artifact opened
rather than once per artifact produced.

Code artifacts come back as Pygments HTML, highlighted server side. There is no
client-side highlighter in this project and this endpoint is why.
"""

from fastapi import APIRouter, HTTPException

from app.api.deps import Registry
from app.core.types import ArtifactBody

router = APIRouter(prefix="/api", tags=["artifacts"])


@router.get("/artifacts/{artifact_id}")
async def get_artifact(artifact_id: str, registry: Registry) -> ArtifactBody:
    found = registry.find_artifact(artifact_id)
    if found is None:
        raise HTTPException(status_code=404, detail=f"No artifact with id {artifact_id!r}")

    record, artifact = found
    body = record.kernel.body(artifact.id)
    if body is not None:
        return body

    # An artifact was emitted without a body. Nothing in the project does this,
    # but answering with the metadata the event already carried beats a 500:
    # the panel shows the file with no contents rather than an error.
    return ArtifactBody(
        id=artifact.id,
        kind=artifact.kind,
        path=artifact.path,
        lang=artifact.lang,
        rows=artifact.rows,
        columns=artifact.columns,
        preview=artifact.preview,
    )
