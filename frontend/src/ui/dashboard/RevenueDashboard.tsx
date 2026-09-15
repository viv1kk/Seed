/**
 * The delivered dashboard. Paper white, full colour, five surfaces.
 *
 * The data flow has exactly one direction:
 *
 *     interaction -> Filters -> POST /query -> AggBundle -> render
 *
 * Every figure on the page was computed by Polars over the run's retained frame
 * at the moment the response was built, and every filter interaction sends the
 * filter back and re-renders from the next response. Nothing is filtered here.
 * A client-side filter would quietly turn this back into a picture of a
 * dashboard, which is the one thing it must not be.
 *
 * While a query is in flight the surfaces dim to 60% rather than showing
 * spinners. The round trip is single-digit milliseconds and a spinner would
 * flash.
 */

import type { AggBundle, Filters } from "../../types/events.ts";
import { count, duration, shortDate } from "../present.ts";
import { Headline } from "./Headline.tsx";
import { RevenueByCategory, RevenueByRegion, RevenueOverTime, TopProducts } from "./surfaces.tsx";

export interface DashboardProps {
  bundle: AggBundle;
  /** True while a query is in flight. */
  pending: boolean;
  /** True on arrival, which is the one time the numerals count up. */
  arriving: boolean;
  onFilter: (next: Filters) => void;
}

export function RevenueDashboard({ bundle, pending, arriving, onFilter }: DashboardProps) {
  const { filters } = bundle;

  /** Toggle a dimension: clicking the value that is already on clears it. */
  const toggle = (key: "category" | "region", value: string) => {
    onFilter({ ...filters, [key]: filters[key] === value ? null : value });
  };

  const chips = activeChips(filters);

  return (
    <div className="h-full overflow-y-auto bg-paper px-6 py-5 text-paper-ink">
      <header className="flex flex-wrap items-baseline justify-between gap-3 pb-4">
        <h2 className="t-run-title">Revenue and margin</h2>
        <p className="t-secondary text-paper-dim">
          {count(bundle.rows)} rows in this selection, aggregated in{" "}
          {duration(bundle.computed_ms)}.
        </p>
      </header>

      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 pb-4">
          {chips.map((chip) => (
            <button
              key={chip.label}
              type="button"
              onClick={() => onFilter({ ...filters, ...chip.clears })}
              className="t-secondary flex items-center gap-1.5 rounded-full border border-paper-rule bg-white px-2.5 py-1 text-paper-ink hover:border-paper-dim"
            >
              {chip.label}
              <span aria-hidden className="text-paper-dim">
                x
              </span>
              <span className="sr-only">Remove this filter</span>
            </button>
          ))}
          <button
            type="button"
            onClick={() => onFilter({})}
            className="t-secondary px-1 text-paper-dim underline underline-offset-2 hover:text-paper-ink"
          >
            Clear filters
          </button>
        </div>
      )}

      <div
        aria-busy={pending}
        className="flex flex-col gap-5 transition-opacity duration-[180ms]"
        style={{ opacity: pending ? 0.6 : 1 }}
      >
        <Headline kpis={bundle.kpis} animate={arriving} />

        <RevenueOverTime bundle={bundle} onFilter={onFilter} />

        <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
          <RevenueByCategory bundle={bundle} onToggle={(value) => toggle("category", value)} />
          <RevenueByRegion bundle={bundle} onToggle={(value) => toggle("region", value)} />
        </div>

        <TopProducts bundle={bundle} />
      </div>
    </div>
  );
}

interface Chip {
  label: string;
  /** The filter fields this chip clears when removed. */
  clears: Partial<Filters>;
}

/** The active filters, read off the response rather than off local state. */
function activeChips(filters: Filters): Chip[] {
  const chips: Chip[] = [];
  if (filters.date_from != null || filters.date_to != null) {
    const from = filters.date_from == null ? "the start" : shortDate(filters.date_from);
    const to = filters.date_to == null ? "the end" : shortDate(filters.date_to);
    chips.push({ label: `${from} to ${to}`, clears: { date_from: null, date_to: null } });
  }
  if (filters.category != null) {
    chips.push({ label: filters.category, clears: { category: null } });
  }
  if (filters.region != null) {
    chips.push({ label: filters.region, clears: { region: null } });
  }
  return chips;
}
