"""
CSV -> Postgres loader.

Reads data/orders.csv, validates each row, inserts the good ones and writes the
bad ones to evidence/rejected.csv with a reason.
"""
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg
import requests

from api.config import DB_DSN


EXPECTED_FIELDS = [
    "order_id",
    "customer_id",
    "drink_id",
    "store_id",
    "qty",
    "ordered_at",
    "status",
]

VALID_STATUSES = {"placed", "ready", "collected", "cancelled"}


def fetch_reference(url):
    """Fetch the drinks reference list from the running API."""
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()


def read_rows(path):
    """Yield one dictionary per CSV data row."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)

        for values in reader:
            row = {}

            for index, field in enumerate(EXPECTED_FIELDS):
                row[field] = values[index] if index < len(values) else ""

            if len(values) < len(EXPECTED_FIELDS):
                row["_row_error"] = "row is too short"
            elif len(values) > len(EXPECTED_FIELDS):
                row["_row_error"] = "row is too long"

            yield row


def validate(row):
    """Return (True, '') for a valid row or (False, reason) for a bad row."""

    if row.get("_row_error"):
        return False, row["_row_error"]

    if not row.get("customer_id", "").strip():
        return False, "customer_id is empty"

    try:
        qty = int(row["qty"])
    except (ValueError, TypeError):
        return False, "qty is not an integer"

    if qty <= 0:
        return False, "qty must be greater than zero"

    try:
        datetime.fromisoformat(row["ordered_at"])
    except (ValueError, TypeError):
        return False, "ordered_at is not a valid timestamp"

    if row.get("status") not in VALID_STATUSES:
        return False, "invalid status"

    try:
        int(row["order_id"])
        int(row["customer_id"])
        int(row["drink_id"])
        int(row["store_id"])
    except (ValueError, TypeError):
        return False, "ID field is not an integer"

    return True, ""


def load(path):
    """Insert valid rows and write rejected rows to evidence/rejected.csv."""

    rows = list(read_rows(path))
    rejected = []
    inserted = 0

    dsn = os.environ.get("DB_DSN", DB_DSN)

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            for row in rows:
                ok, reason = validate(row)

                if not ok:
                    rejected.append((row, reason))
                    continue

                cur.execute(
                    "SELECT 1 FROM drinks WHERE id = %s",
                    (int(row["drink_id"]),),
                )

                if cur.fetchone() is None:
                    rejected.append((row, "drink_id does not exist"))
                    continue

                try:
                    cur.execute(
                        """
                        INSERT INTO orders
                            (customer_id, drink_id, store_id,
                             qty, ordered_at, status)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            int(row["customer_id"]),
                            int(row["drink_id"]),
                            int(row["store_id"]),
                            int(row["qty"]),
                            row["ordered_at"],
                            row["status"],
                        ),
                    )
                    inserted += 1

                except psycopg.errors.ForeignKeyViolation:
                    conn.rollback()
                    rejected.append((row, "foreign key does not exist"))

                except psycopg.errors.UniqueViolation:
                    conn.rollback()
                    rejected.append((row, "duplicate order_id"))

    evidence = Path("evidence")
    evidence.mkdir(parents=True, exist_ok=True)

    with open(evidence / "rejected.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(EXPECTED_FIELDS + ["reason"])

        for row, reason in rejected:
            writer.writerow(
                [row.get(field, "") for field in EXPECTED_FIELDS] + [reason]
            )

    print(f"read {len(rows)} rows")
    print(f"inserted {inserted}")
    print(f"rejected {len(rejected)} -> evidence/rejected.csv")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python ingest/loader.py <csv-path>", file=sys.stderr)
        sys.exit(2)

    load(Path(sys.argv[1]))
