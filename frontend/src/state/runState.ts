/**
 * The shape the renderer draws from.
 *
 * This mirrors `RunState` in backend/app/core/reducer.py, field for field. The
 * two are checked against each other by the fixtures in
 * backend/tests/fixtures, replayed through both reducers.
 *
 * Note the one deliberate asymmetry with the wire: events are snake_case,
 * because that is the contract and there is no conversion layer. Derived view
 * state here is camelCase. The reducer is the single place the two meet.
 */

import type {
  AgentId,
  Artifact,
  LogLevel,
  Plan,
  TaskMetrics,
  TaskStatus,
} from "../types/events.ts";

export interface LogLine {
  seq: number;
  at: number;
  level: LogLevel;
  message: string;
  source: "agent" | "runtime";
  agentId: AgentId | null;
  taskId: string | null;
}

export interface AgentView {
  agentId: AgentId;
  role: string;
  assignedTaskIds: string[];
  idle: boolean;
}

export interface RunState {
  runId: string | null;
  seed: number | null;
  speed: number;
  requirementTitle: string | null;
  started: boolean;
  completed: boolean;
  error: string | null;
  durationMs: number | null;
  plan: Plan | null;
  taskStatus: Readonly<Record<string, TaskStatus>>;
  taskAgent: Readonly<Record<string, AgentId>>;
  taskProgress: Readonly<Record<string, number>>;
  taskMetrics: Readonly<Record<string, TaskMetrics>>;
  taskAttempts: Readonly<Record<string, number>>;
  agents: Readonly<Partial<Record<AgentId, AgentView>>>;
  artifacts: readonly Artifact[];
  logs: readonly LogLine[];
  retryCount: number;
  lastSeq: number;
}

export function initialState(): RunState {
  return {
    runId: null,
    seed: null,
    speed: 1,
    requirementTitle: null,
    started: false,
    completed: false,
    error: null,
    durationMs: null,
    plan: null,
    taskStatus: {},
    taskAgent: {},
    taskProgress: {},
    taskMetrics: {},
    taskAttempts: {},
    agents: {},
    artifacts: [],
    logs: [],
    retryCount: 0,
    lastSeq: -1,
  };
}
