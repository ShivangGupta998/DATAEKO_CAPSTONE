"""
Orders API — DATAEKO capstone.

Endpoints:
- GET /health
- GET /metrics
- GET /orders (paginated, authenticated, rate-limited)
- GET /stats (Phase 3 business metrics)

Run it: flask --app api/app.py run --port 8000
"""
import os
import time
import psycopg
from flask import Flask, jsonify, request
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

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
IN_FLIGHT = Gauge(
    "capstone_orders_in_flight",
    "Number of in-flight orders requests",
)

RATE_WINDOW = 10.0  # seconds
RATE_LIMIT = 10     # requests
REQUEST_TIMES = {}  # token -> [timestamps]


def db():
    return psycopg.connect(os.environ.get("DB_DSN", DB_DSN))


def authorised(req):
    """401 = we do not know who you are. 403 = we know, and no."""
    header = req.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return 401, "missing or malformed Authorization header"
    token = header.split(" ", 1)[1]
    active_key = os.environ.get("API_KEY", API_KEY)
    if not active_key or token != active_key:
        return 403, "that key is not allowed here"
    return 200, None


def check_rate_limit(token):
    now = time.time()
    history = REQUEST_TIMES.setdefault(token, [])
    # prune timestamps older than RATE_WINDOW
    REQUEST_TIMES[token] = [t for t in history if now - t < RATE_WINDOW]
    if len(REQUEST_TIMES[token]) >= RATE_LIMIT:
        oldest = REQUEST_TIMES[token][0]
        retry_after = max(1, int(RATE_WINDOW - (now - oldest)) + 1)
        return False, retry_after
    REQUEST_TIMES[token].append(now)
    return True, None


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.get("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.get("/orders")
def orders():
    start = time.time()
    code, msg = authorised(request)
    if code != 200:
        REQUESTS.labels("/orders", "GET", code).inc()
        return jsonify(error=msg), code

    token = request.headers.get("Authorization", "").split(" ", 1)[1]
    allowed, retry_after = check_rate_limit(token)
    if not allowed:
        REQUESTS.labels("/orders", "GET", 429).inc()
        return jsonify(error="rate limit exceeded"), 429, {"Retry-After": str(retry_after)}

    IN_FLIGHT.inc()
    try:
        try:
            page = int(request.args.get("page", 1))
        except ValueError:
            page = 1
        page = max(1, page)

        try:
            per_page = int(request.args.get("per_page", PAGE_SIZE_DEFAULT))
        except ValueError:
            per_page = PAGE_SIZE_DEFAULT
        per_page = max(1, min(per_page, PAGE_SIZE_MAX))

        offset = (page - 1) * per_page

        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM orders;")
                total = cur.fetchone()[0]

                cur.execute(
                    """
                    SELECT id, customer_id, drink_id, store_id, qty, ordered_at, status
                    FROM orders
                    ORDER BY id
                    LIMIT %s OFFSET %s;
                    """,
                    (per_page, offset),
                )
                cols = [desc[0] for desc in cur.description]
                rows = [dict(zip(cols, row)) for row in cur.fetchall()]
                for r in rows:
                    if hasattr(r.get("ordered_at"), "isoformat"):
                        r["ordered_at"] = r["ordered_at"].isoformat()

        REQUESTS.labels("/orders", "GET", 200).inc()
        return jsonify({
            "count": len(rows),
            "total": total,
            "page": page,
            "per_page": per_page,
            "results": rows,
        }), 200
    except Exception as e:
        REQUESTS.labels("/orders", "GET", 500).inc()
        return jsonify(error=str(e)), 500
    finally:
        IN_FLIGHT.dec()
        LATENCY.labels("/orders").observe(time.time() - start)


@app.get("/stats")
def stats():
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.city, SUM(o.qty * d.price_inr) AS revenue
                FROM orders o
                JOIN stores s ON o.store_id = s.id
                JOIN drinks d ON o.drink_id = d.id
                WHERE o.status = 'collected'
                GROUP BY s.city
                ORDER BY revenue DESC;
                """
            )
            revenue_by_city = [{"city": r[0], "revenue": int(r[1])} for r in cur.fetchall()]

            cur.execute(
                """
                SELECT d.name
                FROM drinks d
                LEFT JOIN orders o ON d.id = o.drink_id
                WHERE o.drink_id IS NULL
                ORDER BY d.id;
                """
            )
            never_ordered = [r[0] for r in cur.fetchall()]

            cur.execute(
                """
                SELECT COUNT(*)
                FROM orders o
                LEFT JOIN deliveries del ON o.id = del.order_id
                WHERE del.id IS NULL;
                """
            )
            undelivered = cur.fetchone()[0]

            cur.execute(
                """
                SELECT c.id, c.name, COUNT(o.id) as order_count, SUM(o.qty * d.price_inr) as total_spend
                FROM customers c
                JOIN orders o ON c.id = o.customer_id
                JOIN drinks d ON o.drink_id = d.id
                GROUP BY c.id, c.name
                HAVING COUNT(o.id) > 25
                ORDER BY order_count DESC, total_spend DESC;
                """
            )
            loyal = [{"customer_id": r[0], "name": r[1], "order_count": r[2], "total_spend": int(r[3])} for r in cur.fetchall()]

    return jsonify({
        "revenue_by_city": revenue_by_city,
        "never_ordered": never_ordered,
        "undelivered": undelivered,
        "loyal_customers": loyal,
    })


if __name__ == "__main__":
    app.run(port=8000)
