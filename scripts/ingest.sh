#!/usr/bin/env bash
# Stages a dropped CSV before the Python loader touches it.
# Usage: ./scripts/ingest.sh <path-to-csv>
set -u

STAGING="data/staging"
mkdir -p "$STAGING"

# DEFECT: $1 is not quoted. Try it with a path that has a space in it.
if [ ! -f "$1" ]; then
  echo "no such file: $1" >&2
  exit 1
fi

rows=$(wc -l < "$1")
if [ "$rows" -lt 2 ]; then
  echo "file has no data rows" >&2
  exit 2
fi

header=$(head -1 "$1")
expected="order_id,customer_id,drink_id,store_id,qty,ordered_at,status"
if [ "$header" != "$expected" ]; then
  echo "bad header" >&2
  echo "  expected: $expected" >&2
  echo "  got:      $header" >&2
  exit 3
fi

cp "$1" "$STAGING/"
echo "staged $(basename "$1") — $((rows - 1)) data rows"
exit 0
