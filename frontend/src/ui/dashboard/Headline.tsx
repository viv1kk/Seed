/**
 * The five headline figures, counting up from zero on arrival.
 *
 * The count-up is part of the completion transition: 600ms, staggered by 60ms,
 * and it happens once, when the dashboard lands. A cross-filter must not
 * re-trigger it, or every filter would read as a page reload.
 *
 * The numbers themselves are never touched. Each tile is handed a final value
 * and a formatter, and the animation only decides what fraction of it to show
 * on the way there. `prefers-reduced-motion` skips straight to the value.
 */

import { useEffect, useRef, useState } from "react";

import type { Kpis } from "../../types/events.ts";
import { count, money, percent } from "../present.ts";

const DURATION_MS = 600;
const STAGGER_MS = 60;

export function Headline({ kpis, animate }: { kpis: Kpis; animate: boolean }) {
  const tiles: { label: string; value: number; format: (value: number) => string }[] = [
    { label: "Net revenue", value: kpis.net_revenue, format: money },
    { label: "Orders", value: kpis.order_count, format: count },
    { label: "Average order value", value: kpis.average_order_value, format: money },
    { label: "Margin", value: kpis.margin_pct, format: percent },
    { label: "Return rate", value: kpis.return_rate, format: percent },
  ];

  return (
    // auto-fit rather than a fixed five, so a numeral that will not fit its
    // column wraps the row instead of running into its neighbour.
    <dl
      className="grid gap-x-6 gap-y-5"
      style={{ gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))" }}
    >
      {tiles.map((tile, index) => (
        <Figure
          key={tile.label}
          label={tile.label}
          value={tile.value}
          format={tile.format}
          delayMs={animate ? index * STAGGER_MS : 0}
          animate={animate}
        />
      ))}
    </dl>
  );
}

function Figure({
  label,
  value,
  format,
  delayMs,
  animate,
}: {
  label: string;
  value: number;
  format: (value: number) => string;
  delayMs: number;
  animate: boolean;
}) {
  const shown = useCountUp(value, delayMs, animate);
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <dd className="t-headline truncate text-paper-ink">{format(shown)}</dd>
      <dt className="t-secondary text-paper-dim">{label}</dt>
    </div>
  );
}

/**
 * Ease a number from zero to its value, once.
 *
 * Keyed on the value: a cross-filter changes it, and the hook then jumps rather
 * than re-running the count, which is what keeps a filter from reading as a
 * reload. Only the first value a tile is given is animated.
 */
function useCountUp(value: number, delayMs: number, animate: boolean): number {
  const [shown, setShown] = useState(animate ? 0 : value);
  const counted = useRef(false);

  useEffect(() => {
    if (!animate || counted.current || prefersReducedMotion()) {
      setShown(value);
      counted.current = true;
      return;
    }
    counted.current = true;

    let frame = 0;
    const started = performance.now() + delayMs;
    const tick = (now: number) => {
      const elapsed = now - started;
      if (elapsed < 0) {
        frame = requestAnimationFrame(tick);
        return;
      }
      const t = Math.min(1, elapsed / DURATION_MS);
      // Ease out cubic: fast at the start, settling rather than stopping.
      setShown(value * (1 - (1 - t) ** 3));
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, delayMs, animate]);

  return shown;
}

export function prefersReducedMotion(): boolean {
  return (
    typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}
