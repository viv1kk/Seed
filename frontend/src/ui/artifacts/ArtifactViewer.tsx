/**
 * The artifact viewer, opened over the centre column.
 *
 * Three states, in the order a file goes through them:
 *
 * 1. **Streaming.** `artifact.streaming` opens the viewer by itself and the
 *    text grows as `artifact.chunk` events land. This is the file being written
 *    in front of you, which is the point; nothing is fetched yet, because there
 *    is nothing on the server to fetch.
 * 2. **Created.** `artifact.created` completes the stream, and the body is
 *    fetched from `GET /api/artifacts/{id}`. Code comes back as Pygments HTML,
 *    highlighted server side, and replaces the plain text in place.
 * 3. **Opened later.** A finished artifact clicked in the tree goes straight to
 *    the fetch.
 *
 * Bodies never travel on the event stream: `artifact.created` carries metadata
 * only, so a 400-line source file does not stall the log.
 */

import { useEffect, useRef, useState } from "react";

import { fetchArtifact } from "../../api/client.ts";
import type { ArtifactBody } from "../../types/events.ts";
import { bytes, count } from "../present.ts";
import { useSeedStore } from "../useSeedStore.ts";
import { useViewStore, viewActions } from "../useViewStore.ts";

/** How long a finished file stays up before the viewer steps aside. */
const DWELL_MS = 1_800;

/**
 * Open the viewer when a runner starts writing a file, and close it again once
 * the file is written.
 *
 * Opening is the beat worth having: a file appearing line by line is the
 * clearest evidence that something is being built rather than revealed. Staying
 * open is not. The viewer covers the graph and the log, and a run writes a
 * dozen files, so a viewer that never left would hide the failure beat, which
 * is the most persuasive thing on the screen.
 *
 * So an automatic viewer sees the file through: the text streams, the Pygments
 * highlighting lands on `artifact.created`, it holds long enough to read, and
 * then it hands the screen back. A viewer somebody opened by clicking stays
 * until they close it, which is why the store records which kind it is.
 *
 * Only while the run is live. A refresh replays every chunk of every past
 * stream in a few frames, and opening each in turn would be a flicker.
 */
export function useOpenOnStream(): void {
  const streaming = useSeedStore((state) => state.run.streaming);
  const completed = useSeedStore((state) => state.run.completed);
  const seen = useRef<Set<string>>(new Set());
  const openArtifactId = useViewStore((state) => state.openArtifactId);
  const auto = useViewStore((state) => state.artifactAutoOpened);

  useEffect(() => {
    for (const stream of Object.values(streaming)) {
      if (seen.current.has(stream.artifactId)) continue;
      seen.current.add(stream.artifactId);
      if (!stream.complete && !completed) {
        viewActions().openArtifact(stream.artifactId, true);
      }
    }
  }, [streaming, completed]);

  const finished =
    openArtifactId !== null && streaming[openArtifactId]?.complete === true;

  useEffect(() => {
    if (!auto || !finished || openArtifactId === null) return;
    const timer = setTimeout(() => {
      // Only if it is still the same automatic viewer. Somebody who clicked a
      // file in the meantime keeps what they opened.
      const now = viewActions();
      if (now.artifactAutoOpened && now.openArtifactId === openArtifactId) {
        now.openArtifact(null);
      }
    }, DWELL_MS);
    return () => clearTimeout(timer);
  }, [auto, finished, openArtifactId]);

  // Clear the way for the deliverable. The last file a run writes is still open
  // when the run ends, and the dashboard arriving behind it would be the one
  // moment of the demo nobody sees. The tree keeps the file one click away.
  useEffect(() => {
    if (completed && viewActions().artifactAutoOpened) viewActions().openArtifact(null);
  }, [completed]);
}

