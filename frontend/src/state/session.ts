/**
 * What the browser needs to rejoin a run after a refresh.
 *
 * The backend replays every run from seq=0, so recovering a refresh needs
 * nothing more than remembering which run was being watched. That is view
 * state, the same kind as a selection or a scroll position, and holding it here
 * does not make the frontend decide anything: the whole run still arrives as
 * events and is applied by the same reducer.
 *
 * sessionStorage rather than localStorage on purpose. A run belongs to the tab
 * watching it, and a stale run id resurfacing in a new window a day later would
 * be worse than starting clean.
 */

const KEY = "seed.watching";

export interface WatchedRun {
  runId: string;
  exampleId: string;
  speed: number;
}

export function rememberRun(watched: WatchedRun): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(watched));
  } catch {
    // Private windows and blocked site data both throw here. Losing the
    // ability to rejoin after a refresh is not worth failing a run over.
  }
}

export function recallRun(): WatchedRun | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (raw === null) return null;
    const parsed = JSON.parse(raw) as Partial<WatchedRun>;
    if (typeof parsed.runId !== "string" || typeof parsed.exampleId !== "string") {
      return null;
    }
    return {
      runId: parsed.runId,
      exampleId: parsed.exampleId,
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
