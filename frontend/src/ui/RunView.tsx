/**
 * The run, as plain text. No graph, no styling.
 *
 * Phase 2 is supposed to look like this. The plan list carries a status word per
 * task and the log is a div, which is enough to see that statuses move in the
 * right order, that two agents work at once where the graph allows, and that
 * lines arrive in order. The plan room is phase 4.
 */

import type { AgentId, Plan } from "../types/events.ts";
import type { LogLine, RunState } from "../state/runState.ts";

const AGENT_NAMES: Record<AgentId, string> = {
  architect: "Architect",
  etl: "ETL Engineer",
  analytics: "Analytics Engineer",
  dashboard: "Dashboard Engineer",
};

/** mm:ss.mmm from run start, per docs/04-AGENT-RUNTIME.md. */
function stamp(at: number): string {
  const minutes = Math.floor(at / 60_000);
  const seconds = Math.floor((at % 60_000) / 1_000);
  const millis = at % 1_000;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(
    millis,
  ).padStart(3, "0")}`;
}

export function PlanProgress({ plan, run }: { plan: Plan; run: RunState }) {
  return (
    <section>
      <h2>{plan.title}</h2>
      {plan.phases.map((phase) => (
        <div key={phase.id}>
          <h3>
            Phase {phase.index}. {phase.title}
          </h3>
          <ul>
            {phase.task_ids.map((taskId) => {
              const task = plan.tasks[taskId];
              if (task === undefined) return null;
              // The status is whatever the backend last said it was. Nothing
              // here derives it.
              const status = run.taskStatus[taskId] ?? "pending";
              const attempt = run.taskAttempts[taskId];
              const metrics = run.taskMetrics[taskId];
              return (
                <li key={taskId}>
                  <strong>{task.id}</strong> {task.title} [{status}]
                  {attempt !== undefined && ` attempt ${attempt}`}
                  {" - "}
                  {AGENT_NAMES[task.agent_id]}
                  {task.depends_on.length > 0 && `, after ${task.depends_on.join(", ")}`}
                  {metrics !== undefined && `, ${metrics.duration_ms} ms`}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </section>
  );
}

export function AgentRail({ run }: { run: RunState }) {
  const agents = Object.values(run.agents);
  if (agents.length === 0) return null;
  return (
    <section>
      <h2>Agents</h2>
      <ul>
        {agents.map((agent) => (
          <li key={agent.agentId}>
            {AGENT_NAMES[agent.agentId]}: {agent.idle ? "idle" : "working"} (
            {agent.assignedTaskIds.join(", ")})
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ArtifactList({ run }: { run: RunState }) {
  const streams = Object.values(run.streaming);
  return (
    <section>
      <h2>Artifacts</h2>
      {run.artifacts.length === 0 && streams.length === 0 && (
        <p>Files appear here as agents produce them.</p>
      )}
      <ul>
        {run.artifacts.map((artifact) => (
          <li key={artifact.id}>
            {artifact.path} ({artifact.kind}, {artifact.bytes} bytes)
          </li>
        ))}
      </ul>
      {streams
        .filter((stream) => !stream.complete)
        .map((stream) => (
          <div key={stream.artifactId}>
            <p>
              Writing {stream.path} ({stream.text.length} characters so far)
            </p>
            <pre>{stream.text}</pre>
          </div>
        ))}
    </section>
  );
}

const WINDOW = 500;

export function LogStream({ logs }: { logs: readonly LogLine[] }) {
  if (logs.length === 0) return <p>The log fills as agents work.</p>;

  // Render window, not a filter. The whole log stays in the store.
  const visible = logs.slice(-WINDOW);
  return (
    <div>
      {visible.map((line) => (
        <div key={line.seq}>
          {stamp(line.at)} {line.agentId === null ? "runtime" : AGENT_NAMES[line.agentId]}{" "}
          {line.level === "info" ? "" : `[${line.level}] `}
          {line.message}
        </div>
      ))}
    </div>
  );
}
