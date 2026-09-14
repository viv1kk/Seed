"""Generate the bundled dataset, with its deliberate defects.

    python tasks.py data

Writes three CSVs to ``app/data/``. They are committed, and regenerating must
reproduce them byte for byte: every draw comes from one seeded generator in a
fixed order, and every value is formatted explicitly rather than left to a
library's float repr.

The defects are the point. Each one exists so an agent has something real to
say, and the timestamp defect in particular drives the failure and retry beat
that the whole demo is built around. See ``docs/05-DATA-AND-PIPELINE.md`` for
the table, and ``tests/test_generate_data.py`` for the assertions that hold the
volumes in place.

The two timestamp formats are exact and mutually exclusive:

    ISO        2025-03-25T14:30:00     %Y-%m-%dT%H:%M:%S
    day-first  25/03/2025 14:30        %d/%m/%Y %H:%M

That matters more than it looks. A strict ISO parse over this file must raise,
because it is the real failure the ETL agent recovers from, and a coalesced
two-format parse must then resolve every single row, because the requirement
document promises no row is dropped for a timestamp we can parse by any
reasonable rule. Anything in between, such as a timestamp Polars parses
leniently into a wrong date, would quietly hollow out the demo.
"""

import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final

from app.core.rng import Rng, make_rng

# Fixed and independent of the run seed, so changing how a run behaves never
# changes the dataset underneath it.
DATA_SEED: Final[int] = 20250101

DATA_DIR: Final[Path] = Path(__file__).resolve().parent.parent / "app" / "data"

# ---------------------------------------------------------------- volumes

PRODUCT_ROWS: Final[int] = 180
CUSTOMER_ROWS: Final[int] = 2_400

# 12,828 distinct orders plus 19 rows that repeat an order_id, which is what the
# ETL agent dedupes down to 12,828 again.
DISTINCT_ORDERS: Final[int] = 12_828
DUPLICATE_ORDERS: Final[int] = 19
TOTAL_ORDER_ROWS: Final[int] = DISTINCT_ORDERS + DUPLICATE_ORDERS

# Defect volumes, as counts rather than rates, so the test can assert them
# exactly instead of within a tolerance.
DAY_FIRST_TIMESTAMPS: Final[int] = 771  # about 6%
DIRTY_QTY_ROWS: Final[int] = 1_203  # about 9%
EMPTY_DISCOUNT_ROWS: Final[int] = 514  # about 4%
REGION_MISMATCH_ROWS: Final[int] = 385  # about 3%

# ---------------------------------------------------------------- vocabulary

REGIONS: Final[tuple[str, ...]] = ("North", "South", "East", "West", "Central")
CHANNELS: Final[tuple[str, ...]] = ("web", "mobile", "retail", "partner")
SEGMENTS: Final[tuple[str, ...]] = ("consumer", "smb", "enterprise")

CATEGORIES: Final[tuple[str, ...]] = (
    "Audio",
    "Computing",
    "Home",
    "Kitchen",
    "Lighting",
    "Mobile",
    "Outdoor",
    "Wearables",
)

PRODUCT_NOUNS: Final[tuple[str, ...]] = (
    "Headphones", "Speaker", "Keyboard", "Monitor", "Router", "Lamp",
    "Kettle", "Blender", "Backpack", "Tracker", "Charger", "Stand",
    "Adapter", "Case", "Mouse", "Webcam", "Thermostat", "Scale",
)
PRODUCT_QUALIFIERS: Final[tuple[str, ...]] = (
    "Compact", "Studio", "Pro", "Lite", "Everyday", "Precision",
    "Nordic", "Traveller", "Classic", "Mini", "Ultra", "Field",
)

STATUS_WEIGHTS: Final[tuple[tuple[str, float], ...]] = (
    ("completed", 0.86),
    ("returned", 0.08),
    ("cancelled", 0.06),
)

