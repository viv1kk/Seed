/**
 * GENERATED FILE. DO NOT EDIT.
 *
 * Generated from backend/app/core/types.py, which is authoritative for the
 * event contract. See docs/03-EVENT-CONTRACT.md.
 *
 * Regenerate with:  make types
 */

/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "SeedEvent".
 */
export type SeedEvent =
  | RunStarted
  | PlanBuilt
  | AgentSpawned
  | TaskReady
  | TaskStarted
  | TaskProgress
  | LogEmitted
  | ArtifactStreaming
  | ArtifactChunk
  | ArtifactCreated
  | TaskFailed
  | TaskRetried
  | TaskCompleted
  | AgentIdle
  | RunCompleted
  | RunFailed;
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "QueryResult".
 */
export type QueryResult = AggregateReady | NoAnalyticalTable;
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "ParseResult".
 */
export type ParseResult = ParseSucceeded | ParseFailed;
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "AgentId".
 */
export type AgentId = "architect" | "etl" | "analytics" | "dashboard";
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "TaskStatus".
 */
export type TaskStatus = "pending" | "ready" | "running" | "retrying" | "completed" | "failed" | "skipped";
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "LogLevel".
 */
export type LogLevel = "debug" | "info" | "warn" | "error" | "success";
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "ArtifactKind".
 */
export type ArtifactKind = "code" | "dataset" | "table" | "dashboard" | "doc";

/**
 * Generated from backend/app/core/types.py. See docs/03-EVENT-CONTRACT.md. Do not hand-edit the TypeScript.
 */
