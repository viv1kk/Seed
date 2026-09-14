# Retail revenue analytics platform

We sell through four channels across five regions and we currently have no single view of revenue or margin. Finance rebuilds the numbers by hand in a spreadsheet every Monday and the figures disagree with what the category managers report.

Build a pipeline over our order, product, and customer extracts, and deliver a dashboard that answers where revenue comes from and where margin is being lost.

Source files are in `data/`. They are raw exports and we know they are not clean.

## Phase 1: Design

### 1.1 Define the schema contract

Agent: Architect

Agree the shape of every source and the shape of the analytical table before any code is written. We have been burned by pipelines that were built against assumptions.

- Read all three source extracts and record the columns present in each
- Decide the join keys between orders, products, and customers
- Specify the derived columns needed for revenue and margin
- Write the contract to a document the rest of the work refers back to

```yaml
sources:
  orders:    { grain: one row per order line, key: order_id }
  products:  { grain: one row per sku,        key: sku }
  customers: { grain: one row per customer,   key: customer_id }
joins:
  - orders.sku         -> products.sku
  - orders.customer_id -> customers.customer_id
```

> The contract names every column consumed downstream, and nothing downstream reads a column that is not in it.

### 1.2 Set the data quality rules

Agent: Architect
Depends on: 1.1

Decide in advance what we do with bad rows, so the pipeline is not making judgement calls silently.

- Set the duplicate handling rule for order_id
- Set the policy for missing discount values
- Set the timestamp normalisation target
- Define what counts as a row we are willing to drop

```yaml
timestamps:
  target: UTC
  tolerance: no row may be dropped for a timestamp we can parse by any reasonable rule
duplicates:
  order_id: keep the most recent, log the count
nulls:
  discount_pct: treat as zero, report the rate
drop_budget: 0.5% of input rows
```

> Every rule is recorded with a count when it is applied. A silent drop is a defect.

## Phase 2: Build

### 2.1 Ingest and clean the order data

Agent: ETL Engineer
Depends on: 1.1, 1.2

This is the messy one. The orders extract comes out of two upstream systems that were merged last year and it shows.

- Load all three source files and report row and column counts
- Profile the order data before committing to a schema
- Normalise all order timestamps to UTC
- Remove duplicate orders under the rule from 1.2
- Coerce quantity to a number and report how many values needed it
- Fill missing discount values and report the null rate

> All rows are retained except those the quality rules explicitly allow us to drop, and the dropped count stays inside the drop budget.

### 2.2 Draft the dashboard layout

Agent: Dashboard Engineer
Depends on: 1.1

You can start on this from the contract alone. We would rather see the layout early than discover at the end that it does not answer the question.

- Choose the headline figures finance will look at first
- Decide which cuts of revenue earn a chart and which earn a table
- Specify the chart types and what each axis carries

> The layout is derived from the schema contract, not from whatever the data happens to contain.

### 2.3 Build the analytical table and metrics

Agent: Analytics Engineer
Depends on: 2.1

Join the cleaned orders to products and customers, derive the money columns, and compute the aggregates the dashboard needs.

- Join orders to products on sku and verify the match rate
- Join orders to customers and resolve any region disagreement between the two
- Derive gross revenue, net revenue, cost of goods, margin, and margin percentage
- Exclude cancelled orders from revenue and account for returns separately
- Compute weekly revenue, revenue by category, revenue by region, and the top ten products
- Compute the headline figures: net revenue, order count, average order value, margin percentage, and return rate

```sql
net_revenue = qty * unit_price * (1 - discount_pct)
cogs        = qty * cost_price
margin      = net_revenue - cogs
```

> Revenue by region sums to total net revenue. Revenue by category sums to total net revenue. If they do not, the pipeline is wrong.

## Phase 3: Deliver

### 3.1 Build the revenue dashboard

Agent: Dashboard Engineer
Depends on: 2.2, 2.3

Render the layout from 2.2 against the metrics from 2.3.

- Render the headline figures
- Render weekly revenue with order volume alongside it
- Render revenue by category, sorted, with margin percentage visible
- Render revenue by region with each region's share of the total
- Render the top ten products with units, revenue, and margin

> Every figure on the dashboard traces back to a computed aggregate. Nothing is placed on the page that the pipeline did not produce.

### 3.2 Verify against the acceptance criteria

Agent: Architect
Depends on: 3.1

Go back through every acceptance criterion in this document and record the measured result beside it.

- Restate each criterion with the value that was actually measured
- Flag anything that did not meet its criterion
- Record the final row counts, the drop count, and the time taken

> The verification document is honest about anything that failed. A clean report that hides a problem is worse than no report.
