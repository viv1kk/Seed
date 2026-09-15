/**
 * The four plotted surfaces. Recharts, on paper.
 *
 * None of these compute anything. Each takes a slice of the `AggBundle` the
 * backend just returned and draws it; a click hands a `Filters` back up, and
 * the next bundle arrives already recomputed in Polars. There is no local
 * filtering here and there must never be, because that claim is the whole
 * reason the dashboard is worth showing.
 *
 * The weekly chart carries order count on a second axis. That is a deliberate
 * departure from general charting advice, which says two scales on one plot
 * invite a false comparison. It is what docs/05 and docs/06 specify, the two
 * series are labelled and separately coloured, and the question the surface
 * answers is "did revenue move because volume moved", which wants them on one
 * time axis.
 */

import {
  Area,
  Bar,
  BarChart,
  Brush,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { AggBundle, Filters } from "../../types/events.ts";
import { count, INK, money, moneyShort, percent, SERIES, shortDate } from "../present.ts";

const AXIS = { fill: INK.paperDim, fontSize: 11 };
const GRID = INK.paperRule;

/**
 * Recharts re-animates a series from zero whenever its data changes, which on
 * this page means every cross-filter. The spec forbids it, and rightly: a chart
 * that rebuilds itself on each filter reads as a page reload rather than as the
 * same chart showing a different cut. The 180ms cross-fade on the container is
 * the whole of the transition.
 */
const NO_REANIMATE = { isAnimationActive: false } as const;

const TOOLTIP_STYLE = {
  background: "#ffffff",
  border: `1px solid ${INK.paperRule}`,
  borderRadius: 3,
  fontSize: 12,
  color: INK.paperInk,
} as const;

export function RevenueOverTime({
  bundle,
  onFilter,
}: {
  bundle: AggBundle;
  onFilter: (next: Filters) => void;
}) {
  const points = bundle.revenue_over_time;

  /**
   * The brush hands back indices into the weekly series. Those become the dates
   * at those positions, and the backend does the filtering.
   */
  const brush = (range: { startIndex?: number; endIndex?: number }) => {
    const from = points[range.startIndex ?? 0];
    const to = points[range.endIndex ?? points.length - 1];
    if (from === undefined || to === undefined) return;
    if (range.startIndex === 0 && range.endIndex === points.length - 1) {
      onFilter({ ...bundle.filters, date_from: null, date_to: null });
      return;
    }
    onFilter({ ...bundle.filters, date_from: from.week, date_to: to.week });
  };

  return (
    <Surface title="Revenue over time" hint="Drag the handles below the chart to filter a period">
      <Legend
        items={[
          ["Net revenue", SERIES[0]],
          ["Orders", SERIES[4]],
        ]}
      />
      <ResponsiveContainer width="100%" height={230}>
        <ComposedChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="seed-revenue" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={SERIES[1]} stopOpacity={0.5} />
              <stop offset="100%" stopColor={SERIES[1]} stopOpacity={0.05} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis
            dataKey="week"
            tick={AXIS}
            tickFormatter={shortDate}
            stroke={GRID}
            minTickGap={36}
          />
          <YAxis
            yAxisId="revenue"
            tick={AXIS}
            stroke={GRID}
            tickFormatter={moneyShort}
            width={68}
          />
          <YAxis
            yAxisId="orders"
            orientation="right"
            tick={AXIS}
            stroke={GRID}
            tickFormatter={count}
            width={48}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            labelFormatter={(label: unknown) => `Week of ${shortDate(String(label))}`}
            formatter={(value: unknown, name: unknown) =>
              name === "Orders" ? count(Number(value)) : money(Number(value))
            }
          />
          <Area
            yAxisId="revenue"
            type="monotone"
            dataKey="net_revenue"
            name="Net revenue"
            stroke={SERIES[0]}
            strokeWidth={2}
            fill="url(#seed-revenue)"
            {...NO_REANIMATE}
          />
          <Line
            yAxisId="orders"
            type="monotone"
            dataKey="order_count"
            name="Orders"
            stroke={SERIES[4]}
            strokeWidth={2}
            dot={false}
            {...NO_REANIMATE}
          />
          <Brush
            dataKey="week"
            height={22}
            travellerWidth={8}
            stroke={INK.paperDim}
            fill="#ffffff"
            tickFormatter={shortDate}
            onChange={brush}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </Surface>
  );
}

export function RevenueByCategory({
  bundle,
  onToggle,
}: {
  bundle: AggBundle;
  onToggle: (category: string) => void;
}) {
  const selected = bundle.filters.category ?? null;
  return (
    <Surface title="Revenue by category" hint="Click a bar to filter">
      <ResponsiveContainer width="100%" height={260}>
        <BarChart
          data={bundle.revenue_by_category}
          layout="vertical"
          margin={{ top: 4, right: 56, bottom: 0, left: 0 }}
          barCategoryGap={6}
        >
          <CartesianGrid stroke={GRID} horizontal={false} />
          <XAxis type="number" tick={AXIS} stroke={GRID} tickFormatter={moneyShort} />
          <YAxis
            type="category"
            dataKey="category"
            tick={AXIS}
            stroke={GRID}
            width={104}
            tickLine={false}
          />
          <Tooltip
            cursor={{ fill: INK.paperRule, fillOpacity: 0.4 }}
            contentStyle={TOOLTIP_STYLE}
            formatter={(value: unknown) => money(Number(value))}
          />
          <Bar
            dataKey="net_revenue"
            name="Net revenue"
            radius={[0, 4, 4, 0]}
            {...NO_REANIMATE}
            label={{
              position: "right",
              fill: INK.paperDim,
              fontSize: 11,
              formatter: (value: unknown) => percent(Number(value)),
              dataKey: "margin_pct",
            }}
          >
            {bundle.revenue_by_category.map((row) => (
              <Cell
                key={row.category}
                cursor="pointer"
                fill={selected === row.category ? SERIES[4] : SERIES[1]}
                fillOpacity={selected === null || selected === row.category ? 1 : 0.35}
                onClick={() => onToggle(row.category)}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p className="t-secondary text-paper-dim">Label on each bar is margin.</p>
    </Surface>
  );
}

export function RevenueByRegion({
  bundle,
  onToggle,
}: {
  bundle: AggBundle;
  onToggle: (region: string) => void;
}) {
  const selected = bundle.filters.region ?? null;
  return (
    <Surface title="Revenue by region" hint="Click a bar to filter">
      <ResponsiveContainer width="100%" height={260}>
        <BarChart
          data={bundle.revenue_by_region}
          margin={{ top: 18, right: 8, bottom: 0, left: 0 }}
          barCategoryGap={10}
        >
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="region" tick={AXIS} stroke={GRID} tickLine={false} />
          <YAxis tick={AXIS} stroke={GRID} tickFormatter={moneyShort} width={68} />
          <Tooltip
            cursor={{ fill: INK.paperRule, fillOpacity: 0.4 }}
            contentStyle={TOOLTIP_STYLE}
            formatter={(value: unknown) => money(Number(value))}
          />
          <Bar
            dataKey="net_revenue"
            name="Net revenue"
            radius={[4, 4, 0, 0]}
            {...NO_REANIMATE}
            label={{
              position: "top",
              fill: INK.paperDim,
              fontSize: 11,
              formatter: (value: unknown) => percent(Number(value)),
              dataKey: "share",
            }}
          >
            {bundle.revenue_by_region.map((row) => (
              <Cell
                key={row.region}
                cursor="pointer"
                fill={regionColour(row.region, bundle)}
                fillOpacity={selected === null || selected === row.region ? 1 : 0.35}
                stroke={selected === row.region ? INK.paperInk : "none"}
                strokeWidth={selected === row.region ? 1.5 : 0}
                onClick={() => onToggle(row.region)}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p className="t-secondary text-paper-dim">Label above each bar is share of total.</p>
    </Surface>
  );
}

export function TopProducts({ bundle }: { bundle: AggBundle }) {
  return (
    <Surface title="Top ten products">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-paper-rule">
            <Th>SKU</Th>
            <Th>Product</Th>
            <Th align="right">Units</Th>
            <Th align="right">Net revenue</Th>
            <Th align="right">Margin</Th>
          </tr>
        </thead>
        <tbody>
          {bundle.top_products.map((row) => (
            <tr key={row.sku} className="border-b border-paper-rule/60">
              <Td mono>{row.sku}</Td>
              <Td>{row.product_name}</Td>
              <Td mono align="right">
                {count(row.units)}
              </Td>
              <Td mono align="right">
                {money(row.net_revenue)}
              </Td>
              <Td mono align="right">
                {percent(row.margin_pct)}
              </Td>
            </tr>
          ))}
        </tbody>
      </table>
    </Surface>
  );
}

/**
 * A region's colour, fixed to the region rather than to its position.
 *
 * The bars are sorted by revenue, and a cross-filter reorders them. Colouring by
 * row index would repaint every region whenever the ranking moved, so the eye
 * would have to re-learn the chart on each filter. Naming the regions in a
 * stable order and indexing the ramp by that keeps West the same colour whether
 * it is first or last.
 */
function regionColour(region: string, bundle: AggBundle): string {
  const names = bundle.revenue_by_region.map((row) => row.region).sort();
  const index = names.indexOf(region);
  return SERIES[index === -1 ? 0 : Math.min(index, SERIES.length - 1)] as string;
}

// ---------------------------------------------------------------- furniture

function Surface({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-2 rounded-sm border border-paper-rule bg-white/60 p-4">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="t-panel-header text-paper-ink">{title}</h3>
        {hint !== undefined && <p className="t-secondary text-paper-dim">{hint}</p>}
      </div>
      {children}
    </section>
  );
}

function Legend({ items }: { items: readonly (readonly [string, string])[] }) {
  return (
    <ul className="flex gap-4">
      {items.map(([label, colour]) => (
        <li key={label} className="t-secondary flex items-center gap-1.5 text-paper-dim">
          <span
            aria-hidden
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: colour }}
          />
          {label}
        </li>
      ))}
    </ul>
  );
}

function Th({ children, align }: { children: React.ReactNode; align?: "right" }) {
  return (
    <th
      className={`t-secondary px-2 py-1.5 font-semibold text-paper-dim ${
        align === "right" ? "text-right" : "text-left"
      }`}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  align,
  mono,
}: {
  children: React.ReactNode;
  align?: "right";
  mono?: boolean;
}) {
  return (
    <td
      className={`px-2 py-1.5 text-paper-ink ${align === "right" ? "text-right" : "text-left"} ${
        mono === true ? "t-num text-[13px]" : "t-secondary"
      }`}
    >
      {children}
    </td>
  );
}
