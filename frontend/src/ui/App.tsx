/**
 * Phase 0 shell. Deliberately unstyled.
 *
 * It renders the backend health response and the number of events the store has
 * seen, which is enough to prove the dev proxy reaches the API and that the
 * store is wired. The plan room arrives in phase 4. Do not start styling here.
 */
import { useEffect, useState } from "react";

import { useSeedStore } from "./useSeedStore.ts";

interface Health {
  status: string;
  version: string;
  mode: string;
}

export function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const lastSeq = useSeedStore((state) => state.run.lastSeq);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/health", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`Health check returned ${response.status}`);
        return response.json() as Promise<Health>;
      })
      .then(setHealth)
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setHealthError(error instanceof Error ? error.message : String(error));
      });
    return () => controller.abort();
  }, []);

  return (
    <main>
      <h1>Seed</h1>
      {health !== null && (
        <p>
          Backend {health.version}, {health.status}, {health.mode} mode.
        </p>
      )}
      {healthError !== null && <p>Cannot reach the backend. Start it on port 8000.</p>}
      {health === null && healthError === null && <p>Checking the backend.</p>}
      <p>Events applied: {lastSeq + 1}</p>
    </main>
  );
}
