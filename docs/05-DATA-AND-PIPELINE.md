# 05. Data and Pipeline

The honest part. `backend/app/pipeline/` is an ordinary Polars pipeline with no knowledge that a simulation exists.

## Bundled dataset

Generated once by `backend/scripts/generate_data.py` with a fixed seed, then committed to `backend/app/data/`. Regenerating must reproduce byte-identical files.

### orders.csv, about 12,800 rows, calendar year 2025

| column | type | notes |
|---|---|---|
| order_id | str | `ORD-` + 7 digits |
| order_ts | str | **deliberately mixed**, see defects |
| customer_id | str | FK to customers |
| region | str | North, South, East, West, Central |
| channel | str | web, mobile, retail, partner |
| sku | str | FK to products |
| qty | str | **deliberately dirty** |
| unit_price | float | 2dp |
| discount_pct | float or empty | 0 to 0.35, about 4% empty |
| status | str | completed, returned, cancelled |

### products.csv, 180 rows

`sku, product_name, category, cost_price`. Eight categories. `cost_price` is 45% to 75% of typical `unit_price`, so margin is a real spread rather than a constant.

### customers.csv, 2,400 rows

`customer_id, signup_date, segment, region`. Segments consumer, smb, enterprise. `region` also exists on orders and the two disagree on about 3% of rows, which the Analytics Engineer notices and resolves in favour of the order-level region.

## Deliberate defects

Seeded and reproducible. Each exists to give an agent something real to say.

| Defect | Volume | Agent reaction |
|---|---|---|
| `order_ts` in `DD/MM/YYYY HH:mm` alongside ISO 8601 | about 6%, 771 rows | ETL. **Triggers the failure and retry beat.** |
| Duplicate `order_id` | 19 rows | ETL, dedupe keeping latest |
| `qty` with whitespace or as `"3.0"` | about 9% | ETL, coercion with a logged count |
| `discount_pct` empty | about 4% | ETL, fill zero and log the null rate |
| `region` mismatch between order and customer | about 3% | Analytics, logged and resolved |
| Negative `qty` on returns | all `returned` rows | Analytics, excluded from gross revenue |

## Pipeline steps

Pure functions, real metrics, one per task in the demo requirement file.

**1. `load_csv(name) -> LoadResult`**

```python
pl.read_csv(path, infer_schema_length=0)   # everything as Utf8
```

Reading everything as strings is deliberate: coercion becomes visible and countable later, and it is what a careful engineer would do with an untrusted extract. Returns `df`, `rows`, `columns`, `parse_ms`.

**2. `profile(df) -> ProfileResult`**

Per column: null count, distinct count, inferred type, and for string columns a format fingerprint. The timestamp format detection lives here and is what the ETL agent uses to diagnose the failure. All counts real.

**3. `clean(df, strategy) -> CleanResult`**

```python
class CleanStrategy(BaseModel):
    timestamp: Literal["iso-strict", "multi-format-day-first"]
    dedupe_on: str | None = None
    coerce: dict[str, str] = {}
    fill_nulls: dict[str, float] = {}
```

`iso-strict` is:

```python
df.with_columns(
    pl.col("order_ts").str.to_datetime(format="%Y-%m-%dT%H:%M:%S", strict=True)
)
```

Against the real file this **raises `pl.exceptions.InvalidOperationError`**. That is the failure beat, and it is a real library raising on real malformed data. Do not wrap it in a flag, do not pre-check, do not simulate it. Let it raise, catch it in the runner, and report the real failing count from a non-strict probe pass.

`multi-format-day-first` is:

```python
df.with_columns(
    pl.coalesce(
        pl.col("order_ts").str.to_datetime(format="%Y-%m-%dT%H:%M:%S", strict=False),
        pl.col("order_ts").str.to_datetime(format="%d/%m/%Y %H:%M",  strict=False),
    ).alias("order_ts")
)
```

Returns `df`, `rows_in`, `rows_out`, `rows_dropped`, `coerced_counts`, `null_rates`, `failures`.

**4. `join(left, right, on) -> JoinResult`** Inner join with match statistics. Returns `matched` and `unmatched`, computed rather than assumed, even where the answer should be zero.

**5. `derive(df) -> DeriveResult`** Adds `gross_revenue`, `net_revenue`, `cogs`, `margin`, `margin_pct`, `order_date`, `order_week`.

```python
net_revenue = qty * unit_price * (1 - discount_pct)
cogs        = qty * cost_price
margin      = net_revenue - cogs
```