YEAR_START: Final[datetime] = datetime(2025, 1, 1, 0, 0, 0)
YEAR_MINUTES: Final[int] = 365 * 24 * 60


def _weighted_choice(rng: Rng, weighted: tuple[tuple[str, float], ...]) -> str:
    roll = rng.random()
    cumulative = 0.0
    for value, weight in weighted:
        cumulative += weight
        if roll < cumulative:
            return value
    return weighted[-1][0]


# ---------------------------------------------------------------- products


def generate_products(rng: Rng) -> list[dict[str, str]]:
    """180 products across 8 categories.

    ``base_price`` never reaches the CSV. It anchors both the product's
    cost_price and the unit_price on orders of it, so margin comes out as a real
    spread across the catalogue rather than a constant.
    """
    products: list[dict[str, str]] = []
    for index in range(PRODUCT_ROWS):
        base_price = round(rng.uniform(12.0, 480.0), 2)
        # 45% to 75% of the typical selling price.
        cost_price = round(base_price * rng.uniform(0.45, 0.75), 2)
        name = f"{rng.choice(PRODUCT_QUALIFIERS)} {rng.choice(PRODUCT_NOUNS)}"
        products.append(
            {
                "sku": f"SKU-{index + 1:04d}",
                "product_name": name,
                "category": CATEGORIES[index % len(CATEGORIES)],
                "cost_price": f"{cost_price:.2f}",
                "base_price": f"{base_price:.2f}",
            }
        )
    return products


# ---------------------------------------------------------------- customers


def generate_customers(rng: Rng) -> list[dict[str, str]]:
    customers: list[dict[str, str]] = []
    for index in range(CUSTOMER_ROWS):
        signup = datetime(2019, 1, 1, 0, 0, 0) + timedelta(
            days=rng.randint(0, 2_190)
        )
        customers.append(
            {
                "customer_id": f"CUST-{index + 1:05d}",
                "signup_date": signup.strftime("%Y-%m-%d"),
                "segment": _weighted_choice(
                    rng, (("consumer", 0.62), ("smb", 0.27), ("enterprise", 0.11))
                ),
                "region": rng.choice(REGIONS),
            }
        )
    return customers


# ---------------------------------------------------------------- orders


def _format_qty(rng: Rng, quantity: int, *, dirty: bool) -> str:
    """Quantity as it would arrive from an untrusted extract.

    Clean rows are plain integers. Dirty rows are padded with whitespace or
    carry a trailing ``.0``, which is what a spreadsheet export does to an
    integer column and what the ETL agent counts as it coerces.
    """
    if not dirty:
        return str(quantity)
    style = rng.randint(0, 2)
    if style == 0:
        return f" {quantity}"
    if style == 1:
        return f"{quantity} "
    return f"{quantity}.0"


def generate_orders(
    rng: Rng,
    products: list[dict[str, str]],
    customers: list[dict[str, str]],
) -> list[dict[str, str]]:
    customer_region = {row["customer_id"]: row["region"] for row in customers}

    rows: list[dict[str, object]] = []
    for index in range(DISTINCT_ORDERS):
        product = products[rng.randrange(PRODUCT_ROWS)]
        customer = customers[rng.randrange(CUSTOMER_ROWS)]
        status = _weighted_choice(rng, STATUS_WEIGHTS)

        quantity = rng.randint(1, 8)
        if status == "returned":
            # Returns carry a negative quantity, which is how the Analytics
            # Engineer keeps them out of gross revenue.
            quantity = -quantity

        unit_price = round(float(product["base_price"]) * rng.uniform(0.9, 1.1), 2)
        discount = 0.0 if rng.random() < 0.5 else round(rng.uniform(0.05, 0.35), 2)

        rows.append(
            {
                "order_id": f"ORD-{1_000_000 + index:07d}",
                "ts": YEAR_START + timedelta(minutes=rng.randrange(YEAR_MINUTES)),
                "customer_id": customer["customer_id"],
                # The order-level region agrees with the customer by default.
                # The 3% that disagree are introduced further down, so the
                # mismatch count is exact rather than incidental.
                "region": customer_region[customer["customer_id"]],
                "channel": rng.choice(CHANNELS),
                "sku": product["sku"],
                "qty": quantity,
                "unit_price": unit_price,
                "discount_pct": discount,
                "status": status,
            }
        )

    # Duplicate order_ids, each a later restatement of an existing row, so that
    # "keep the most recent" is a rule with something to choose between.
    for source in rng.sample(rows, DUPLICATE_ORDERS):
        duplicate = dict(source)
        assert isinstance(source["ts"], datetime)
        duplicate["ts"] = source["ts"] + timedelta(minutes=rng.randint(3, 240))
        rows.append(duplicate)

    rng.shuffle(rows)
    return _apply_defects(rng, rows, customer_region)


