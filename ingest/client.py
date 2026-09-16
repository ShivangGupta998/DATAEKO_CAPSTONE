"""
Orders API Client — pages through orders, handles rate limits, and respects Retry-After.
"""
import os
import sys
import time
import requests

API_URL = os.environ.get("API_URL", "http://localhost:8000")
API_KEY = os.environ.get("API_KEY", "")


def get_all_orders(api_url=API_URL, api_key=API_KEY):
    """Paginates through /orders, retrying upon HTTP 429 using Retry-After header."""
    headers = {"Authorization": f"Bearer {api_key}"}
    page = 1
    per_page = 100
    all_orders = []

    while True:
        try:
            response = requests.get(
                f"{api_url}/orders",
                headers=headers,
                params={"page": page, "per_page": per_page},
                timeout=10,
            )
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 1))
                time.sleep(retry_after)
                continue

            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            if not results:
                break

            all_orders.extend(results)
            if len(all_orders) >= data.get("total", 0) or len(results) < per_page:
                break
            page += 1
        except requests.RequestException as e:
            print(f"Request error: {e}", file=sys.stderr)
            break

    print(f"collected {len(all_orders)} orders across {page} pages")
    return all_orders


if __name__ == "__main__":
    get_all_orders()
