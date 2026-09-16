"""
CSV -> Postgres loader.

Reads data/orders.csv, validates each row, inserts the good ones and writes the
bad ones to evidence/rejected.csv with a reason.

The file has deliberately malformed rows. It must NOT crash on them.
"""
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg
import requests

from api.config import DB_DSN

VALID_STATUSES = {"placed", "ready", "collected", "cancelled"}


def fetch_reference(url):
    """Fetch the drinks reference list from the running API."""
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()


def read_rows(path):
    """Yield one dict per CSV row using the csv module."""
    with open(path, mode="r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        try:
            raw_header = next(reader)
        except StopIteration:
            return
        header = [col.strip() for col in raw_header]
        for row in reader:
            if not row:
                continue
            if len(row) == len(header):
                yield dict(zip(header, (v.strip() for v in row)))
            elif len(row) < len(header):
                d = dict(zip(header, (v.strip() for v in row)))
                d["_malformed"] = "row too short"
                yield d
            else:
                d = dict(zip(header, (row[i].strip() for i in range(len(header)))))
                d["_malformed"] = "row too long"
                d["_extra"] = [v.strip() for v in row[len(header):]]
                yield d


def validate(row):
    """Validate a single order row dict. Return (ok: bool, reason: str)."""
    if not isinstance(row, dict):
        return False, "row is not a dictionary"

    if row.get("_malformed") == "row too short":
        return False, "row has too few columns"
    if row.get("_malformed") == "row too long":
        return False, "row has too many columns"

    # customer_id
    cid_str = row.get("customer_id")
    if cid_str is None or not str(cid_str).strip():
        return False, "customer_id cannot be empty"
    try:
        cid = int(cid_str)
        if cid <= 0:
            return False, f"customer_id must be positive, got {cid}"
    except ValueError:
        return False, f"customer_id is not a valid integer: {cid_str!r}"

    # qty
    qty_str = row.get("qty")
    if qty_str is None or not str(qty_str).strip():
        return False, "qty cannot be empty"
    try:
        qty = int(qty_str)
        if qty <= 0:
            return False, f"qty must be greater than 0, got {qty}"
    except ValueError:
        return False, f"qty is not a valid integer: {qty_str!r}"

    # status
    status = row.get("status")
    if not status or status not in VALID_STATUSES:
        return False, f"invalid status: {status!r} (must be one of {sorted(VALID_STATUSES)})"

    # ordered_at
    ordered_at = row.get("ordered_at")
    if not ordered_at:
        return False, "ordered_at cannot be empty"
    try:
        datetime.fromisoformat(ordered_at)
    except Exception:
        return False, f"ordered_at is not a valid ISO timestamp: {ordered_at!r}"

    # drink_id (drinks table has IDs 1 through 18)
    did_str = row.get("drink_id")
    if did_str is None or not str(did_str).strip():
        return False, "drink_id cannot be empty"
    try:
        did = int(did_str)
        if did <= 0 or did > 18:
            return False, f"drink_id {did} does not exist in drinks menu"
    except ValueError:
        return False, f"drink_id is not a valid integer: {did_str!r}"

    # store_id (stores table has IDs 1 through 6)
    sid_str = row.get("store_id")
    if sid_str is None or not str(sid_str).strip():
        return False, "store_id cannot be empty"
    try:
        sid = int(sid_str)
        if sid <= 0 or sid > 6:
            return False, f"store_id {sid} does not exist"
    except ValueError:
        return False, f"store_id is not a valid integer: {sid_str!r}"

    # order_id
    oid_str = row.get("order_id")
    if oid_str is not None and str(oid_str).strip():
        try:
            oid = int(oid_str)
            if oid <= 0:
                return False, f"order_id must be positive, got {oid}"
        except ValueError:
            return False, f"order_id is not a valid integer: {oid_str!r}"

    return True, ""


def load(path):
    """Insert good rows into Postgres, write rejects to evidence/rejected.csv, and print summary."""
    path = Path(path)
    rows = list(read_rows(path))
    good_rows = []
    bad_rows = []

    for row in rows:
        ok, reason = validate(row)
        if ok:
            good_rows.append(row)
        else:
            r = dict(row)
            r["reason"] = reason
            bad_rows.append(r)

    # Insert into PostgreSQL inside a single transaction
    db_url = os.environ.get("DB_DSN", DB_DSN)
    try:
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                for r in good_rows:
                    cur.execute(
                        """
                        INSERT INTO orders (id, customer_id, drink_id, store_id, qty, ordered_at, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            customer_id = EXCLUDED.customer_id,
                            drink_id = EXCLUDED.drink_id,
                            store_id = EXCLUDED.store_id,
                            qty = EXCLUDED.qty,
                            ordered_at = EXCLUDED.ordered_at,
                            status = EXCLUDED.status;
                        """,
                        (
                            int(r["order_id"]),
                            int(r["customer_id"]),
                            int(r["drink_id"]),
                            int(r["store_id"]),
                            int(r["qty"]),
                            r["ordered_at"],
                            r["status"],
                        ),
                    )
            conn.commit()
    except Exception as e:
        print(f"Database insertion error: {e}", file=sys.stderr)
        raise

    evidence_dir = Path(__file__).resolve().parent.parent / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    rejected_path = evidence_dir / "rejected.csv"

    fieldnames = ["order_id", "customer_id", "drink_id", "store_id", "qty", "ordered_at", "status", "reason"]
    with open(rejected_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in bad_rows:
            writer.writerow(r)

    print(f"read {len(rows)} rows")
    print(f"inserted {len(good_rows)}")
    print(f"rejected {len(bad_rows)} -> evidence/rejected.csv")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python ingest/loader.py <csv-path>", file=sys.stderr)
        sys.exit(2)
    load(Path(sys.argv[1]))
