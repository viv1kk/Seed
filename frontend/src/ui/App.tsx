/**
 * Phase 1 shell. Deliberately unstyled.
 *
 * Load an example, render the source document beside the plan the parser made
 * of it. That pairing is the whole point of this screen: the plan is visibly
 * derived from the text next to it, so editing a heading and reloading is a
 * demonstration rather than a claim. The plan room arrives in phase 4.
 */
import { useCallback, useEffect, useState } from "react";

import { createPlan, fetchExamples } from "../api/client.ts";
import type { ExampleSummary, ParseError, Plan } from "../types/events.ts";
import { PlanView } from "./PlanView.tsx";

export function App() {
  const [examples, setExamples] = useState<ExampleSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [errors, setErrors] = useState<ParseError[]>([]);
  const [failure, setFailure] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchExamples()
      .then(setExamples)
      .catch(() => setFailure("Cannot reach the backend. Start it on port 8000."));
  }, []);

  const load = useCallback((exampleId: string) => {
    setLoading(true);
    setSelected(exampleId);
    setPlan(null);
    setErrors([]);
    setFailure(null);

    createPlan({ example_id: exampleId })
      .then((result) => {
        // The backend decides whether the document is usable. This only draws
        // the answer.
        if (result.status === "ok") setPlan(result.plan);
        else setErrors(result.errors);
      })
      .catch((error: unknown) => {
        setFailure(error instanceof Error ? error.message : String(error));
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <main>
      <h1>Seed</h1>

      <section>
        <h2>Requirements</h2>
        {examples.length === 0 && failure === null && <p>Loading examples.</p>}
        <ul>
          {examples.map((example) => (
            <li key={example.id}>
              <button type="button" onClick={() => load(example.id)}>
                {example.title}
              </button>
              {selected === example.id && " (loaded)"}
            </li>
          ))}
        </ul>
      </section>

      {failure !== null && <p>{failure}</p>}
      {loading && <p>Parsing the requirement.</p>}

      {errors.length > 0 && (
        <section>
          <h2>This requirement cannot be run</h2>
          <p>Fix the document and load it again.</p>
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
          <PlanView plan={plan} />
          <section>
            <h2>Source document</h2>
            <pre>{plan.source_markdown}</pre>
          </section>
        </>
      )}
    </main>
  );
}
