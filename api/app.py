"""
Orders API — DATAEKO capstone.

Endpoints you must finish are marked TODO. Everything else works.
Run it:  flask --app api/app.py run --port 8000
"""
import os
import time
import psycopg
from flask import Flask, jsonify, request
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

from api.config import API_KEY, DB_DSN, PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX

app = Flask(__name__)

REQUESTS = Counter(
    "capstone_requests_total",
    "Total HTTP requests",
    ["endpoint", "method", "status"],
)
LATENCY = Histogram(
    "capstone_request_seconds",
    "Request latency in seconds",
    ["endpoint"],
)

ORDERS_IN_FLIGHT = Gauge(
    "capstone_orders_in_flight",
    "Number of orders currently in flight",
)
def db():
    return psycopg.connect(os.environ.get("DB_DSN", DB_DSN))


def authorised(req):
    """401 = we do not know who you are. 403 = we know, and no."""
    header = req.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return 401, "missing or malformed Authorization header"
    token = header.split(" ", 1)[1]
    if token != API_KEY:
        return 403, "that key is not allowed here"
    return 200, None


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.get("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.get("/orders")
def orders():
    start = time.time()
    ORDERS_IN_FLIGHT.inc()

    try:
        code, msg = authorised(request)

        if code != 200:
            REQUESTS.labels("/orders", "GET", code).inc()
            LATENCY.labels("/orders").observe(time.time() - start)
            return jsonify(error=msg), code

        # TODO (Phase 2): pagination.
        #   ?page= and ?per_page=, per_page capped at PAGE_SIZE_MAX.
        #   The response MUST report count (this page) and total (all rows).
        #   Week 2 taught you why those are different numbers.
        raise NotImplementedError("Phase 2: implement /orders")

    finally:
        ORDERS_IN_FLIGHT.dec()


@app.get("/stats")
def stats():
    # TODO (Phase 3): return the four business answers as JSON.
    raise NotImplementedError("Phase 3: implement /stats")


if __name__ == "__main__":
    app.run(port=8000)
