/**
 * Node positions for the plan graph. Pure: a Plan in, geometry out.
 *
 * dagre ranks the nodes; this file arranges the ranks into phase bands and
 * routes the edges. Custom SVG draws the result, per docs/06-UI-SPEC.md. React
 * Flow would fight the drawing aesthetic and, for seven to fifteen nodes, its
 * pan, zoom and minimap are not worth the weight.
 *
 * One dagre pass per phase rather than one for the whole graph. The spec puts
 * phases in horizontal bands and ranks within the band, and laying each band
 * out on its own is the direct way to get that: a band's height is then its own
 * business and no cross-phase edge can drag a node out of its band.
 *
 * Nothing here reads run state. Geometry is a function of the plan, so it is
 * computed once when the plan arrives and not again as statuses change.
 */

import dagre from "dagre";

import type { Plan } from "../../types/events.ts";

export const NODE_W = 178;
export const NODE_H = 58;

/** Room in the left margin for the phase name, set beside its band. */
export const GUTTER = 104;

const BAND_PAD_TOP = 30;
const BAND_PAD_BOTTOM = 24;
const MARGIN_X = 24;
const MARGIN_BOTTOM = 20;

export interface NodeBox {
  taskId: string;
  x: number;
  y: number;
}

export interface Band {
  phaseId: string;
  index: number;
  title: string;
  y: number;
  height: number;
}

export interface EdgePath {
  id: string;
  from: string;
  to: string;
  /** An SVG path, orthogonal: down, across, down. */
  d: string;
}

export interface GraphLayout {
  nodes: Map<string, NodeBox>;
  bands: Band[];
  edges: EdgePath[];
  width: number;
  height: number;
  /** Ancestors and descendants per task, for the hover trace. */
  ancestors: Map<string, Set<string>>;
  descendants: Map<string, Set<string>>;
}

export function layoutPlan(plan: Plan): GraphLayout {
  const nodes = new Map<string, NodeBox>();
  const bands: Band[] = [];
  let cursorY = 0;
  let widest = 0;

  for (const phase of plan.phases) {
    const placed = layoutBand(plan, phase.task_ids);
    const top = cursorY;

    for (const box of placed.boxes) {
      nodes.set(box.taskId, {
        taskId: box.taskId,
        x: GUTTER + MARGIN_X + box.x,
        y: top + BAND_PAD_TOP + box.y,
      });
    }

    const height = BAND_PAD_TOP + placed.height + BAND_PAD_BOTTOM;
    bands.push({
      phaseId: phase.id,
      index: phase.index,
      title: phase.title,
      y: top,
      height,
    });
    cursorY = top + height;
    widest = Math.max(widest, GUTTER + MARGIN_X + placed.width + MARGIN_X);
  }

  return {
    nodes,
    bands,
    edges: routeEdges(plan, nodes),
    width: Math.max(widest, GUTTER + 320),
    height: cursorY + MARGIN_BOTTOM,
    ancestors: relatives(plan, "up"),
    descendants: relatives(plan, "down"),
  };
}

interface BandResult {
  boxes: NodeBox[];
  width: number;
  height: number;
}

/**
 * One band, laid out by dagre over the edges that stay inside it.
 *
 * Cross-phase edges are left out on purpose. They are drawn, but they must not
 * influence ranking, or a task would be pushed down the band to sit under a
 * parent that is not in the band at all.
 */
function layoutBand(plan: Plan, taskIds: readonly string[]): BandResult {
  const inside = new Set(taskIds);
  const graph = new dagre.graphlib.Graph();
  graph.setGraph({ rankdir: "TB", nodesep: 30, ranksep: 40, marginx: 0, marginy: 0 });
  graph.setDefaultEdgeLabel(() => ({}));

  for (const taskId of taskIds) {
    graph.setNode(taskId, { width: NODE_W, height: NODE_H });
  }
  for (const taskId of taskIds) {
    const task = plan.tasks[taskId];
    if (task === undefined) continue;
    for (const parent of task.depends_on) {
      if (inside.has(parent)) graph.setEdge(parent, taskId);
    }
  }

  dagre.layout(graph);

  const boxes: NodeBox[] = [];
  let width = 0;
  let height = 0;
  for (const taskId of taskIds) {
    // dagre reports centres; everything downstream wants top-left corners.
    const placed = graph.node(taskId) as { x: number; y: number } | undefined;
    const centreX = placed?.x ?? NODE_W / 2;
    const centreY = placed?.y ?? NODE_H / 2;
    const x = centreX - NODE_W / 2;
    const y = centreY - NODE_H / 2;
    boxes.push({ taskId, x, y });
    width = Math.max(width, x + NODE_W);
    height = Math.max(height, y + NODE_H);
  }
  return { boxes, width, height };
}