export function ArtifactViewer({ artifactId }: { artifactId: string }) {
  const stream = useSeedStore((state) => state.run.streaming[artifactId]);
  const artifact = useSeedStore((state) =>
    state.run.artifacts.find((candidate) => candidate.id === artifactId),
  );
  const [body, setBody] = useState<ArtifactBody | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const streamingNow = stream !== undefined && !stream.complete;
  const path = body?.path ?? artifact?.path ?? stream?.path ?? artifactId;

  // Fetch once the artifact exists on the server, and not before.
  useEffect(() => {
    setBody(null);
    setFailure(null);
    if (artifact === undefined) return;

    let live = true;
    fetchArtifact(artifactId)
      .then((next) => {
        if (live) setBody(next);
      })
      .catch(() => {
        if (live) setFailure("Could not load this file. Try opening it again.");
      });
    return () => {
      live = false;
    };
  }, [artifactId, artifact]);

  return (
    <section
      className="flex h-full flex-col bg-ink-800"
      aria-label={`File ${path}`}
    >
      <header className="flex items-center gap-3 border-b border-ink-600 px-3 py-2">
        <h2 className="t-log min-w-0 flex-1 truncate text-chalk">{path}</h2>
        <span className="t-secondary shrink-0 text-chalk-dim">{caption(body, artifact, stream)}</span>
        <button
          type="button"
          onClick={() => viewActions().openArtifact(null)}
          className="t-secondary shrink-0 rounded-sm px-2 py-0.5 text-chalk-dim hover:text-chalk"
        >
          Close
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-auto px-3 py-2">
        {failure !== null && <p className="t-secondary text-fault-ink">{failure}</p>}

        {streamingNow && <StreamingText text={stream.text} />}

        {!streamingNow && body === null && failure === null && (
          <p className="t-secondary text-chalk-dim">Loading.</p>
        )}

        {!streamingNow && body !== null && <Body body={body} />}
      </div>
    </section>
  );
}

/**
 * The file as it is being written, scrolled to the end.
 *
 * Unhighlighted on purpose. Pygments runs on the server against a finished
 * file, and there is no client-side highlighter in this project; a half-written
 * file has no valid parse anyway.
 */
function StreamingText({ text }: { text: string }) {
  const end = useRef<HTMLSpanElement | null>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [text]);

  return (
    <pre className="t-log whitespace-pre-wrap text-chalk">
      {text}
      <span
        ref={end}
        aria-hidden
        className="ml-0.5 inline-block h-3.5 w-1.5 translate-y-0.5 bg-signal"
      />
    </pre>
  );
}

function Body({ body }: { body: ArtifactBody }) {
  if (body.kind === "dataset" || body.preview != null) return <Preview body={body} />;

  if (body.html != null) {
    return (
      // Highlighted server side by Pygments. The only innerHTML in the project,
      // and its source is our own backend reading our own files.
      <pre className="seed-code seed-fade" dangerouslySetInnerHTML={{ __html: body.html }} />
    );
  }

  return <pre className="t-log seed-fade whitespace-pre-wrap text-chalk">{body.text ?? ""}</pre>;
}

function Preview({ body }: { body: ArtifactBody }) {
  const columns = body.columns ?? [];
  const rows = body.preview ?? [];
  return (
    <div className="seed-fade overflow-x-auto">
      <table className="t-log w-full border-collapse">
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column}
                className="border-b border-ink-600 px-2 py-1 text-left font-medium text-chalk-dim whitespace-nowrap"
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-b border-ink-600/40">
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="px-2 py-0.5 whitespace-nowrap text-chalk">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="t-secondary pt-2 text-chalk-dim">
        Showing the first {rows.length} of {count(body.rows ?? 0)} rows.
      </p>
    </div>
  );
}

function caption(
  body: ArtifactBody | null,
  artifact: { bytes: number; rows?: number | null } | undefined,
  stream: { text: string; complete: boolean } | undefined,
): string {
  if (stream !== undefined && !stream.complete) return `writing, ${count(stream.text.length)} chars`;
  if (body?.lines != null) return `${count(body.lines)} lines`;
  if (body?.rows != null) return `${count(body.rows)} rows, ${(body.columns ?? []).length} columns`;
  if (artifact !== undefined) return bytes(artifact.bytes);
  return "";
}
