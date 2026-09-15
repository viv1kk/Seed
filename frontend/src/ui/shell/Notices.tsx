/**
 * Banners and the empty state. Every string here is the exact one from
 * docs/06-UI-SPEC.md; they are design content, not filler.
 *
 * Parse problems are normal outcomes rather than server faults: the document
 * belongs to the person using this, and a broken `Depends on:` reference is an
 * ordinary thing to write. The errors say what went wrong and what to do next,
 * and the run is refused by there being no plan to start.
 */

import type { ExampleSummary, ParseError, ParseWarning } from "../../types/events.ts";

export function EmptyState({
  examples,
  onPick,
  loading,
}: {
  examples: readonly ExampleSummary[];
  onPick: (exampleId: string) => void;
  loading: boolean;
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-5 px-8 text-center">
      <div className="max-w-md">
        <h2 className="t-run-title text-chalk">Load a requirement to begin</h2>
        <p className="t-body pt-2 text-chalk-dim">
          Seed reads a Markdown requirements file, plans the work, and builds it. Pick one of
          the examples or paste your own.
        </p>
      </div>

      {loading ? (
        <p className="t-secondary text-chalk-dim">Loading examples.</p>
      ) : (
        <ul className="flex flex-wrap justify-center gap-2">
          {examples.map((example) => (
            <li key={example.id}>
              <button
                type="button"
                onClick={() => onPick(example.id)}
                className="t-body rounded-sm border border-ink-600 px-4 py-2 text-chalk hover:border-signal hover:text-signal"
              >
                {example.title}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ParseErrors({ errors }: { errors: readonly ParseError[] }) {
  if (errors.length === 0) return null;
  return (
    <div
      role="alert"
      className="border-b border-fault/40 bg-fault/10 px-5 py-2.5"
    >
      <h2 className="t-panel-header pb-1 text-fault-ink">This requirement cannot be run</h2>
      <ul className="flex flex-col gap-0.5">
        {errors.map((error, index) => (
          <li key={`${error.code}-${index}`} className="t-secondary text-chalk">
            {error.message}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function PlanWarnings({ warnings }: { warnings: readonly ParseWarning[] }) {
  const unassigned = warnings.filter((warning) => warning.code === "unassigned-agent");
  if (unassigned.length === 0) return null;
  return (
    <p className="t-secondary border-b border-signal/30 bg-signal/10 px-5 py-1.5 text-signal">
      {unassigned.length} tasks had no agent assigned. Seed inferred an owner from the task
      text.
    </p>
  );
}

export function ConnectionNotice({ message }: { message: string | null }) {
  if (message === null) return null;
  return (
    <p
      role="status"
      className="t-secondary border-b border-fault/40 bg-fault/10 px-5 py-1.5 text-fault-ink"
    >
      {message}
    </p>
  );
}

export function RunOutcome({
  completed,
  durationMs,
  artifactCount,
  rows,
  error,
}: {
  completed: boolean;
  durationMs: number | null;
  artifactCount: number;
  rows: number | null;
  error: string | null;
}) {
  if (error !== null) {
    return <span className="t-secondary text-fault-ink">{error}</span>;
  }
  if (!completed || durationMs === null) return null;
  return (
    <span className="t-secondary text-verify">
      Built in {readable(durationMs)}. {artifactCount} artifacts
      {rows === null ? "" : `, ${rows.toLocaleString("en-IN")} rows processed`}.
    </span>
  );
}

function readable(ms: number): string {
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}
