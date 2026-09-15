/**
 * Fetch wrappers for the API.
 *
 * Four endpoints and no data-fetching library, per CLAUDE.md. Paths are
 * relative: in development Vite proxies /api to port 8000, and in the built
 * demo uvicorn serves the API and this bundle from one origin.
 */

import type { ExampleSummary, ParseResult } from "../types/events.ts";

export type ControlAction = "pause" | "resume" | "cancel" | "speed";

export interface RunControlState {
  run_id: string;
  action: string;
  speed: number;
  paused: boolean;
  cancelled: boolean;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return (await response.json()) as T;
}

export async function fetchExamples(): Promise<ExampleSummary[]> {
  return getJson<ExampleSummary[]>("/api/examples");
}

/**
 * Parse a requirement document.
 *
 * A rejected document is a 200 carrying `status: "error"`, not an HTTP failure,
 * so the caller branches on the result rather than catching. Only a genuine
 * transport or server fault throws.
 */
export async function createPlan(
  body: { example_id: string } | { markdown: string },
): Promise<ParseResult> {
  const response = await fetch("/api/plans", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`/api/plans returned ${response.status}`);
  return (await response.json()) as ParseResult;
}

export async function createRun(
  planId: string,
  speed = 1,
): Promise<{ run_id: string }> {
  const response = await fetch("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ plan_id: planId, speed }),
  });
  if (!response.ok) throw new Error(`/api/runs returned ${response.status}`);
  return (await response.json()) as { run_id: string };
}

/**
 * Pause, resume, cancel, or change speed.
 *
 * The backend owns all of it. Nothing here tracks whether a run is paused; the
 * answer comes back on the response and, for anything that matters, on the
 * event stream.
 */
export async function controlRun(
  runId: string,
  action: ControlAction,
  value?: number,
): Promise<RunControlState> {
  const response = await fetch(`/api/runs/${runId}/control`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, value: value ?? null }),
  });
  if (!response.ok) throw new Error(`control returned ${response.status}`);
  return (await response.json()) as RunControlState;
}
