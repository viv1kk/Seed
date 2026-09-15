/**
 * One task on the plan graph. Drawn the way a drawing expresses status.
 *
 * Planned work is a dashed outline, work in progress is a solid stroke in
 * survey amber with the dash marching, completed work is filled, faulted work
 * is struck through. The table is in docs/06-UI-SPEC.md and is followed exactly.
 *
 * Subscribes per task id: a log line arriving must not re-render the graph, so
 * this component reads only its own task's status, progress and attempt.
 */

import { memo } from "react";

import type { TaskStatus } from "../../types/events.ts";
import { AGENT_INITIALS, STATUS_WORDS } from "../present.ts";
import { useSeedStore } from "../useSeedStore.ts";
import { NODE_H, NODE_W } from "./layout.ts";

export interface TaskNodeProps {
  taskId: string;
  title: string;
  x: number;
  y: number;
  selected: boolean;
  /** 1 when nothing is hovered, dropped to 0.25 for tasks off the traced path. */
  emphasis: number;
  onSelect: (taskId: string) => void;
  onHover: (taskId: string | null) => void;
}

interface Skin {
  fill: string;
  stroke: string;
  strokeWidth: number;
  dash: string | undefined;
  marching: boolean;
  label: string;
  rule: string | null;
}

function skinFor(status: TaskStatus): Skin {
  switch (status) {
    case "pending":
      return {
        fill: "transparent",
        stroke: "var(--color-ink-600)",
        strokeWidth: 1,
        dash: "4 4",
        marching: false,
        label: "var(--color-chalk-dim)",
        rule: null,
      };
    case "ready":
      return {
        fill: "transparent",
        stroke: "var(--color-ink-600)",
        strokeWidth: 1,
        dash: undefined,
        marching: false,
        label: "var(--color-chalk)",
        rule: null,
      };
    case "running":
    case "retrying":
      return {
        fill: "transparent",
        stroke: "var(--color-signal)",
        strokeWidth: 2,
        dash: "8 8",
        marching: true,
        label: "var(--color-chalk)",
        rule: null,
      };
    case "completed":
      return {
        fill: "var(--color-ink-800)",
        stroke: "var(--color-ink-600)",
        strokeWidth: 1,
        dash: undefined,
        marching: false,
        label: "var(--color-chalk)",
        rule: "var(--color-verify)",
      };
    case "failed":
      return {
        fill: "transparent",
        stroke: "var(--color-fault)",
        strokeWidth: 2,
        dash: undefined,
        marching: false,
        label: "var(--color-fault-ink)",
        rule: null,
      };
    case "skipped":
      return {
        fill: "transparent",
        stroke: "var(--color-ink-600)",
        strokeWidth: 1,
        dash: "2 5",
        marching: false,
        label: "var(--color-chalk-dim)",
        rule: null,
      };
  }
}

export const TaskNode = memo(function TaskNode({
  taskId,
  title,
  x,
  y,
  selected,
  emphasis,
  onSelect,
  onHover,
}: TaskNodeProps) {
  const status = useSeedStore((state) => state.run.taskStatus[taskId] ?? "pending");
  const progress = useSeedStore((state) => state.run.taskProgress[taskId] ?? 0);
  const attempt = useSeedStore((state) => state.run.taskAttempts[taskId]);
  const agentId = useSeedStore((state) => state.run.taskAgent[taskId]);

  const skin = skinFor(status);
  const struck = status === "failed" || status === "skipped";
  const showAttempt = attempt !== undefined && attempt > 1 && status !== "completed";

  return (
    <g
      transform={`translate(${x} ${y})`}
      opacity={emphasis}
      style={{ transition: "opacity 120ms ease-out" }}
      onMouseEnter={() => onHover(taskId)}
      onMouseLeave={() => onHover(null)}
    >
      <rect
        width={NODE_W}
        height={NODE_H}
        rx={3}
        fill={skin.fill}
        stroke={skin.stroke}
        strokeWidth={skin.strokeWidth}
        strokeDasharray={skin.dash}
        className={skin.marching ? "seed-marching" : undefined}
        style={{ transition: "fill 150ms ease-out, stroke 150ms ease-out" }}
      />

      {/* The verify rule on the left edge of a finished node. */}
      {skin.rule !== null && (
        <rect x={0} y={0} width={2.5} height={NODE_H} fill={skin.rule} rx={1} />
      )}

      {/* Selection reads as a second, offset line, the way a drawing marks a
          detail rather than by changing the object's own weight. */}
      {selected && (
        <rect
          x={-4}
          y={-4}
          width={NODE_W + 8}
          height={NODE_H + 8}
          rx={5}
          fill="none"
          stroke="var(--color-chalk)"
          strokeWidth={1}
          opacity={0.55}
        />
      )}

      <text x={12} y={21} className="t-num" fontSize={11} fill="var(--color-chalk-dim)">
        {taskId}
      </text>

      {/* The top right corner carries the owning agent's initial, and gives it
          up to the attempt badge while a task is being retried. Both at once
          does not fit, and during a retry the attempt is the thing to read. */}
      {showAttempt ? (
        <>
          <rect
            x={NODE_W - 68}
            y={10}
            width={58}
            height={15}
            rx={7.5}
            fill="var(--color-signal)"
            opacity={0.18}
          />
          <text
            x={NODE_W - 39}
            y={21}
            textAnchor="middle"
            fontSize={10}
            fill="var(--color-signal)"
          >
            attempt {attempt}
          </text>
        </>
      ) : (
        agentId !== undefined && (
          <text
            x={NODE_W - 12}
            y={21}
            textAnchor="end"
            fontSize={11}
            fontWeight={600}
            fill="var(--color-chalk-dim)"
          >
            {AGENT_INITIALS[agentId]}
          </text>
        )
      )}

      <text
        x={12}
        y={41}
        className="t-node-label"
        fill={skin.label}
        textDecoration={struck ? "line-through" : undefined}
      >
        {clip(title, 25)}
      </text>

      {/* Step progress, along the bottom edge. */}
      <rect x={0} y={NODE_H - 2} width={NODE_W} height={2} fill="var(--color-ink-600)" />
      <rect
        x={0}
        y={NODE_H - 2}
        width={NODE_W * clamp01(progress)}
        height={2}
        fill={status === "completed" ? "var(--color-verify)" : "var(--color-signal)"}
        style={{ transition: "width 150ms linear" }}
      />

      {/* The hit target and the accessible name. A transparent rect over the
          whole node, so the pointer and the keyboard reach the same thing. */}
      <rect
        width={NODE_W}
        height={NODE_H}
        fill="transparent"
        role="button"
        tabIndex={-1}
        aria-label={`${taskId} ${title}, ${STATUS_WORDS[status]}`}
        style={{ cursor: "pointer" }}
        onClick={() => onSelect(taskId)}
      />
    </g>
  );
});

function clip(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, max - 1).trimEnd()}...`;
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}