**6. `aggregate(df, filters=None) -> AggBundle`** Five aggregations over the derived frame, excluding `cancelled`, with returns counted separately rather than folded into revenue.

| Aggregation | Group by | Measures |
|---|---|---|
| `kpis` | none | net revenue, order count, average order value, margin pct, return rate |
| `revenue_over_time` | order_week | net revenue, order count |
| `revenue_by_category` | category | net revenue, margin pct |
| `revenue_by_region` | region | net revenue, share of total |
| `top_products` | sku | net revenue, units, margin pct, top 10 by net revenue |

**Every `group_by` passes `maintain_order=True`.** Polars does not guarantee group order otherwise, and the run stops being reproducible in a way that is miserable to debug on day 5.

## Cross-filter

`aggregate` takes an optional `Filters`. This is what turns the delivered dashboard into a live surface.

```python
class Filters(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    category: str | None = None
    region: str | None = None
```

`POST /api/runs/{id}/query` applies them to the retained derived frame and returns a fresh `AggBundle`. The derived frame stays in the run registry after completion, so the dashboard can keep querying it.

**A dimension cut is not filtered by itself.** `revenue_by_category` is computed
with every active filter except `category`, and `revenue_by_region` with every
filter except `region`. Everything else takes all of them. Filtering the category
chart by the selected category leaves it showing a single bar, with no other
category visible to compare against or click next, which defeats the interaction
the chart exists for: `06-UI-SPEC.md` says a category click recomputes region,
time and top products, and that the clicked bar takes a selected treatment
among the others.

With nothing selected this changes nothing, so both cuts still sum to the
headline and the acceptance criterion in the requirement document holds. Under a
selection they deliberately do not: with a category chosen, `revenue_by_category`
sums to more than `kpis.net_revenue`, and `revenue_by_region`'s shares are shares
of that cut's own total, which is what makes a share label answer "of the revenue
this chart is showing".

Frontend behaviour, specified in `06-UI-SPEC.md`: brushing the weekly revenue chart, or clicking a category bar or a region bar, issues a query and re-renders everything from the response. The frontend does not filter locally, ever. A 12,800-row frame recomputes in single-digit milliseconds, so this is fast and it is real.

This is the strongest answer available to "is that dashboard just a picture." A canned screenshot cannot cross-filter. Budget for it and do not cut it.

## Dashboard bindings

`frontend/src/ui/dashboard/` consumes `AggBundle` only. It has no access to any row-level data.

| Surface | Source | Chart |
|---|---|---|
| Five headline figures | `kpis` | large numerals with a label beneath |
| Revenue over time | `revenue_over_time` | Recharts `AreaChart`, weekly, order count on a secondary axis, `Brush` enabled |
| Revenue by category | `revenue_by_category` | horizontal `BarChart`, sorted descending, margin pct as bar label, bars clickable |
| Revenue by region | `revenue_by_region` | vertical `BarChart` with share of total, bars clickable |
| Top products | `top_products` | table, right-aligned numerics, tabular figures |

`Intl.NumberFormat` with `en-IN` and INR. Percentages to one decimal.

## Generated code artifacts

Code artifacts are the real pipeline modules, read from disk and highlighted with Pygments server side.

```python
source = (PIPELINE_DIR / "clean.py").read_text()
html = highlight(source, PythonLexer(), HtmlFormatter(nowrap=True))
```

The artifact a stakeholder opens is the code that actually ran. That means it needs to read well: comment it properly, name things clearly, keep modules focused. Someone will put it on a projector.

Artifacts produced during a run, in order:

| Path | Kind | By |
|---|---|---|
| `design/schema_contract.md` | doc | architect |
| `pipeline/load.py` | code | etl |
| `pipeline/clean.py` | code | etl |
| `data/orders_clean` | dataset | etl |
| `dashboard/spec.json` | code | dashboard |
| `pipeline/transform.py` | code | analytics |
| `data/orders_enriched` | dataset | analytics |
| `pipeline/aggregate.py` | code | analytics |
| `analytics/metrics.json` | table | analytics |
| `dashboard/RevenueDashboard.tsx` | code | dashboard |
| `dashboard` | dashboard | dashboard |
| `design/verification.md` | doc | architect |

`design/verification.md` is generated at run time. It walks every `>` acceptance criterion in the requirement file and writes the measured value beside it, flagging anything that missed. It is the closing artifact and the most client-legible output in the build. It should read like something a careful engineer wrote, not like a template.
