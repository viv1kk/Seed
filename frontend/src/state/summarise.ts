/**
 * Reduce a RunState to the comparable shape the fixtures assert.
 *
 * ## The keys here are snake_case on purpose
 *
 * Everywhere else in this tree, derived view state is camelCase and only the
 * wire is snake_case. This function deliberately crosses back.
 *
 * The reason is that the `expected` block in each fixture is a single
 * hand-written object asserted by both `backend/tests/test_reducer.py` and
 * `replay.test.ts`. One spelling has to win, and it is Python's, because the
 * contract is defined in Python and the fixtures live in the backend tree.
 *
 * So: this is a serialiser to a foreign convention, not a leak of one. If you
 * find yourself renaming a key here to match the TypeScript field it came from,
 * you have broken the parity test, which is the only thing keeping the two
 * reducers honest. Rename it in the fixtures and in summarise() on the Python
 * side too, or not at all.
 */

import type { RunState } from "./runState.ts";

/** The parity shape. Every key is snake_case. See the note above. */
export interface StateSummary {
  last_seq: number;
  run_id: string | null;
  seed: number | null;
  speed: number;
  requirement_title: string | null;
  started: boolean;
  completed: boolean;
  error: string | null;
  duration_ms: number | null;
  task_status: Record<string, string>;
  task_agent: Record<string, string>;
  task_attempts: Record<string, number>;
  retry_count: number;
  artifact_count: number;
  artifact_ids: string[];
  log_count: number;
  streaming_ids: string[];
  streamed_chars: number;
  streams_complete: string[];
  agents_spawned: string[];
  agents_idle: string[];
  plan_task_count: number;
}

export function summarise(state: RunState): StateSummary {
  const agentIds = Object.keys(state.agents).sort();

  return {
    last_seq: state.lastSeq,
    run_id: state.runId,
    seed: state.seed,
    speed: state.speed,
    requirement_title: state.requirementTitle,
    started: state.started,
    completed: state.completed,
    error: state.error,
    duration_ms: state.durationMs,
    task_status: sortedByKey(state.taskStatus),
    task_agent: sortedByKey(state.taskAgent),
    task_attempts: sortedByKey(state.taskAttempts),
    retry_count: state.retryCount,
    artifact_count: state.artifacts.length,
    artifact_ids: state.artifacts.map((artifact) => artifact.id),
    log_count: state.logs.length,
    streaming_ids: Object.keys(state.streaming).sort(),
    streamed_chars: Object.values(state.streaming).reduce((n, s) => n + s.text.length, 0),
    streams_complete: Object.values(state.streaming)
      .filter((s) => s.complete)
      .map((s) => s.artifactId)
      .sort(),
    agents_spawned: agentIds,
    agents_idle: agentIds.filter((id) => state.agents[id as keyof typeof state.agents]?.idle),
    plan_task_count: state.plan === null ? 0 : Object.keys(state.plan.tasks).length,
  };
}

/**
 * Key order is not significant to a deep-equal comparison, but it is significant
 * to anyone reading a failure diff, and Python's summarise() sorts too.
 */
function sortedByKey<T>(record: Readonly<Record<string, T>>): Record<string, T> {
  const out: Record<string, T> = {};
  for (const key of Object.keys(record).sort()) {
    out[key] = record[key] as T;
  }
  return out;
}
