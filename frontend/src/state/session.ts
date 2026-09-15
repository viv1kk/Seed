/**
 * What the browser needs to rejoin a run after a refresh.
 *
 * The backend replays every run from seq=0, so recovering a refresh needs
 * nothing more than remembering which run was being watched and which document
 * it was built from. That is view state, the same kind as a selection or a
 * scroll position, and holding it here does not make the frontend decide
 * anything: the whole run still arrives as events and is applied by the same
 * reducer, and the plan is rebuilt by asking the backend to parse the document
 * again.
 *
 * The document is stored, not just its id, because a requirement can be pasted
 * or opened from a file rather than picked from the bundled examples, and there
 * is nothing on the server to look it up by. It is a few kilobytes of Markdown.
 *
 * sessionStorage rather than localStorage on purpose. A run belongs to the tab
 * watching it, and a stale run id resurfacing in a new window a day later would
 * be worse than starting clean.
 */

const KEY = "seed.watching";

/**
 * Where a requirement document came from.
 *
 * `example` is one of the bundled files, named by id so the backend reads it
 * from disk. `markdown` is the person's own document, carried as text because
 * only they have it. `POST /api/plans` takes either.
 */
export type Source =
  | { kind: "example"; id: string }
  | { kind: "markdown"; text: string; name: string };

export interface WatchedRun {
  runId: string;
  source: Source;
  speed: number;
}

export function rememberRun(watched: WatchedRun): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(watched));
  } catch {
    // Private windows, blocked site data, and a document too large for the
    // quota all throw here. Losing the ability to rejoin after a refresh is not
    // worth failing a run over.
  }
}

export function recallRun(): WatchedRun | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (raw === null) return null;
    const parsed = JSON.parse(raw) as Partial<WatchedRun>;
    const source = readSource(parsed.source);
    if (typeof parsed.runId !== "string" || source === null) return null;
    return {
      runId: parsed.runId,
      source,
      speed: typeof parsed.speed === "number" ? parsed.speed : 1,
    };
  } catch {
    return null;
  }
}

export function forgetRun(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // See rememberRun.
  }
}

/**
 * Validate what came back out of storage.
 *
 * Anything can be in sessionStorage: a half-written value, or a shape this
 * build no longer writes. An unreadable one means "nothing to rejoin", which is
 * a clean start rather than an error.
 */
function readSource(value: unknown): Source | null {
  if (typeof value !== "object" || value === null) return null;
  const candidate = value as Partial<Source> & Record<string, unknown>;

  if (candidate.kind === "example" && typeof candidate.id === "string") {
    return { kind: "example", id: candidate.id };
  }
  if (
    candidate.kind === "markdown" &&
    typeof candidate.text === "string" &&
    typeof candidate.name === "string"
  ) {
    return { kind: "markdown", text: candidate.text, name: candidate.name };
  }
  return null;
}

/** The body `POST /api/plans` expects for this source. */
export function planRequestFor(source: Source): { example_id: string } | { markdown: string } {
  return source.kind === "example" ? { example_id: source.id } : { markdown: source.text };
}

/** What to show in the title bar beside the product name. */
export function sourceName(source: Source): string {
  return source.kind === "example" ? `${source.id}.md` : source.name;
}
