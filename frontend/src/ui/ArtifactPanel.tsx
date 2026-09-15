/**
 * The artifacts panel: a list of what the run produced, and a viewer.
 *
 * Bodies are not on the event stream. `artifact.created` carries metadata only,
 * and the body is fetched from `GET /api/artifacts/{id}` when somebody opens
 * one, so a 400-line source file never has to travel through the log.
 *
 * Code arrives as Pygments HTML from the backend. There is no client-side
 * highlighter in this project, by decision: the markup is generated once,
 * server side, next to the file it describes.
 *
 * Phase 3 is a list and a viewer. The tree, the insert flash and the styling
 * are phase 4.
 */

import { useCallback, useEffect, useState } from "react";

import { fetchArtifact } from "../api/client.ts";
import type { ArtifactBody } from "../types/events.ts";
import type { RunState } from "../state/runState.ts";

export function ArtifactPanel({ run }: { run: RunState }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const [body, setBody] = useState<ArtifactBody | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const open = useCallback((id: string) => {
    setOpenId(id);
    setBody(null);
    setFailure(null);
  }, []);

  useEffect(() => {
    if (openId === null) return;
    let live = true;
    fetchArtifact(openId)
      .then((next) => {
        if (live) setBody(next);
      })
      .catch(() => {
        if (live) setFailure("Could not load this file. Try opening it again.");
      });
    return () => {
      live = false;
    };
  }, [openId]);

  const streams = Object.values(run.streaming).filter((stream) => !stream.complete);

  return (
    <section>
      <h2>Artifacts</h2>
      {run.artifacts.length === 0 && streams.length === 0 && (
        <p>Files appear here as agents produce them.</p>
      )}

      <ul>
        {run.artifacts.map((artifact) => (
          <li key={artifact.id}>
            <button type="button" onClick={() => open(artifact.id)}>
              {artifact.path}
            </button>{" "}
            ({artifact.kind}, {artifact.bytes.toLocaleString("en-IN")} bytes
            {artifact.rows != null && `, ${artifact.rows.toLocaleString("en-IN")} rows`})
          </li>
        ))}
      </ul>

      {streams.map((stream) => (
        <div key={stream.artifactId}>
          <p>
            Writing {stream.path} ({stream.text.length} characters so far)
          </p>
          <pre>{stream.text}</pre>
        </div>
      ))}

      {openId !== null && (
        <div>
          <button type="button" onClick={() => setOpenId(null)}>
            Close
          </button>
          {failure !== null && <p>{failure}</p>}
          {body === null && failure === null && <p>Loading.</p>}
          {body !== null && <ArtifactBodyView body={body} />}
        </div>
      )}
    </section>
  );
}

function ArtifactBodyView({ body }: { body: ArtifactBody }) {
  if (body.kind === "dataset") {
    return <DatasetView body={body} />;
  }

  if (body.html != null) {
    return (
      <>
        <p>
          {body.path}
          {body.lines != null && `, ${body.lines} lines`}
        </p>
        {/* Highlighted server side by Pygments. The only innerHTML in the
            project, and its source is our own backend reading our own files. */}
        <pre className="seed-code" dangerouslySetInnerHTML={{ __html: body.html }} />
      </>
    );
  }

  return (
    <>
      <p>{body.path}</p>
      <pre>{body.text ?? ""}</pre>
    </>
  );
}

function DatasetView({ body }: { body: ArtifactBody }) {
  const columns = body.columns ?? [];
  const rows = body.preview ?? [];
  return (
    <>
      <p>
        {body.path}, {(body.rows ?? 0).toLocaleString("en-IN")} rows, {columns.length} columns.
        Showing the first {rows.length}.
      </p>
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {row.map((cell, cellIndex) => (
                <td key={cellIndex}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
