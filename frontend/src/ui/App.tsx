/**
 * The plan room.
 *
 * Three columns at 1440: the requirement as written, the plan graph over the
 * log, and the agents over the artifacts. On `run.completed` the requirement
 * and log columns recede and the dashboard takes the screen.
 *
 * This component owns the run's lifecycle wiring and nothing about its content.
 * Statuses, progress, metrics and artifacts all arrive as events and are
 * applied by the reducer; the dashboard's figures all arrive from
 * `POST /api/runs/{id}/query`. Nothing on this page is computed here.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { controlRun, createPlan, createRun, fetchExamples, queryRun } from "../api/client.ts";
import { subscribeToRun, type StreamHandle } from "../api/stream.ts";
import {
  forgetRun,
  planRequestFor,
  recallRun,
  rememberRun,
  sourceName,
  type Source,
} from "../state/session.ts";
import { seedStore } from "../state/store.ts";
import { viewStore } from "../state/viewStore.ts";
import type { AggBundle, ExampleSummary, Filters, ParseError, Plan } from "../types/events.ts";
import { AgentRail } from "./agents/AgentRail.tsx";
import { ArtifactPanel } from "./artifacts/ArtifactPanel.tsx";
import { ArtifactViewer, useOpenOnStream } from "./artifacts/ArtifactViewer.tsx";
import { RevenueDashboard } from "./dashboard/RevenueDashboard.tsx";
import { prefersReducedMotion } from "./dashboard/Headline.tsx";
import { Inspector } from "./graph/Inspector.tsx";
import { PlanGraph } from "./graph/PlanGraph.tsx";
import { BottomPanel } from "./shell/BottomPanel.tsx";
import { Header, type Phase } from "./shell/Header.tsx";
import { Intake } from "./shell/Intake.tsx";
import {
  ConnectionNotice,
  ParseErrors,
  PlanWarnings,
  RunOutcome,
} from "./shell/Notices.tsx";
import { RequirementColumn } from "./shell/RequirementColumn.tsx";
import { NARROW, useDelivery, useMediaQuery } from "./shell/useLayoutHints.ts";
import { useSeedStore } from "./useSeedStore.ts";
import { useViewStore, viewActions } from "./useViewStore.ts";

const DEFAULT_SEED = 4471;

/** Escape closes whatever is open, from anywhere on the page. */
export function useGlobalEscape(): void {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      const actions = viewActions();
      if (actions.openArtifactId !== null) actions.openArtifact(null);
      else if (actions.selectedTaskId !== null) actions.selectTask(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}


export function App() {
  const [examples, setExamples] = useState<ExampleSummary[]>([]);
  /** The document this plan came from: a bundled example, or the person's own. */
  const [source, setSource] = useState<Source | null>(null);
  /** What is in the intake box. Held here so the header's button can build it. */
  const [draft, setDraft] = useState("");
  const [draftName, setDraftName] = useState("pasted requirement");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [errors, setErrors] = useState<ParseError[]>([]);
  const [failure, setFailure] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [paused, setPaused] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [seed, setSeed] = useState(DEFAULT_SEED);
  const [bundle, setBundle] = useState<AggBundle | null>(null);
  const [querying, setQuerying] = useState(false);
  /** True once a completed run has told us it produced no analytical table. */
  const [noDashboard, setNoDashboard] = useState(false);
  const [showingDashboard, setShowingDashboard] = useState(true);

  const completed = useSeedStore((state) => state.run.completed);
  const runError = useSeedStore((state) => state.run.error);
  const durationMs = useSeedStore((state) => state.run.durationMs);
  const artifactCount = useSeedStore((state) => state.run.artifacts.length);
  const warnings = plan?.warnings ?? [];

  const selectedTaskId = useViewStore((state) => state.selectedTaskId);
  const openArtifactId = useViewStore((state) => state.openArtifactId);

  const stream = useRef<StreamHandle | null>(null);
  const restored = useRef(false);
  const narrow = useMediaQuery(NARROW);
  useOpenOnStream();
  useGlobalEscape();

  const watch = useCallback((id: string) => {
    stream.current?.close();
    stream.current = subscribeToRun(id, {
      onBatch: (events) => seedStore.getState().applyEvents(events),
      onError: setFailure,
      onOpen: () => setFailure(null),
    });
  }, []);

  useEffect(() => {
    fetchExamples()
      .then(setExamples)
      .catch(() => setFailure("Cannot reach the backend. Start it on port 8000."));
  }, []);

  // Rejoin whatever this tab was watching before the refresh. The stream
  // replays from seq=0, so the run is recovered in full rather than joined late.
  useEffect(() => {
    if (restored.current) return; // StrictMode runs effects twice in development
    restored.current = true;

    const watched = recallRun();
    if (watched === null) return;

    setSource(watched.source);
    setSpeed(watched.speed);
    if (watched.source.kind === "markdown") {
      setDraft(watched.source.text);
      setDraftName(watched.source.name);
    }
    // Re-parsed rather than cached: the plan is the backend's to derive, and
    // for a pasted document the text is the only thing this tab kept.
    createPlan(planRequestFor(watched.source))
      .then((result) => {
        if (result.status !== "ok") {
          forgetRun();
          return;
        }
        setPlan(result.plan);
        setRunId(watched.runId);
        seedStore.getState().reset();
        watch(watched.runId);
      })
      .catch(() => forgetRun());
  }, [watch]);

  useEffect(() => () => stream.current?.close(), []);

  const query = useCallback(
    (filters: Filters) => {
      if (runId === null) return;
      setQuerying(true);
      queryRun(runId, filters)
        .then((result) => {
          // A run whose document described no aggregate has no dashboard to
          // deliver. That is an outcome, not a fault: the run still built what
          // it was asked for, and the artifacts are in the tree.
          setNoDashboard(result.status === "no-analytical-table");
          setBundle(result.status === "ok" ? result.bundle : null);
        })
        .catch(() => setFailure("The dashboard could not be refreshed. Try the filter again."))
        .finally(() => setQuerying(false));
    },
    [runId],
  );

  // The unfiltered bundle comes from the same endpoint every cross-filter uses,
  // so the delivered dashboard and a filtered one are one code path on both
  // sides. `completed` is the backend's word, not a guess made here.
  useEffect(() => {
    if (runId === null || !completed) return;
    query({});
  }, [runId, completed, query]);

  /**
   * Parse a document into a plan.
   *
   * One path for a bundled example and for something the person pasted or
   * opened, because the parser has one path for them too. A rejected document
   * is a 200 carrying errors, not a failure: the run is refused by there being
   * no plan, and the intake box keeps its text so the line can be fixed.
   */
  const buildPlan = useCallback((next: Source) => {
    stream.current?.close();
    stream.current = null;
    forgetRun();
    seedStore.getState().reset();
    viewStore.getState().reset();
    setSource(next);
    setBundle(null);
    setNoDashboard(false);
    setRunId(null);
    setPaused(false);
    setPlan(null);
    setErrors([]);
    setFailure(null);
    setShowingDashboard(true);

    createPlan(planRequestFor(next))
      .then((result) => {
        if (result.status === "ok") setPlan(result.plan);
        else setErrors(result.errors);
      })
      .catch(() => setFailure("Cannot reach the backend. Start it on port 8000."));
  }, []);

  const buildFromDraft = useCallback(() => {
    if (draft.trim().length === 0) return;
    buildPlan({ kind: "markdown", text: draft, name: draftName });
  }, [draft, draftName, buildPlan]);

  /** Back to intake, with whatever was in the box still in it. */
  const newRequirement = useCallback(() => {
    if (runId !== null) void controlRun(runId, "cancel").catch(() => undefined);
    stream.current?.close();
    stream.current = null;
    forgetRun();
    seedStore.getState().reset();
    viewStore.getState().reset();
    setSource(null);
    setPlan(null);
    setErrors([]);
    setRunId(null);
    setPaused(false);
    setBundle(null);
    setNoDashboard(false);
    setFailure(null);
    setShowingDashboard(true);
  }, [runId]);

  const start = useCallback(() => {
    if (plan === null || source === null) return;
    // Replay always starts at seq 0, so the store has to start empty or every
    // line would be applied twice.
    seedStore.getState().reset();
    viewStore.getState().reset();
    setFailure(null);
    setBundle(null);
    setNoDashboard(false);
    setShowingDashboard(true);

    createRun(plan.id, speed, seed)
      .then(({ run_id }) => {
        setRunId(run_id);
        setPaused(false);
        rememberRun({ runId: run_id, source, speed });
        watch(run_id);
      })
      .catch(() => setFailure("The run could not be started. Check the backend and try again."));
  }, [plan, source, speed, seed, watch]);

  const togglePause = useCallback(() => {
    if (runId === null) return;
    controlRun(runId, paused ? "resume" : "pause")
      .then((state) => setPaused(state.paused))
      .catch(() => undefined);
  }, [runId, paused]);

  const reset = useCallback(() => {
    if (runId !== null) void controlRun(runId, "cancel").catch(() => undefined);
    stream.current?.close();
    stream.current = null;
    forgetRun();
    seedStore.getState().reset();
    viewStore.getState().reset();
    setRunId(null);
    setPaused(false);
    setBundle(null);
    setNoDashboard(false);
    setFailure(null);
    setShowingDashboard(true);
  }, [runId]);

  const changeSpeed = useCallback(
    (next: number) => {
      setSpeed(next);
      if (runId !== null) void controlRun(runId, "speed", next).catch(() => undefined);
    },
    [runId],
  );

  const phase: Phase = useMemo(() => {
    if (plan === null) return "idle";
    if (runId === null) return "planned";
    if (completed || runError !== null) return "done";
    return paused ? "paused" : "running";
  }, [plan, runId, completed, runError, paused]);

  // The completion transition. `delivery` is "dimming" for 250ms, then
  // "delivered", and the dashboard wipes up once it lands. Toggling back to the
  // run does not re-run it: the moment happens once.
  const delivery = useDelivery(completed && bundle !== null);
  const onDashboard = delivery === "delivered" && bundle !== null && showingDashboard;
  const dimming = delivery === "dimming";

  if (plan === null) {
    return (
      <div className="flex h-full flex-col">
        <Header
          requirementName={null}
          seed={seed}
          onSeedChange={setSeed}
          speed={speed}
          onSpeedChange={changeSpeed}
          phase="idle"
          primaryLabel="Build the plan"
          onPrimary={buildFromDraft}
          primaryDisabled={draft.trim().length === 0}
          onTogglePause={togglePause}
          onReset={reset}
        />
        <ConnectionNotice message={failure} />
        <ParseErrors errors={errors} />
        <main className="min-h-0 flex-1 overflow-y-auto">
          <Intake
            examples={examples}
            loadingExamples={examples.length === 0 && failure === null}
            draft={draft}
            onDraftChange={(text, name) => {
              setDraft(text);
              if (name !== undefined) setDraftName(name);
            }}
            onPickExample={(id) => buildPlan({ kind: "example", id })}
            onBuild={buildFromDraft}
            notice={
              errors.length > 0
                ? "Fix the lines above and build the plan again."
                : null
            }
          />
        </main>
      </div>
    );
  }

  return (
    <div className="relative flex h-full flex-col">
      <Header
        requirementName={source === null ? null : sourceName(source)}
        seed={seed}
        onSeedChange={setSeed}
        speed={speed}
        onSpeedChange={changeSpeed}
        phase={phase}
        primaryLabel="Start the run"
        onPrimary={start}
        primaryDisabled={phase === "running" || phase === "paused"}
        onTogglePause={togglePause}
        onReset={reset}
        extra={
          <div className="flex items-center gap-3">
            <RunOutcome
              completed={completed}
              durationMs={durationMs}
              artifactCount={artifactCount}
              rows={bundle?.rows ?? null}
              error={runError}
            />
            {noDashboard && (
              <span className="t-secondary text-chalk-dim">
                This requirement produced no analytical table, so there is no dashboard.
              </span>
            )}
            {completed && bundle !== null && (
              <button
                type="button"
                onClick={() => setShowingDashboard((shown) => !shown)}
                className="t-secondary rounded-sm border border-ink-600 px-2.5 py-0.5 text-chalk-dim hover:border-chalk-dim hover:text-chalk"
              >
                {showingDashboard ? "Show the run" : "Show the dashboard"}
              </button>
            )}
            <button
              type="button"
              onClick={newRequirement}
              className="t-secondary rounded-sm border border-ink-600 px-2.5 py-0.5 text-chalk-dim hover:border-chalk-dim hover:text-chalk"
            >
              Load another requirement
            </button>
          </div>
        }
      />

      <ConnectionNotice message={failure} />
      <ParseErrors errors={errors} />
      <PlanWarnings warnings={warnings} />

      <main
        className={`grid min-h-0 flex-1 transition-opacity duration-[250ms] ${
          onDashboard
            ? "grid-cols-[minmax(0,1fr)_300px] max-[1100px]:grid-cols-[minmax(0,1fr)]"
            : narrow
              ? "grid-cols-[280px_minmax(0,1fr)]"
              : "grid-cols-[320px_minmax(0,1fr)_300px]"
        }`}
        style={{ opacity: dimming ? 0.7 : 1 }}
      >
        {/* Left: the document, or the inspector over it. It recedes once the
            deliverable has landed. */}
        {!onDashboard && (
          <section
            className="min-h-0 overflow-hidden border-r border-ink-600"
            aria-label="Requirement"
          >
            {selectedTaskId === null ? (
              <RequirementColumn
                markdown={plan.source_markdown}
                plan={plan}
                selectedTaskId={null}
              />
            ) : (
              <Inspector plan={plan} taskId={selectedTaskId} />
            )}
          </section>
        )}

        {/* Centre: the graph over the log, or the deliverable. */}
        <section className="relative flex min-h-0 flex-col" aria-label="Run">
          {onDashboard && bundle !== null ? (
            <div className={prefersReducedMotion() ? "seed-fade h-full" : "seed-wipe h-full"}>
              <RevenueDashboard bundle={bundle} pending={querying} arriving onFilter={query} />
            </div>
          ) : (
            <>
              <PlanGraph plan={plan} />
              <div className="flex h-[34%] min-h-[160px] flex-col">
                <BottomPanel tabbed={narrow} />
              </div>
              {openArtifactId !== null && (
                <div className="absolute inset-0 z-10 bg-ink-800 shadow-2xl">
                  <ArtifactViewer artifactId={openArtifactId} />
                </div>
              )}
            </>
          )}
        </section>

        {/* Right: who is working, and what they have made. It stays through the
            transition, because "open clean.py" is the next question asked. */}
        {!narrow && (
          <aside
            className="flex min-h-0 flex-col border-l border-ink-600"
            aria-label="Agents and artifacts"
          >
            <h2 className="t-panel-header border-b border-ink-600 px-3 py-1.5 text-chalk-dim">
              Agents
            </h2>
            <div className="max-h-[45%] shrink-0 overflow-y-auto">
              <AgentRail />
            </div>
            <h2 className="t-panel-header border-t border-b border-ink-600 px-3 py-1.5 text-chalk-dim">
              Artifacts
            </h2>
            <div className="min-h-0 flex-1 overflow-y-auto">
              <ArtifactPanel />
            </div>
          </aside>
        )}
      </main>

      {/* On the dashboard the viewer opens over the whole console, so that
          "show me the code that produced this" does not mean going back. */}
      {onDashboard && openArtifactId !== null && (
        <div className="absolute inset-x-0 top-[104px] bottom-0 z-20 bg-ink-800 shadow-2xl">
          <ArtifactViewer artifactId={openArtifactId} />
        </div>
      )}
    </div>
  );
}
