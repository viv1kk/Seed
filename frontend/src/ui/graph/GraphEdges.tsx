/**
 * The connectors between tasks.
 *
 * Chalk at 40%, brightening to the signal colour when the source has completed
 * and the target has become ready, which is the moment the dependency is
 * actually discharged. Tracing a node dims everything off its path.
 *
 * Separate from PlanGraph so that the statuses these read do not re-render the
 * pan and zoom state around them.
 */

import { memo } from "react";

import { useSeedStore } from "../useSeedStore.ts";
import type { EdgePath, GraphLayout } from "./layout.ts";

export interface GraphEdgesProps {
  edges: readonly EdgePath[];
  /** The task being traced, from hover or selection. */
  traced: string | null;
  layout: GraphLayout;
}

export const GraphEdges = memo(function GraphEdges({ edges, traced, layout }: GraphEdgesProps) {
  const statuses = useSeedStore((state) => state.run.taskStatus);

  return (
    <g fill="none">
      {edges.map((edge) => {
        const sourceDone = statuses[edge.from] === "completed";
        const targetWaiting = statuses[edge.to] === "pending";
        const live = sourceDone && !targetWaiting;
        const onPath = traced === null || tracedThrough(layout, traced, edge);

        return (
          <path
            key={edge.id}
            d={edge.d}
            stroke={live ? "var(--color-signal)" : "var(--color-chalk)"}
            strokeWidth={live ? 1.5 : 1}
            opacity={(live ? 0.75 : 0.4) * (onPath ? 1 : 0.25)}
            style={{ transition: "opacity 120ms ease-out, stroke 150ms ease-out" }}
          />
        );
      })}
    </g>
  );
});

/** True when both ends of the edge sit on the traced task's dependency path. */
function tracedThrough(layout: GraphLayout, traced: string, edge: EdgePath): boolean {
  const up = layout.ancestors.get(traced);
  const down = layout.descendants.get(traced);
  const onTrace = (taskId: string): boolean =>
    taskId === traced || up?.has(taskId) === true || down?.has(taskId) === true;
  return onTrace(edge.from) && onTrace(edge.to);
}
