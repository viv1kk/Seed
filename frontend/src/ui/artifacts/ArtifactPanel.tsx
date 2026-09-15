/**
 * The artifacts panel: a file tree grouped by folder.
 *
 * New rows flash amber for 400ms and nothing else. A row is new for exactly as
 * long as it takes to notice, and then it behaves like every other row.
 *
 * A file still being written appears here too, as its own row with a live
 * character count, so the tree shows the run producing a file rather than the
 * file appearing fully formed. Clicking any row opens the viewer.
 */

import { memo, useEffect, useMemo, useRef, useState } from "react";

import type { StreamingArtifact } from "../../state/runState.ts";
import type { Artifact } from "../../types/events.ts";
import { bytes, count } from "../present.ts";
import { useSeedStore } from "../useSeedStore.ts";
import { useViewStore, viewActions } from "../useViewStore.ts";

interface Row {
  id: string;
  name: string;
  detail: string;
  streaming: boolean;
}

export function ArtifactPanel() {
  const artifacts = useSeedStore((state) => state.run.artifacts);
  const streaming = useSeedStore((state) => state.run.streaming);
  const openId = useViewStore((state) => state.openArtifactId);

  const folders = useMemo(() => group(artifacts, streaming), [artifacts, streaming]);
  const total = folders.reduce((sum, folder) => sum + folder.rows.length, 0);

  if (total === 0) {
    return (
      <p className="t-secondary px-3 py-2 text-chalk-dim">
        Files appear here as agents produce them.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3 px-1 py-2">
      {folders.map((folder) => (
        <div key={folder.name}>
          <h3 className="t-panel-header px-2 pb-1 text-chalk-dim opacity-70">{folder.name}</h3>
          <ul>
            {folder.rows.map((row) => (
              <ArtifactRow key={row.id} row={row} open={openId === row.id} />
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

const ArtifactRow = memo(function ArtifactRow({ row, open }: { row: Row; open: boolean }) {
  const [fresh, setFresh] = useState(true);
  const mounted = useRef(false);

  useEffect(() => {
    // Only a row that arrives during a run flashes. A replay after a refresh
    // would otherwise light the whole tree up at once.
    if (mounted.current) return;
    mounted.current = true;
    const timer = setTimeout(() => setFresh(false), 420);
    return () => clearTimeout(timer);
  }, []);

  return (
    <li>
      <button
        type="button"
        onClick={() => viewActions().openArtifact(row.id)}
        className={`flex w-full items-baseline justify-between gap-2 rounded-sm px-2 py-1 text-left hover:bg-ink-700 ${
          fresh ? "seed-flash" : ""
        } ${open ? "bg-ink-700" : ""}`}
      >
        <span className="t-log min-w-0 truncate text-chalk">
          {row.streaming && (
            <span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-signal align-middle" />
          )}
          {row.name}
        </span>
        <span className="t-secondary shrink-0 text-chalk-dim opacity-70">{row.detail}</span>
      </button>
    </li>
  );
});

interface Folder {
  name: string;
  rows: Row[];
}

/**
 * Group by folder, in the order files were produced.
 *
 * A file that is mid-stream shows its character count so far. Once
 * `artifact.created` lands the same row becomes the finished artifact, which is
 * why both are keyed by artifact id.
 */
function group(
  artifacts: readonly Artifact[],
  streaming: Readonly<Record<string, StreamingArtifact>>,
): Folder[] {
  const done = new Set(artifacts.map((artifact) => artifact.id));
  const rows: Row[] = artifacts.map((artifact) => ({
    id: artifact.id,
    name: fileName(artifact.path),
    detail:
      artifact.rows != null ? `${count(artifact.rows)} rows` : bytes(artifact.bytes),
    streaming: false,
  }));

  for (const stream of Object.values(streaming)) {
    if (done.has(stream.artifactId)) continue;
    rows.push({
      id: stream.artifactId,
      name: fileName(stream.path),
      detail: `${count(stream.text.length)} chars`,
      streaming: true,
    });
  }

  const folders: Folder[] = [];
  const index = new Map<string, Folder>();
  const pathOf = new Map<string, string>([
    ...artifacts.map((a) => [a.id, a.path] as const),
    ...Object.values(streaming).map((s) => [s.artifactId, s.path] as const),
  ]);

  for (const row of rows) {
    const name = folderName(pathOf.get(row.id) ?? row.name);
    let folder = index.get(name);
    if (folder === undefined) {
      folder = { name, rows: [] };
      index.set(name, folder);
      folders.push(folder);
    }
    folder.rows.push(row);
  }
  return folders;
}

function folderName(path: string): string {
  const cut = path.lastIndexOf("/");
  return cut === -1 ? "root" : `${path.slice(0, cut)}/`;
}

function fileName(path: string): string {
  const cut = path.lastIndexOf("/");
  return cut === -1 ? path : path.slice(cut + 1);
}