def _apply_defects(
    rng: Rng,
    rows: list[dict[str, object]],
    customer_region: dict[str, str],
) -> list[dict[str, str]]:
    """Stamp the defects onto exact row counts, then format every field.

    Selecting the rows by index up front is what makes each volume exact. The
    alternative, rolling a probability per row, lands near the target and drifts
    every time the generator changes.
    """
    indices = range(len(rows))
    day_first = set(rng.sample(indices, DAY_FIRST_TIMESTAMPS))
    dirty_qty = set(rng.sample(indices, DIRTY_QTY_ROWS))
    empty_discount = set(rng.sample(indices, EMPTY_DISCOUNT_ROWS))
    mismatched_region = set(rng.sample(indices, REGION_MISMATCH_ROWS))

    out: list[dict[str, str]] = []
    for index, row in enumerate(rows):
        timestamp = row["ts"]
        assert isinstance(timestamp, datetime)
        assert isinstance(row["qty"], int)

        region = str(row["region"])
        if index in mismatched_region:
            true_region = customer_region[str(row["customer_id"])]
            region = rng.choice([r for r in REGIONS if r != true_region])

        out.append(
            {
                "order_id": str(row["order_id"]),
                "order_ts": (
                    timestamp.strftime("%d/%m/%Y %H:%M")
                    if index in day_first
                    else timestamp.strftime("%Y-%m-%dT%H:%M:%S")
                ),
                "customer_id": str(row["customer_id"]),
                "region": region,
                "channel": str(row["channel"]),
                "sku": str(row["sku"]),
                "qty": _format_qty(rng, row["qty"], dirty=index in dirty_qty),
                "unit_price": f"{float(str(row['unit_price'])):.2f}",
                "discount_pct": (
                    "" if index in empty_discount else f"{float(str(row['discount_pct'])):.2f}"
                ),
                "status": str(row["status"]),
            }
        )
    return out


# ---------------------------------------------------------------- writing


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    """Write with explicit newlines so the committed files are byte-identical
    on every platform, rather than picking up CRLF on Windows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fieldnames, lineterminator="\n", extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)


def generate_all(out_dir: Path = DATA_DIR) -> dict[str, int]:
    rng = make_rng(DATA_SEED)

    products = generate_products(rng)
    customers = generate_customers(rng)
    orders = generate_orders(rng, products, customers)

    write_csv(out_dir / "products.csv", ["sku", "product_name", "category", "cost_price"], products)
    write_csv(
        out_dir / "customers.csv",
        ["customer_id", "signup_date", "segment", "region"],
        customers,
    )
    write_csv(
        out_dir / "orders.csv",
        [
            "order_id",
            "order_ts",
            "customer_id",
            "region",
            "channel",
            "sku",
            "qty",
            "unit_price",
            "discount_pct",
            "status",
        ],
        orders,
    )

    return {"products": len(products), "customers": len(customers), "orders": len(orders)}


def main() -> None:
    counts = generate_all()
    for name, count in counts.items():
        print(f"{name}.csv: {count:,} rows")
    print(f"written to {DATA_DIR}")


if __name__ == "__main__":
    main()
