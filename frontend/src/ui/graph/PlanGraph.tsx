/**
 * The plan graph: the surface that proves the environment read the document.
 *
 * Custom SVG over a dagre layout, per docs/06-UI-SPEC.md. Pan with a drag, zoom
 * about the cursor with the wheel, clamped 0.5x to 2.5x, Fit to reset. Hovering
 * a node traces its dependency path. Arrow keys walk the graph, Enter opens the
 * inspector, Escape closes it.
 *
 * Auto-focus happens on one event only: a task failing outside the viewport.
 * Panning for any other reason is disorienting, and the spec says so.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { Plan } from "../../types/events.ts";
import { useSeedStore } from "../useSeedStore.ts";
import { useViewStore, viewActions } from "../useViewStore.ts";
import { GraphEdges } from "./GraphEdges.tsx";
import { GUTTER, layoutPlan, NODE_H, NODE_W, step } from "./layout.ts";
import { TaskNode } from "./TaskNode.tsx";

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 2.5;

/** Pixels of travel before a press counts as a pan rather than a click. */
const DRAG_THRESHOLD = 4;

interface Viewport {
  x: number;
  y: number;
  k: number;
}

export function PlanGraph({ plan }: { plan: Plan }) {
  const layout = useMemo(() => layoutPlan(plan), [plan]);
  const frame = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: 900, height: 520 });
  const [view, setView] = useState<Viewport>({ x: 0, y: 0, k: 1 });
  const drag = useRef<{
    x: number;
    y: number;
    startX: number;
    startY: number;
    capturing: boolean;
  } | null>(null);

  const selectedTaskId = useViewStore((state) => state.selectedTaskId);
  const hoveredTaskId = useViewStore((state) => state.hoveredTaskId);
  const failedTaskId = useSeedStore((state) => {
    const entries = Object.entries(state.run.taskStatus);
    return entries.find(([, status]) => status === "failed" || status === "retrying")?.[0] ?? null;
  });

  const fit = useCallback(() => {
    const k = clamp(
      Math.min(size.width / layout.width, size.height / layout.height, 1),
      MIN_ZOOM,
      MAX_ZOOM,
    );
    setView({
      x: (size.width - layout.width * k) / 2,
      y: Math.min(0, (size.height - layout.height * k) / 2),
      k,
    });
  }, [layout.width, layout.height, size.width, size.height]);

  // Measure the frame, and fit once the plan or the frame changes size.
  useEffect(() => {
    const element = frame.current;
    if (element === null) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry === undefined) return;
      setSize({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(fit, [fit]);

  // Wheel zoom about the cursor: the point under the pointer stays put.
  useEffect(() => {
    const element = frame.current;
    if (element === null) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const box = element.getBoundingClientRect();
      const px = event.clientX - box.left;
      const py = event.clientY - box.top;
      setView((current) => {
        const k = clamp(current.k * Math.exp(-event.deltaY / 400), MIN_ZOOM, MAX_ZOOM);
        const scale = k / current.k;
        return { k, x: px - (px - current.x) * scale, y: py - (py - current.y) * scale };
      });
    };
    element.addEventListener("wheel", onWheel, { passive: false });
    return () => element.removeEventListener("wheel", onWheel);
  }, []);

  /**
   * Bring a failing node into view, and only a failing one.
   *
   * The pan is skipped when the node is already on screen, because moving the
   * drawing under someone who is reading it is worse than leaving it still.
   */
  useEffect(() => {
    if (failedTaskId === null) return;
    const box = layout.nodes.get(failedTaskId);
    if (box === undefined) return;
    setView((current) => {
      const screenX = box.x * current.k + current.x;
      const screenY = box.y * current.k + current.y;
      const visible =
        screenX > 0 &&
        screenY > 0 &&
        screenX + NODE_W * current.k < size.width &&
        screenY + NODE_H * current.k < size.height;
      if (visible) return current;
      return {
        k: current.k,
        x: size.width / 2 - (box.x + NODE_W / 2) * current.k,
        y: size.height / 2 - (box.y + NODE_H / 2) * current.k,
      };
    });
  }, [failedTaskId, layout, size.width, size.height]);

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const keys: Record<string, "up" | "down" | "left" | "right"> = {
      ArrowUp: "up",
      ArrowDown: "down",
      ArrowLeft: "left",
      ArrowRight: "right",
    };
    const direction = keys[event.key];
    const actions = viewActions();

    if (direction !== undefined) {
      event.preventDefault();
      const from = selectedTaskId ?? plan.order[0];
      if (from === undefined) return;
      const next = selectedTaskId === null ? from : step(plan, layout, from, direction);
      if (next !== null) actions.selectTask(next);
      return;
    }
    if (event.key === "Enter" && selectedTaskId !== null) {
      event.preventDefault();
      actions.selectTask(selectedTaskId);
    }
    if (event.key === "Escape") {
      actions.selectTask(null);
    }
  };

  const traced = hoveredTaskId ?? selectedTaskId;
  const emphasisFor = (taskId: string): number => {
    if (traced === null) return 1;
    if (taskId === traced) return 1;
    if (layout.ancestors.get(traced)?.has(taskId) === true) return 0.7;
    if (layout.descendants.get(traced)?.has(taskId) === true) return 0.5;
    return 0.25;
  };

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div
        ref={frame}
        tabIndex={0}
        role="application"
        aria-label="Plan graph. Arrow keys move between tasks, Enter opens a task."
        className="min-h-0 flex-1 cursor-grab overflow-hidden active:cursor-grabbing"
        onKeyDown={onKeyDown}
        onPointerDown={(event) => {
          drag.current = {
            x: view.x,
            y: view.y,
            startX: event.clientX,
            startY: event.clientY,
            capturing: false,
          };
        }}
        onPointerMove={(event) => {
          const from = drag.current;
          if (from === null) return;
          const dx = event.clientX - from.startX;
          const dy = event.clientY - from.startY;

          // Capture only once the pointer has actually travelled. Capturing on
          // pointerdown retargets the whole gesture to this element, and the
          // browser then fires `click` here rather than on the node underneath,
          // so every click on a task would be swallowed by the pan handler.
          if (!from.capturing) {
            if (Math.abs(dx) + Math.abs(dy) < DRAG_THRESHOLD) return;
            from.capturing = true;
            event.currentTarget.setPointerCapture(event.pointerId);
          }

          setView((current) => ({ ...current, x: from.x + dx, y: from.y + dy }));
        }}
        onPointerUp={(event) => {
          if (drag.current?.capturing === true) {
            event.currentTarget.releasePointerCapture(event.pointerId);
          }
          drag.current = null;
        }}
        onPointerCancel={() => {
          drag.current = null;
        }}
      >
        <svg width={size.width} height={size.height} role="presentation">
          <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
            {layout.bands.map((band) => (
              <g key={band.phaseId}>
                <line
                  x1={0}
                  y1={band.y}
                  x2={layout.width}
                  y2={band.y}
                  stroke="var(--color-ink-600)"
                  strokeWidth={1}
                />
                <text
                  x={16}
                  y={band.y + 24}
                  className="t-panel-header"
                  fill="var(--color-chalk-dim)"
                >
                  Phase {band.index}
                </text>
                <text
                  x={16}
                  y={band.y + 42}
                  className="t-secondary"
                  fill="var(--color-chalk-dim)"
                  opacity={0.75}
                >
                  {band.title.length > 13 ? `${band.title.slice(0, 12)}...` : band.title}
                </text>
                <line
                  x1={GUTTER}
                  y1={band.y}
                  x2={GUTTER}
                  y2={band.y + band.height}
                  stroke="var(--color-ink-600)"
                  strokeWidth={1}
                  opacity={0.5}
                />
              </g>
            ))}

            <GraphEdges edges={layout.edges} traced={traced} layout={layout} />

            {[...layout.nodes.values()].map((box) => (
              <TaskNode
                key={box.taskId}
                taskId={box.taskId}
                title={plan.tasks[box.taskId]?.title ?? box.taskId}
                x={box.x}
                y={box.y}
                selected={selectedTaskId === box.taskId}
                emphasis={emphasisFor(box.taskId)}
                onSelect={viewActions().selectTask}
                onHover={viewActions().hoverTask}
              />
            ))}
          </g>
        </svg>
      </div>

      <div className="absolute right-3 bottom-3 flex gap-1.5">
        <GraphButton label="Fit" onClick={fit} />
        <GraphButton
          label="Zoom out"
          symbol="-"
          onClick={() => setView((c) => ({ ...c, k: clamp(c.k / 1.2, MIN_ZOOM, MAX_ZOOM) }))}
        />
        <GraphButton
          label="Zoom in"
          symbol="+"
          onClick={() => setView((c) => ({ ...c, k: clamp(c.k * 1.2, MIN_ZOOM, MAX_ZOOM) }))}
        />
      </div>
    </div>
  );
}

function GraphButton({
  label,
  symbol,
  onClick,
}: {
  label: string;
  symbol?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="t-secondary min-w-8 rounded-sm border border-ink-600 bg-ink-800 px-2 py-1 text-chalk-dim hover:border-chalk-dim hover:text-chalk"
    >
      {symbol ?? label}
    </button>
  );
}

function clamp(value: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, value));
}
