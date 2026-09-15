/**
 * The delivered dashboard: five surfaces over one AggBundle.
 *
 * This component computes nothing. Every figure on the page arrives already
 * calculated from `POST /api/runs/{id}/query`, and every filter interaction
 * sends the filter back and re-renders from the response. There is no local
 * filtering here and there must never be: the whole claim of this dashboard is
 * that brushing a date range re-runs Polars over the real frame, and a
 * client-side filter would quietly turn it back into a picture.
 *
 * So the data flow has exactly one direction:
 *
 *     interaction -> Filters -> POST /query -> AggBundle -> render
 *
 * Formatting is the one thing that does happen here, because it is
 * presentation. Indian numbering and INR, percentages to one decimal.
 *
 * Phase 3 styles this minimally on purpose. The paper-white treatment, the
 * chart palette and the completion transition are phase 4, from
 * docs/06-UI-SPEC.md.
 */

import {
  Area,
  Bar,
  BarChart,
  Brush,
  CartesianGrid,
  Cell,
  Line,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { AggBundle, Filters } from "../../types/events.ts";

const money = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});
const compact = new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 });
const count = new Intl.NumberFormat("en-IN");

function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

/**
 * Recharts types a tooltip value as a union, because a chart can carry
 * anything. Every series here is a number from the bundle, so this narrows once
 * rather than at four call sites, and falls back to the raw text instead of
 * asserting a type the library will not promise.
 */
function asMoney(value: unknown): string {
  return typeof value === "number" ? money.format(value) : String(value ?? "");
}

export interface DashboardProps {
  bundle: AggBundle;
  /** True while a query is in flight. Surfaces dim rather than showing spinners. */
  pending: boolean;
  onFilter: (next: Filters) => void;
}

export function RevenueDashboard({ bundle, pending, onFilter }: DashboardProps) {
  const { kpis, filters } = bundle;

  /** Toggle a dimension: clicking the active value clears it. */
  const toggle = (key: "category" | "region", value: string) => {
    onFilter({ ...filters, [key]: filters[key] === value ? null : value });
  };

  /**
   * The brush hands back indices into the weekly series, which are turned into
   * the dates at those positions. The backend does the filtering; this only
   * says which window was dragged.
   */
  const brush = (range: { startIndex?: number; endIndex?: number }) => {
    const points = bundle.revenue_over_time;
    const from = points[range.startIndex ?? 0];
    const to = points[range.endIndex ?? points.length - 1];
    if (from === undefined || to === undefined) return;
    onFilter({ ...filters, date_from: from.week, date_to: to.week });
  };

  const clear = () => onFilter({});
  const chips = activeChips(filters);

  return (
    <section style={{ opacity: pending ? 0.6 : 1 }} aria-busy={pending}>
      <h2>Revenue dashboard</h2>

      {chips.length > 0 && (
        <p>
          {chips.map((chip) => (
            <span key={chip}>{chip} </span>
          ))}
          <button type="button" onClick={clear}>
            Clear filters
          </button>
        </p>
      )}

      <dl>
        <Figure label="Net revenue" value={money.format(kpis.net_revenue)} />
        <Figure label="Orders" value={count.format(kpis.order_count)} />
        <Figure label="Average order value" value={money.format(kpis.average_order_value)} />
        <Figure label="Margin" value={percent(kpis.margin_pct)} />
        <Figure label="Return rate" value={percent(kpis.return_rate)} />
      </dl>

      <h3>Revenue over time</h3>
      <ResponsiveContainer width="100%" height={240}>
        <ComposedChart data={bundle.revenue_over_time}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="week" />
          <YAxis yAxisId="revenue" tickFormatter={(v: number) => compact.format(v)} />
          <YAxis yAxisId="orders" orientation="right" />
          <Tooltip formatter={asMoney} />
          <Area yAxisId="revenue" type="monotone" dataKey="net_revenue" name="Net revenue" />
          <Line yAxisId="orders" type="monotone" dataKey="order_count" name="Orders" dot={false} />
          <Brush dataKey="week" height={20} onChange={brush} />
        </ComposedChart>
      </ResponsiveContainer>

      <h3>Revenue by category</h3>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={bundle.revenue_by_category} layout="vertical">
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis type="number" tickFormatter={(v: number) => compact.format(v)} />
          <YAxis type="category" dataKey="category" width={90} />
          <Tooltip formatter={asMoney} />
          <Bar dataKey="net_revenue" name="Net revenue">
            {bundle.revenue_by_category.map((row) => (
              <Cell
                key={row.category}
                cursor="pointer"
                opacity={filters.category === null || filters.category === row.category ? 1 : 0.4}
                onClick={() => toggle("category", row.category)}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <h3>Revenue by region</h3>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={bundle.revenue_by_region}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="region" />
          <YAxis tickFormatter={(v: number) => compact.format(v)} />
          <Tooltip formatter={asMoney} />
          <Bar dataKey="net_revenue" name="Net revenue">
            {bundle.revenue_by_region.map((row) => (
              <Cell
                key={row.region}
                cursor="pointer"
                opacity={filters.region === null || filters.region === row.region ? 1 : 0.4}
                onClick={() => toggle("region", row.region)}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <h3>Top products</h3>
      <table>
        <thead>
          <tr>
            <th>SKU</th>
            <th>Product</th>
            <th>Units</th>
            <th>Net revenue</th>
            <th>Margin</th>
          </tr>
        </thead>
        <tbody>
          {bundle.top_products.map((row) => (
            <tr key={row.sku}>
              <td>{row.sku}</td>
              <td>{row.product_name}</td>
              <td>{count.format(row.units)}</td>
              <td>{money.format(row.net_revenue)}</td>
              <td>{percent(row.margin_pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <p>
        {count.format(bundle.rows)} rows in the current selection, aggregated in{" "}
        {bundle.computed_ms} ms.
      </p>
    </section>
  );
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

/** The active filters, as text. Reads the response, never local state. */
function activeChips(filters: Filters): string[] {
  const chips: string[] = [];
  if (filters.date_from != null || filters.date_to != null) {
    chips.push(`${filters.date_from ?? "start"} to ${filters.date_to ?? "end"}`);
  }
  if (filters.category != null) chips.push(filters.category);
  if (filters.region != null) chips.push(filters.region);
  return chips;
}
