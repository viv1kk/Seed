/**
 * Phase 2 shell. Deliberately unstyled.
 *
 * Load an example, build the plan, start the run, and watch it over SSE. The
 * plan room arrives in phase 4 and starting on it now is the failure mode the
 * implementation plan warns about.
 *
 * Nothing here decides anything about the run. Statuses, progress and metrics
 * all arrive as events; this only draws them and sends control actions back.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { controlRun, createPlan, createRun, fetchExamples } from "../api/client.ts";
import { subscribeToRun, type StreamHandle } from "../api/stream.ts";
import { forgetRun, recallRun, rememberRun } from "../state/session.ts";
import { seedStore } from "../state/store.ts";
import type { ExampleSummary, ParseError, Plan } from "../types/events.ts";
import { PlanView } from "./PlanView.tsx";
import { AgentRail, ArtifactList, LogStream, PlanProgress } from "./RunView.tsx";
import { useSeedStore } from "./useSeedStore.ts";

const SPEEDS = [1, 2, 5] as const;

export function App() {
  const [examples, setExamples] = useState<ExampleSummary[]>([]);
  const [exampleId, setExampleId] = useState<string | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [errors, setErrors] = useState<ParseError[]>([]);
  const [failure, setFailure] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [paused, setPaused] = useState(false);
  const [speed, setSpeed] = useState<number>(1);
  const [rejoined, setRejoined] = useState(false);

  const run = useSeedStore((state) => state.run);
  const stream = useRef<StreamHandle | null>(null);
  const restored = useRef(false);

  const watch = useCallback((id: string) => {
    stream.current?.close();
    stream.current = subscribeToRun(id, {
      onBatch: (events) => seedStore.getState().applyEvents(events),
      onError: setFailure,
    });
  }, []);

  useEffect(() => {
    fetchExamples()
      .then(setExamples)
      .catch(() => setFailure("Cannot reach the backend. Start it on port 8000."));
  }, []);

  // Rejoin whatever this tab was watching before the refresh. The stream
  // replays from seq=0, so the run is recovered in full rather than joined
  // late; the plan is rebuilt from the same document for the same reason.
  useEffect(() => {
    if (restored.current) return; // StrictMode runs effects twice in development
    restored.current = true;

    const watched = recallRun();
    if (watched === null) return;

    setExampleId(watched.exampleId);
    setSpeed(watched.speed);
    createPlan({ example_id: watched.exampleId })
      .then((result) => {
        if (result.status !== "ok") {
          forgetRun();
          return;
        }
        setPlan(result.plan);
        setRunId(watched.runId);
        setRejoined(true);
        seedStore.getState().reset();
        watch(watched.runId);
      })
      .catch(() => forgetRun());
  }, [watch]);

  useEffect(() => () => stream.current?.close(), []);

  const buildPlan = useCallback((id: string) => {
    stream.current?.close();
    stream.current = null;
    forgetRun();
    seedStore.getState().reset();
    setExampleId(id);
    setRunId(null);
    setRejoined(false);
    setPaused(false);
    setPlan(null);
    setErrors([]);
    setFailure(null);

    createPlan({ example_id: id })
      .then((result) => {
        if (result.status === "ok") setPlan(result.plan);
        else setErrors(result.errors);
      })
      .catch((error: unknown) => setFailure(String(error)));
  }, []);

  const start = useCallback(() => {
    if (plan === null || exampleId === null) return;
    // Replay always starts at seq 0, so the store has to start empty or every
    // line would be applied twice.
    seedStore.getState().reset();
    setFailure(null);
    setRejoined(false);

    createRun(plan.id, speed)
      .then(({ run_id }) => {
        setRunId(run_id);
        setPaused(false);
        rememberRun({ runId: run_id, exampleId, speed });
        watch(run_id);
      })
      .catch((error: unknown) => setFailure(String(error)));
  }, [plan, exampleId, speed, watch]);

  const togglePause = useCallback(() => {
    if (runId === null) return;
    controlRun(runId, paused ? "resume" : "pause")
      .then((state) => setPaused(state.paused))
      .catch((error: unknown) => setFailure(String(error)));
  }, [runId, paused]);

  const reset = useCallback(() => {
    if (runId !== null) void controlRun(runId, "cancel").catch(() => undefined);
    stream.current?.close();
    stream.current = null;
    forgetRun();
    seedStore.getState().reset();
    setRunId(null);
    setRejoined(false);
    setPaused(false);
  }, [runId]);

  const changeSpeed = useCallback(
    (next: number) => {
      setSpeed(next);
      if (runId !== null) void controlRun(runId, "speed", next).catch(() => undefined);
    },
    [runId],
  );

  const running = runId !== null && !run.completed && run.error === null;

  return (
    <main>
      <h1>Seed</h1>
      <p>Agent reasoning is scripted. The pipeline and all figures are computed from real data.</p>

      <section>
        <h2>Requirements</h2>
        {examples.length === 0 && failure === null && <p>Loading examples.</p>}
        <ul>
          {examples.map((example) => (
            <li key={example.id}>
              <button type="button" onClick={() => buildPlan(example.id)}>
                {example.title}
              </button>
            </li>
          ))}
        </ul>
      </section>

      {failure !== null && <p>{failure}</p>}

      {errors.length > 0 && (
        <section>
          <h2>This requirement cannot be run</h2>
          <ul>
            {errors.map((error, index) => (
              <li key={`${error.code}-${index}`}>
                {error.task_id !== null && error.task_id !== undefined && (
                  <strong>{error.task_id} </strong>
                )}
                {error.message}
              </li>
            ))}
          </ul>
        </section>
      )}

      {plan !== null && (
        <>
          <section>
            <h2>Controls</h2>
            <button type="button" onClick={start} disabled={running}>
              Start the run
            </button>{" "}
            <button type="button" onClick={togglePause} disabled={!running}>
              {paused ? "Resume" : "Pause"}
            </button>{" "}
            <button type="button" onClick={reset} disabled={runId === null}>
              Reset
            </button>{" "}
            {SPEEDS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => changeSpeed(option)}
                disabled={speed === option}
              >
                {option}x
              </button>
            ))}
            <p>
              {runId === null
                ? "Not started."
                : run.completed
                  ? `Built in ${run.durationMs ?? 0} ms. ${run.artifacts.length} artifacts.`
                  : run.error !== null
                    ? run.error
                    : `Running. ${run.lastSeq + 1} events.`}
            </p>
            {rejoined && <p>Rejoined a run already in progress. Replayed from the start.</p>}
          </section>

          {runId === null ? (
            <PlanView plan={plan} />
          ) : (
            <>
              <PlanProgress plan={plan} run={run} />
              <AgentRail run={run} />
              <ArtifactList run={run} />
              <section>
                <h2>Log</h2>
                <LogStream logs={run.logs} />
              </section>
            </>
          )}
        </>
      )}
    </main>
  );
}