/**
 * Orthogonal connectors: out of the source's bottom edge, across at the
 * midpoint, into the target's top edge. Drawing-office corners, not curves.
 *
 * An edge that runs upwards, which a dependency never should but a hand-edited
 * document can produce, still draws: it leaves the bottom and arrives at the
 * top, and the midpoint simply sits between them.
 */
function routeEdges(plan: Plan, nodes: Map<string, NodeBox>): EdgePath[] {
  const edges: EdgePath[] = [];
  for (const taskId of Object.keys(plan.tasks)) {
    const task = plan.tasks[taskId];
    if (task === undefined) continue;
    for (const parent of task.depends_on) {
      const from = nodes.get(parent);
      const to = nodes.get(taskId);
      if (from === undefined || to === undefined) continue;

      const x1 = from.x + NODE_W / 2;
      const y1 = from.y + NODE_H;
      const x2 = to.x + NODE_W / 2;
      const y2 = to.y;
      const midY = (y1 + y2) / 2;
      const d =
        x1 === x2
          ? `M ${x1} ${y1} L ${x2} ${y2}`
          : `M ${x1} ${y1} L ${x1} ${midY} L ${x2} ${midY} L ${x2} ${y2}`;
      edges.push({ id: `${parent}->${taskId}`, from: parent, to: taskId, d });
    }
  }
  return edges;
}

/**
 * Transitive ancestors or descendants of every task.
 *
 * Used by the hover trace, which is the thing that makes a DAG readable in a
 * second. Computed once with the layout rather than walked on every mouse move.
 */
function relatives(plan: Plan, direction: "up" | "down"): Map<string, Set<string>> {
  const adjacency = new Map<string, string[]>();
  for (const taskId of Object.keys(plan.tasks)) adjacency.set(taskId, []);

  for (const taskId of Object.keys(plan.tasks)) {
    const task = plan.tasks[taskId];
    if (task === undefined) continue;
    for (const parent of task.depends_on) {
      if (!adjacency.has(parent)) continue;
      if (direction === "up") adjacency.get(taskId)?.push(parent);
      else adjacency.get(parent)?.push(taskId);
    }
  }

  const out = new Map<string, Set<string>>();
  for (const taskId of adjacency.keys()) {
    const seen = new Set<string>();
    const stack = [...(adjacency.get(taskId) ?? [])];
    while (stack.length > 0) {
      const next = stack.pop();
      if (next === undefined || seen.has(next)) continue;
      seen.add(next);
      stack.push(...(adjacency.get(next) ?? []));
    }
    out.set(taskId, seen);
  }
  return out;
}

/**
 * The task reached by an arrow key, or null at the edge of the graph.
 *
 * Up and down walk dependencies, which is what the arrows mean on a DAG drawn
 * top to bottom. Left and right move along the band by horizontal position, so
 * two tasks that can run at the same time are one key apart.
 */
export function step(
  plan: Plan,
  layout: GraphLayout,
  from: string,
  key: "up" | "down" | "left" | "right",
): string | null {
  const here = layout.nodes.get(from);
  if (here === undefined) return null;

  if (key === "up" || key === "down") {
    const task = plan.tasks[from];
    const candidates =
      key === "up"
        ? (task?.depends_on ?? [])
        : Object.keys(plan.tasks).filter((id) => plan.tasks[id]?.depends_on.includes(from));
    return nearestByX(layout, here, candidates);
  }

  const sameRow = [...layout.nodes.values()].filter(
    (box) => box.taskId !== from && Math.abs(box.y - here.y) < NODE_H / 2,
  );
  const side = sameRow.filter((box) => (key === "left" ? box.x < here.x : box.x > here.x));
  side.sort((a, b) => Math.abs(a.x - here.x) - Math.abs(b.x - here.x));
  return side[0]?.taskId ?? null;
}

function nearestByX(
  layout: GraphLayout,
  here: NodeBox,
  candidates: readonly string[],
): string | null {
  let best: string | null = null;
  let bestDistance = Infinity;
  for (const taskId of candidates) {
    const box = layout.nodes.get(taskId);
    if (box === undefined) continue;
    const distance = Math.abs(box.x - here.x);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = taskId;
    }
  }
  return best;
}
