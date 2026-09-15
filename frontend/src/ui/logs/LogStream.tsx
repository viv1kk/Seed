/**
 * The log stream: fixed columns, level tinting, filters, autoscroll.
 *
 * Two things here are load-bearing rather than decorative, both from
 * docs/02-ARCHITECTURE.md. The render window is capped at 500 lines with the
 * rest retained in the store, and the events feeding it were already batched
 * onto animation frames by the subscription. At 200 lines a minute, dropping
 * either of those is visible.
 *
 * Lines append with no animation. Animated log lines look fake and cost frames.
 *
 * aria-live is scoped to error and success lines only. Announcing every debug
 * line would make the page unusable with a screen reader.
 */

import { useEffect, useMemo, useRef } from "react";

import type { LogLine } from "../../state/runState.ts";
import type { AgentFilter, LevelFilter } from "../../state/viewStore.ts";
import { AGENT_IDS, AGENT_NAMES, LEVEL_TEXT, LOG_LEVELS, stamp } from "../present.ts";
import { useSeedStore } from "../useSeedStore.ts";
import { useViewStore, viewActions } from "../useViewStore.ts";

const WINDOW = 500;

/**
 * `chrome` is false when the log is one tab among several and the panel around
 * it already carries a heading, so the header here would be a second one.
 */
export function LogStream({ chrome = true }: { chrome?: boolean }) {
  const logs = useSeedStore((state) => state.run.logs);
  const agent = useViewStore((state) => state.logAgent);
  const level = useViewStore((state) => state.logLevel);
  const released = useViewStore((state) => state.logReleased);

  const scroller = useRef<HTMLDivElement | null>(null);

  const visible = useMemo(() => {
    const matching = logs.filter(
      (line) =>
        (agent === "all" || line.agentId === agent) && (level === "all" || line.level === level),
    );
    // A render window, not a filter: the whole log stays in the store.
    return matching.slice(-WINDOW);
  }, [logs, agent, level]);

  // The retry is the most persuasive moment in the demo, and a filter can hide
  // it. Say so in the filter bar rather than swallowing it silently.
  const hidingRetry = useSeedStore((state) => {
    const retrying = Object.entries(state.run.taskStatus).some(
      ([taskId, status]) =>
        (status === "retrying" || status === "failed") && state.run.taskAgent[taskId] === "etl",
    );
    return retrying && (agent !== "all" || level !== "all") && agent !== "etl";
  });

  useEffect(() => {
    if (released) return;
    const element = scroller.current;
    if (element === null) return;
    element.scrollTop = element.scrollHeight;
  }, [visible, released]);

  const announce = visible
    .filter((line) => line.level === "error" || line.level === "success")
    .slice(-3);

  return (
    <section
      className={`flex min-h-0 flex-1 flex-col ${chrome ? "border-t border-ink-600" : ""}`}
    >
      <header className="flex items-center gap-3 border-b border-ink-600 px-3 py-1.5">
        {chrome && <h2 className="t-panel-header text-chalk-dim">Log</h2>}
        <div className="flex flex-1 items-center justify-end gap-2">
          <Select
            label="Filter by agent"
            value={agent}
            options={[
              ["all", "All agents"],
              ...AGENT_IDS.map((id) => [id, AGENT_NAMES[id]] as [AgentFilter, string]),
            ]}
            onChange={(next) => viewActions().setLogAgent(next as AgentFilter)}
          />
          <Select
            label="Filter by level"
            value={level}
            options={[
              ["all", "All levels"],
              ...LOG_LEVELS.map((id) => [id, id] as [LevelFilter, string]),
            ]}
            onChange={(next) => viewActions().setLogLevel(next as LevelFilter)}
          />
          <button
            type="button"
            onClick={() => void copyAll(visible)}
            className="t-secondary rounded-sm border border-ink-600 px-2 py-0.5 text-chalk-dim hover:border-chalk-dim hover:text-chalk"
          >
            Copy all
          </button>
        </div>
      </header>

      {hidingRetry && (
        <p className="t-secondary border-b border-ink-600 bg-ink-700 px-3 py-1.5 text-signal">
          The ETL Engineer is recovering from a failure. Clear the filter to watch.
        </p>
      )}

      <div className="relative min-h-0 flex-1">
        <div
          ref={scroller}
          className="h-full overflow-y-auto px-3 py-1.5"
          onScroll={(event) => {
            const element = event.currentTarget;
            const atBottom =
              element.scrollHeight - element.scrollTop - element.clientHeight < 24;
            if (atBottom === released) viewActions().setLogReleased(!atBottom);
          }}
        >
          {visible.length === 0 ? (
            <p className="t-secondary text-chalk-dim">The log fills as agents work.</p>
          ) : (
            visible.map((line) => <Line key={line.seq} line={line} />)
          )}
        </div>

        {released && (
          <button
            type="button"
            onClick={() => {
              viewActions().setLogReleased(false);
              const element = scroller.current;
              if (element !== null) element.scrollTop = element.scrollHeight;
            }}
            className="t-secondary absolute right-4 bottom-3 rounded-full border border-signal bg-ink-800 px-3 py-1 text-signal"
          >
            Jump to latest
          </button>
        )}
      </div>

      {/* Only outcomes are announced. See the note at the top of this file. */}
      <div aria-live="polite" className="sr-only">
        {announce.map((line) => (
          <p key={line.seq}>{line.message}</p>
        ))}
      </div>
    </section>
  );
}

function Line({ line }: { line: LogLine }) {
  const who = line.agentId === null ? "[kernel]" : AGENT_NAMES[line.agentId];
  const kernel = line.source === "runtime";
  return (
    <div className="t-log flex gap-3">
      <span className="w-[68px] shrink-0 text-chalk-dim opacity-70">{stamp(line.at)}</span>
      <span className={`w-[124px] shrink-0 truncate ${kernel ? "text-chalk-dim opacity-70" : "text-chalk-dim"}`}>
        {kernel ? "[kernel]" : who}
      </span>
      <span className={`min-w-0 ${kernel ? "text-chalk-dim" : LEVEL_TEXT[line.level]}`}>
        {line.message}
      </span>
    </div>
  );
}

function Select<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: readonly (readonly [T, string])[];
  onChange: (next: T) => void;
}) {
  return (
    <select
      aria-label={label}
      value={value}
      onChange={(event) => onChange(event.target.value as T)}
      className="t-secondary rounded-sm border border-ink-600 bg-ink-800 px-1.5 py-0.5 text-chalk-dim hover:text-chalk"
    >
      {options.map(([id, text]) => (
        <option key={id} value={id} className="bg-ink-800 text-chalk">
          {text}
        </option>
      ))}
    </select>
  );
}

async function copyAll(lines: readonly LogLine[]): Promise<void> {
  const text = lines
    .map(
      (line) =>
        `${stamp(line.at)}  ${line.agentId === null ? "[kernel]" : AGENT_NAMES[line.agentId]}  ${line.message}`,
    )
    .join("\n");
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // Clipboard access is denied in some contexts. Nothing to recover: the log
    // is on screen, and failing a run over a copy would be worse.
  }
}
