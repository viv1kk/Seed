/**
 * The panel under the graph.
 *
 * At 1440 it is the log, and the agents and artifacts live in their own column
 * on the right. Below 1100 that column has nowhere to go, so its two panels
 * join the log here as tabs. Mobile is not a target; this is the safety net for
 * a projector that turns out to be narrower than the layout was drawn for.
 */

import { useState } from "react";

import { AgentRail } from "../agents/AgentRail.tsx";
import { ArtifactPanel } from "../artifacts/ArtifactPanel.tsx";
import { LogStream } from "../logs/LogStream.tsx";

type Tab = "log" | "agents" | "artifacts";

const TABS: readonly (readonly [Tab, string])[] = [
  ["log", "Log"],
  ["agents", "Agents"],
  ["artifacts", "Artifacts"],
];

export function BottomPanel({ tabbed }: { tabbed: boolean }) {
  const [tab, setTab] = useState<Tab>("log");

  if (!tabbed) return <LogStream />;

  return (
    <section className="flex min-h-0 flex-1 flex-col border-t border-ink-600">
      <div role="tablist" aria-label="Run detail" className="flex border-b border-ink-600">
        {TABS.map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={`t-panel-header px-3 py-1.5 ${
              tab === id
                ? "border-b-2 border-signal text-chalk"
                : "border-b-2 border-transparent text-chalk-dim hover:text-chalk"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {tab === "log" && <LogStream chrome={false} />}
        {tab === "agents" && <AgentRail />}
        {tab === "artifacts" && <ArtifactPanel />}
      </div>
    </section>
  );
}
