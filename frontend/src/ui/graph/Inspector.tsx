/**
 * The node inspector, opened over the requirement column.
 *
 * The task as written in the source document, its steps with per-step status,
 * its constraints, its acceptance criteria, its metrics once complete, its
 * artifacts, and the log filtered to that task alone. One panel that answers
 * almost every question a client asks mid-run, which is why it earns the space.
 *
 * Everything shown arrives on an event or in the plan. Per-step status is the
 * one thing that looks derived and is not: `task.progress` carries the step id
 * the backend is on, and a step is done when a later step has been reported.
 */

import { useMemo } from "react";

import type { Plan } from "../../types/events.ts";
import { AGENT_NAMES, bytes, count, duration, percent, stamp, STATUS_WORDS } from "../present.ts";
import { useSeedStore } from "../useSeedStore.ts";
import { viewActions } from "../useViewStore.ts";

export function Inspector({ plan, taskId }: { plan: Plan; taskId: string }) {
  const task = plan.tasks[taskId];
  const status = useSeedStore((state) => state.run.taskStatus[taskId] ?? "pending");
  const metrics = useSeedStore((state) => state.run.taskMetrics[taskId]);
  const attempt = useSeedStore((state) => state.run.taskAttempts[taskId]);
  const progress = useSeedStore((state) => state.run.taskProgress[taskId] ?? 0);
  // Both of these select a stable reference and narrow it in a memo. A selector
  // that returns a fresh array on every call never compares equal, and the
  // component re-renders until React gives up: "maximum update depth exceeded".
  const allArtifacts = useSeedStore((state) => state.run.artifacts);
  const logs = useSeedStore((state) => state.run.logs);
  const artifacts = useMemo(
    () => allArtifacts.filter((artifact) => artifact.task_id === taskId),
    [allArtifacts, taskId],
  );
  const lines = useMemo(
    () => logs.filter((line) => line.taskId === taskId).slice(-60),
    [logs, taskId],
  );

  if (task === undefined) return null;

  return (
    <aside
      className="flex h-full flex-col overflow-y-auto bg-ink-800"
      aria-label={`Task ${taskId}`}
    >
      <header className="sticky top-0 flex items-start gap-3 border-b border-ink-600 bg-ink-800 px-4 py-3">
        <div className="min-w-0 flex-1">
          <div className="t-secondary text-chalk-dim">
            <span className="t-num">{task.id}</span>
            <span className="mx-2">·</span>
            {AGENT_NAMES[task.agent_id]}
          </div>
          <h2 className="t-body font-medium text-chalk">{task.title}</h2>
        </div>
        <button
          type="button"
          onClick={() => viewActions().selectTask(null)}
          className="t-secondary rounded-sm px-2 py-1 text-chalk-dim hover:text-chalk"
        >
          Close
        </button>
      </header>

      <div className="flex flex-col gap-5 px-4 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill status={STATUS_WORDS[status]} />
          {attempt !== undefined && attempt > 1 && (
            <span className="t-secondary text-signal">attempt {attempt} of 3</span>
          )}
          {task.depends_on.length > 0 && (
            <span className="t-secondary text-chalk-dim">
              after <span className="t-num">{task.depends_on.join(", ")}</span>
            </span>
          )}
        </div>

        <Section title="Steps">
          <ol className="flex flex-col gap-1.5">
            {task.steps.map((step, index) => {
              const done = progress >= (index + 1) / task.steps.length - 0.001;
              const active = !done && progress >= index / task.steps.length - 0.001;
              return (
                <li key={step.id} className="t-secondary flex gap-2.5">
                  <span
                    aria-hidden
                    className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                      done ? "bg-verify" : active ? "bg-signal" : "bg-ink-600"
                    }`}
                  />
                  <span className={done || active ? "text-chalk" : "text-chalk-dim"}>
                    {step.text}
                  </span>
                </li>
              );
            })}
          </ol>
        </Section>

        {task.constraints.length > 0 && (
          <Section title="Constraints">
            {task.constraints.map((constraint, index) => (
              <pre
                key={index}
                className="t-log overflow-x-auto rounded-sm border border-ink-600 bg-ink-900 p-2.5 text-chalk-dim"
              >
                {constraint.code.trimEnd()}
              </pre>
            ))}
          </Section>
        )}

        {task.acceptance.length > 0 && (
          <Section title="Acceptance">
            <ul className="flex flex-col gap-2">
              {task.acceptance.map((criterion, index) => (
                <li
                  key={index}
                  className="t-secondary border-l-2 border-ink-600 pl-2.5 text-chalk-dim"
                >
                  {criterion}
                </li>
              ))}
            </ul>
          </Section>
        )}

        {metrics !== undefined && (
          <Section title="Measured">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5">
              <Measure label="Took" value={duration(metrics.duration_ms)} />
              {metrics.rows_in != null && (
                <Measure label="Rows in" value={count(metrics.rows_in)} />
              )}
              {metrics.rows_out != null && (
                <Measure label="Rows out" value={count(metrics.rows_out)} />
              )}
              {metrics.rows_dropped != null && (
                <Measure label="Dropped" value={count(metrics.rows_dropped)} />
              )}
              {metrics.columns_added != null && metrics.columns_added.length > 0 && (
                <Measure
                  label="Columns added"
                  value={String(metrics.columns_added.length)}
                  title={metrics.columns_added.join(", ")}
                />
              )}
              {metrics.null_rates != null &&
                Object.entries(metrics.null_rates).map(([column, rate]) => (
                  <Measure key={column} label={`${column} nulls`} value={percent(rate)} />
                ))}
            </dl>
          </Section>
        )}

        {artifacts.length > 0 && (
          <Section title="Produced">
            <ul className="flex flex-col gap-1">
              {artifacts.map((artifact) => (
                <li key={artifact.id}>
                  <button
                    type="button"
                    onClick={() => viewActions().openArtifact(artifact.id)}
                    className="t-secondary w-full text-left text-chalk-dim hover:text-chalk"
                  >
                    <span className="t-num">{artifact.path}</span>
                    <span className="ml-2 opacity-60">{bytes(artifact.bytes)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </Section>
        )}

        <Section title="Log">
          {lines.length === 0 ? (
            <p className="t-secondary text-chalk-dim">This task has not started.</p>
          ) : (
            <div className="flex flex-col">
              {lines.map((line) => (
                <div key={line.seq} className="t-log flex gap-2">
                  <span className="shrink-0 text-chalk-dim opacity-70">{stamp(line.at)}</span>
                  <span
                    className={
                      line.source === "runtime" ? "text-chalk-dim" : "text-chalk opacity-90"
                    }
                  >
                    {line.message}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Section>
      </div>
    </aside>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="t-panel-header text-chalk-dim">{title}</h3>
      {children}
    </section>
  );
}

function Measure({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2" title={title}>
      <dt className="t-secondary text-chalk-dim">{label}</dt>
      <dd className="t-secondary t-num text-chalk">{value}</dd>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const tone: Record<string, string> = {
    running: "border-signal text-signal",
    retrying: "border-signal text-signal",
    completed: "border-verify text-verify",
    failed: "border-fault text-fault-ink",
  };
  return (
    <span
      className={`t-secondary rounded-full border px-2 py-0.5 ${
        tone[status] ?? "border-ink-600 text-chalk-dim"
      }`}
    >
      {status}
    </span>
  );
}
