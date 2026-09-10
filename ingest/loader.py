"""
CSV -> Postgres loader.

Reads data/orders.csv, validates each row, inserts the good ones and writes the
bad ones to evidence/rejected.csv with a reason.

The file has deliberately malformed rows. It must NOT crash on them.
"""
import csv
import sys
from pathlib import Path

import requests


def fetch_reference(url):
    """Fetch the drinks reference list from the running API."""
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()


def read_rows(path):
    """TODO (Phase 1): yield one dict per CSV row using the csv module."""
    raise NotImplementedError("Phase 1: implement read_rows")


def validate(row):
    """TODO (Phase 1): return (ok: bool, reason: str)."""
    raise NotImplementedError("Phase 1: implement validate")


def load(path):
    """TODO (Phase 1): insert good rows, write rejects, print a summary."""
    raise NotImplementedError("Phase 1: implement load")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python ingest/loader.py <csv-path>", file=sys.stderr)
        sys.exit(2)
    load(Path(sys.argv[1]))
