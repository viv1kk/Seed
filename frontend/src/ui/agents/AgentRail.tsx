/**
 * The agent cards.
 *
 * Name, one-line role, current task, and a rolling activity line showing that
 * agent's most recent message. A 2px amber rule on the left edge while working,
 * idle cards at 60% opacity, `attempt 2 of 3` beside the task id during the
 * retry. Clicking a card filters the log to that agent.
 *
 * Each card subscribes per agent id, so one agent speaking does not re-render
 * the other three.
 */

import { memo } from "react";

import type { AgentId } from "../../types/events.ts";
import { AGENT_IDS, AGENT_NAMES, AGENT_ROLES } from "../present.ts";
import { useSeedStore } from "../useSeedStore.ts";
import { useViewStore, viewActions } from "../useViewStore.ts";

export function AgentRail() {
  const spawned = useSeedStore((state) => state.run.agents);
  const present = AGENT_IDS.filter((agentId) => spawned[agentId] !== undefined);

  if (present.length === 0) {
    return <p className="t-secondary px-3 py-2 text-chalk-dim">Agents appear when the run starts.</p>;
  }

  return (
    <ul className="flex flex-col gap-px">
      {present.map((agentId) => (
        <AgentCard key={agentId} agentId={agentId} />
      ))}
    </ul>
  );
}

const AgentCard = memo(function AgentCard({ agentId }: { agentId: AgentId }) {
  const idle = useSeedStore((state) => state.run.agents[agentId]?.idle ?? true);
  const filtered = useViewStore((state) => state.logAgent === agentId);

  // The task this agent is on, and the last thing it said. Both are reads of
  // state the backend put there; neither decides anything.
  const current = useSeedStore((state) => {
    const entry = Object.entries(state.run.taskStatus).find(
      ([taskId, status]) =>
        state.run.taskAgent[taskId] === agentId &&
        (status === "running" || status === "retrying"),
    );
    return entry?.[0] ?? null;
  });
  const attempt = useSeedStore((state) =>
    current === null ? undefined : state.run.taskAttempts[current],
  );
  const latest = useSeedStore((state) => {
    for (let index = state.run.logs.length - 1; index >= 0; index -= 1) {
      const line = state.run.logs[index];
      if (line !== undefined && line.agentId === agentId) return line.message;
    }
    return null;
  });

  const working = current !== null;

  return (
    <li>
      <button
        type="button"
        aria-pressed={filtered}
        onClick={() => viewActions().setLogAgent(filtered ? "all" : agentId)}
        className={`flex w-full flex-col items-start gap-0.5 border-l-2 px-3 py-2.5 text-left transition-opacity duration-150 hover:bg-ink-700 ${
          working ? "border-signal" : "border-transparent"
        } ${idle && !working ? "opacity-60" : "opacity-100"} ${filtered ? "bg-ink-700" : ""}`}
      >
        <div className="flex w-full items-baseline justify-between gap-2">
          <span className="t-body font-medium text-chalk">{AGENT_NAMES[agentId]}</span>
          <span className="t-secondary t-num shrink-0 text-chalk-dim">
            {current ?? (idle ? "idle" : "waiting")}
          </span>
        </div>

        {attempt !== undefined && attempt > 1 && (
          <span className="t-secondary text-signal">attempt {attempt} of 3</span>
        )}

        <span className="t-secondary w-full truncate text-chalk-dim">
          {latest ?? AGENT_ROLES[agentId]}
        </span>
      </button>
    </li>
  );
});