export interface SeedContract {
  SeedEvent: SeedEvent;
  Plan: Plan;
  Artifact: Artifact;
  ArtifactBody: ArtifactBody;
  AggBundle: AggBundle;
  QueryResult: QueryResult;
  Filters: Filters;
  ParseResult: ParseResult;
  ExampleSummary: ExampleSummary;
  AgentId: AgentId;
  TaskStatus: TaskStatus;
  LogLevel: LogLevel;
  ArtifactKind: ArtifactKind;
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "RunStarted".
 */
export interface RunStarted {
  run_id: string;
  seq: number;
  at: number;
  type: "run.started";
  requirement_title: string;
  seed: number;
  speed: number;
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "PlanBuilt".
 */
export interface PlanBuilt {
  run_id: string;
  seq: number;
  at: number;
  type: "plan.built";
  plan: Plan;
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "Plan".
 */
export interface Plan {
  id: string;
  title: string;
  source_markdown: string;
  phases: Phase[];
  tasks: {
    [k: string]: Task;
  };
  order: string[];
  warnings: ParseWarning[];
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "Phase".
 */
export interface Phase {
  id: string;
  index: number;
  title: string;
  task_ids: string[];
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "Task".
 */
export interface Task {
  id: string;
  phase_id: string;
  title: string;
  agent_id: "architect" | "etl" | "analytics" | "dashboard";
  depends_on: string[];
  steps: TaskStep[];
  constraints: Constraint[];
  acceptance: string[];
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "TaskStep".
 */
export interface TaskStep {
  id: string;
  text: string;
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "Constraint".
 */
export interface Constraint {
  lang: string;
  code: string;
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "ParseWarning".
 */
export interface ParseWarning {
  code: "unassigned-agent" | "implicit-dependency" | "empty-task";
  task_id?: string | null;
  message: string;
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "AgentSpawned".
 */
export interface AgentSpawned {
  run_id: string;
  seq: number;
  at: number;
  type: "agent.spawned";
  agent_id: "architect" | "etl" | "analytics" | "dashboard";
  role: string;
  assigned_task_ids: string[];
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "TaskReady".
 */
export interface TaskReady {
  run_id: string;
  seq: number;
  at: number;
  type: "task.ready";
  task_id: string;
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "TaskStarted".
 */
export interface TaskStarted {
  run_id: string;
  seq: number;
  at: number;
  type: "task.started";
  task_id: string;
  agent_id: "architect" | "etl" | "analytics" | "dashboard";
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "TaskProgress".
 */
export interface TaskProgress {
  run_id: string;
  seq: number;
  at: number;
  type: "task.progress";
  task_id: string;
  step_id: string;
  pct: number;
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "LogEmitted".
 */
export interface LogEmitted {
  run_id: string;
  seq: number;
  at: number;
  type: "log.emitted";
  agent_id?: ("architect" | "etl" | "analytics" | "dashboard") | null;
  task_id?: string | null;
  level: "debug" | "info" | "warn" | "error" | "success";
  message: string;
  source: "agent" | "runtime";
}
/**
 * A code artifact is about to arrive, in chunks.
 *
 * Optional. A runner may emit `artifact.created` on its own, as before. When
 * it does stream, this opens the stream, `artifact.chunk` carries the text,
 * and `artifact.created` closes it with the finished metadata.
 *
 * This exists for the swap path rather than for the animation. A future
 * LlmRunner streams tokens because that is how a model emits code, so the
 * contract has to carry chunks from the start. Adding them later would either
 * break a frozen contract or leave the real runner behaving differently from
 * the simulated one, which is the one thing the seam must not do.
 *
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "ArtifactStreaming".
 */
export interface ArtifactStreaming {
  run_id: string;
  seq: number;
  at: number;
  type: "artifact.streaming";
  artifact_id: string;
  path: string;
  lang?: string | null;
  produced_by: "architect" | "etl" | "analytics" | "dashboard";
  task_id: string;
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "ArtifactChunk".
 */
export interface ArtifactChunk {
  run_id: string;
  seq: number;
  at: number;
  type: "artifact.chunk";
  artifact_id: string;
  text: string;
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "ArtifactCreated".
 */
export interface ArtifactCreated {
  run_id: string;
  seq: number;
  at: number;
  type: "artifact.created";
  artifact: Artifact;
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "Artifact".
 */
export interface Artifact {
  id: string;
  kind: "code" | "dataset" | "table" | "dashboard" | "doc";
  path: string;
  produced_by: "architect" | "etl" | "analytics" | "dashboard";
  task_id: string;
  bytes: number;
  lang?: string | null;
  rows?: number | null;
  columns?: string[] | null;
  preview?: string[][] | null;
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "TaskFailed".
 */
export interface TaskFailed {
  run_id: string;
  seq: number;
  at: number;
  type: "task.failed";
  task_id: string;
  agent_id: "architect" | "etl" | "analytics" | "dashboard";
  reason: string;
  recoverable: boolean;
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "TaskRetried".
 */
export interface TaskRetried {
  run_id: string;
  seq: number;
  at: number;
  type: "task.retried";
  task_id: string;
  agent_id: "architect" | "etl" | "analytics" | "dashboard";
  attempt: number;
  strategy: string;
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "TaskCompleted".
 */
export interface TaskCompleted {
  run_id: string;
  seq: number;
  at: number;
  type: "task.completed";
  task_id: string;
  agent_id: "architect" | "etl" | "analytics" | "dashboard";
  metrics: TaskMetrics;
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "TaskMetrics".
 */
export interface TaskMetrics {
  rows_in?: number | null;
  rows_out?: number | null;
  rows_dropped?: number | null;
  columns_added?: string[] | null;
  null_rates?: {
    [k: string]: number;
  } | null;
  duration_ms: number;
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "AgentIdle".
 */
export interface AgentIdle {
  run_id: string;
  seq: number;
  at: number;
  type: "agent.idle";
  agent_id: "architect" | "etl" | "analytics" | "dashboard";
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "RunCompleted".
 */
export interface RunCompleted {
  run_id: string;
  seq: number;
  at: number;
  type: "run.completed";
  duration_ms: number;
  artifact_ids: string[];
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "RunFailed".
 */
export interface RunFailed {
  run_id: string;
  seq: number;
  at: number;
  type: "run.failed";
  error: string;
}
/**
 * The contents of one artifact, fetched separately from the event stream.
 *
 * Code arrives as Pygments HTML rather than as source, because the
 * highlighting is done server side and there is no client-side highlighter in
 * this project. ``text`` carries the raw source for anything that wants it,
 * such as a copy action, and documents use it directly.
 *
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "ArtifactBody".
 */
export interface ArtifactBody {
  id: string;
  kind: "code" | "dataset" | "table" | "dashboard" | "doc";
  path: string;
  lang?: string | null;
  text?: string | null;
  html?: string | null;
  lines?: number | null;
  rows?: number | null;
  columns?: string[] | null;
  preview?: string[][] | null;
}
/**
 * Everything the dashboard draws, computed in one pass over one frame.
 *
 * One bundle per query, rather than an endpoint per surface. Every figure on
 * screen then comes from the same filtered frame at the same moment, so the
 * category totals and the region totals cannot disagree with the headline
 * because one of them was computed a request later.
 *
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "AggBundle".
 */
export interface AggBundle {
  kpis: Kpis;
  revenue_over_time: WeekPoint[];
  revenue_by_category: CategoryRow[];
  revenue_by_region: RegionRow[];
  top_products: ProductRow[];
  rows: number;
  computed_ms: number;
  filters: Filters;
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "Kpis".
 */
export interface Kpis {
  net_revenue: number;
  order_count: number;
  average_order_value: number;
  margin_pct: number;
  return_rate: number;
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "WeekPoint".
 */
export interface WeekPoint {
  week: string;
  net_revenue: number;
  order_count: number;
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "CategoryRow".
 */
export interface CategoryRow {
  category: string;
  net_revenue: number;
  margin_pct: number;
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "RegionRow".
 */
export interface RegionRow {
  region: string;
  net_revenue: number;
  share: number;
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "ProductRow".
 */
export interface ProductRow {
  sku: string;
  product_name: string;
  net_revenue: number;
  units: number;
  margin_pct: number;
}
/**
 * The cross-filter, applied to the retained derived frame.
 *
 * Sent by the dashboard to ``POST /api/runs/{id}/query`` and echoed back on
 * the bundle, so a response can be matched to the request that produced it
 * without the frontend tracking what it asked for.
 *
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "Filters".
 */
export interface Filters {
  date_from?: string | null;
  date_to?: string | null;
  category?: string | null;
  region?: string | null;
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "AggregateReady".
 */
export interface AggregateReady {
  status: "ok";
  bundle: AggBundle;
}
/**
 * The run has not produced a frame to aggregate, and may never.
 *
 * Two different situations, deliberately one answer. A query that arrives
 * before the analytics task has derived the table is early; a run whose
 * document never described an aggregate at all will never have one. Neither is
 * a fault, and the dashboard does the same thing in both cases: it does not
 * draw.
 *
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "NoAnalyticalTable".
 */
export interface NoAnalyticalTable {
  status: "no-analytical-table";
  message: string;
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "ParseSucceeded".
 */
export interface ParseSucceeded {
  status: "ok";
  plan: Plan;
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "ParseFailed".
 */
export interface ParseFailed {
  status: "error";
  errors: ParseError[];
  warnings: ParseWarning[];
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "ParseError".
 */
export interface ParseError {
  code: "unknown-dependency" | "self-dependency" | "dependency-cycle" | "task-outside-phase" | "no-tasks";
  task_id?: string | null;
  message: string;
}
/**
 * This interface was referenced by `SeedContract`'s JSON-Schema
 * via the `definition` "ExampleSummary".
 */
export interface ExampleSummary {
  id: string;
  title: string;
}
