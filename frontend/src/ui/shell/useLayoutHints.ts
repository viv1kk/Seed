/**
 * Two small facts about the viewport that the layout needs to branch on.
 *
 * Both are view state, not logic: one asks how wide the window is, the other
 * asks whether the person has told their operating system to reduce motion.
 */

import { useEffect, useState } from "react";

/** Below 1100 the artifacts column collapses into a tab beside the log. */
export const NARROW = "(max-width: 1100px)";

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => matchMedia(query).matches);

  useEffect(() => {
    const list = matchMedia(query);
    const onChange = () => setMatches(list.matches);
    onChange();
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

/**
 * The completion transition, as a state machine.
 *
 * The console dims 30% over 250ms, and only then does the deliverable wipe up
 * from the bottom edge. Nothing else animates during it, which is what makes it
 * read as one orchestrated moment rather than three things happening at once.
 *
 * Returns "run" while the console is live, "dimming" during the 250ms, and
 * "delivered" once the dashboard has the screen.
 */
export type Delivery = "run" | "dimming" | "delivered";

export function useDelivery(ready: boolean): Delivery {
  const [stage, setStage] = useState<Delivery>("run");

  useEffect(() => {
    if (!ready) {
      setStage("run");
      return;
    }
    if (stage === "delivered") return;
    setStage("dimming");
    const timer = setTimeout(() => setStage("delivered"), 250);
    return () => clearTimeout(timer);
    // `stage` is read to avoid restarting the timer once it has landed, but it
    // must not re-trigger the effect, or the dashboard would flicker back.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready]);

  return stage;
}
