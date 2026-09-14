/**
 * The event reducer. Pure, and the only place events become view state.
 *
 * This mirrors `apply_event` in backend/app/core/reducer.py. Both are replayed
 * over the same fixtures and must agree, so a change here without the matching
 * change there fails a test in both languages.
 *
 * It computes nothing. Every value written is carried on the event; the switch
 * only decides where it lands. Deriving a status or a metric here would be the
 * frontend doing the backend's job, which is the one thing this tree must not
 * do (see frontend/CLAUDE.md).
 */

import type { AgentId, SeedEvent } from "../types/events.ts";
import { assertNever } from "./assertNever.ts";
import type { AgentView, RunState } from "./runState.ts";

export function applyEvents(state: RunState, events: readonly SeedEvent[]): RunState {
  let next = state;
  for (const event of events) next = applyEvent(next, event);
  return next;
}

export function applyEvent(state: RunState, event: SeedEvent): RunState {
  const base: RunState = { ...state, lastSeq: event.seq, runId: event.run_id };

  switch (event.type) {
    case "run.started":
      return {
        ...base,
        started: true,
        seed: event.seed,
        speed: event.speed,
        requirementTitle: event.requirement_title,
      };

    case "plan.built": {
      // Every task in the plan enters the board as pending, so the whole graph
      // can be drawn before anything moves.
      const taskStatus: Record<string, RunState["taskStatus"][string]> = {};
      const taskAgent: Record<string, AgentId> = {};
      for (const [taskId, task] of Object.entries(event.plan.tasks)) {
        taskStatus[taskId] = "pending";
        taskAgent[taskId] = task.agent_id;
      }
      return { ...base, plan: event.plan, taskStatus, taskAgent };
    }

    case "agent.spawned":
      return {
        ...base,
        agents: {
          ...base.agents,
          [event.agent_id]: {
            agentId: event.agent_id,
            role: event.role,
            assignedTaskIds: [...event.assigned_task_ids],
            idle: false,
          } satisfies AgentView,
        },
      };

    case "task.ready":
      return { ...base, taskStatus: { ...base.taskStatus, [event.task_id]: "ready" } };

    case "task.started":
      return {
        ...base,
        taskStatus: { ...base.taskStatus, [event.task_id]: "running" },
        taskAgent: { ...base.taskAgent, [event.task_id]: event.agent_id },
        agents: withAgentIdle(base, event.agent_id, false),
      };

    case "task.progress":
      return { ...base, taskProgress: { ...base.taskProgress, [event.task_id]: event.pct } };

    case "log.emitted":
      return {
        ...base,
        logs: [
          ...base.logs,
          {
            seq: event.seq,
            at: event.at,
            level: event.level,
            message: event.message,
            source: event.source,
            agentId: event.agent_id ?? null,
            taskId: event.task_id ?? null,
          },
        ],
      };

    case "artifact.created":
      return { ...base, artifacts: [...base.artifacts, event.artifact] };

    case "task.failed":
      // A recoverable failure reads as retrying, because a task.retried is
      // coming (contract rule 4) and the node must not look dead.
      return {
        ...base,
        taskStatus: {
          ...base.taskStatus,
          [event.task_id]: event.recoverable ? "retrying" : "failed",
        },
        taskAgent: { ...base.taskAgent, [event.task_id]: event.agent_id },
      };

    case "task.retried":
      return {
        ...base,
        taskStatus: { ...base.taskStatus, [event.task_id]: "running" },
        taskAttempts: { ...base.taskAttempts, [event.task_id]: event.attempt },
        retryCount: base.retryCount + 1,
      };

    case "task.completed":
      return {
        ...base,
        taskStatus: { ...base.taskStatus, [event.task_id]: "completed" },
        taskAgent: { ...base.taskAgent, [event.task_id]: event.agent_id },
        taskMetrics: { ...base.taskMetrics, [event.task_id]: event.metrics },
        taskProgress: { ...base.taskProgress, [event.task_id]: 1.0 },
      };

    case "agent.idle":
      return { ...base, agents: withAgentIdle(base, event.agent_id, true) };

    case "run.completed":
      return { ...base, completed: true, durationMs: event.duration_ms };

    case "run.failed":
      return { ...base, error: event.error };

    default:
      return assertNever(event);
  }
}

function withAgentIdle(state: RunState, agentId: AgentId, idle: boolean): RunState["agents"] {
  const existing = state.agents[agentId];
  if (existing === undefined) {
    // An agent can be referenced before its agent.spawned arrives, on a replay
    // that starts mid-stream. Record what we know.
    return { ...state.agents, [agentId]: { agentId, role: "", assignedTaskIds: [], idle } };
  }
  return { ...state.agents, [agentId]: { ...existing, idle } };
}
