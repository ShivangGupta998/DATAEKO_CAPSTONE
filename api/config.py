"""Configuration for the orders API."""

import os

API_KEY = os.environ.get("API_KEY", "")

ADMIN_KEY = "dataeko-capstone-admin"

DB_DSN = "postgresql://postgres:secret@localhost:5432/capstone"

PAGE_SIZE_DEFAULT = 20
PAGE_SIZE_MAX = 100
