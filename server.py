#!/usr/bin/env python3
"""
Counter — a local-first sales dashboard.

    python3 server.py

Then open http://127.0.0.1:8787

Everything is stored in a SQLite database next to this file.
No third-party packages, no build step, no cloud account.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import mimetypes
import os
import random
import re
import sqlite3
import sys
import threading
import traceback
import webbrowser
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DEFAULT_DB = os.path.join(BASE_DIR, "sales.db")
DB_PATH = os.environ.get("COUNTER_DB", DEFAULT_DB)
BIND_HOST = "127.0.0.1"
LOOPBACK_NAMES = {"127.0.0.1", "localhost", "::1"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS sales (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT    NOT NULL,
    product     TEXT    NOT NULL,
    category    TEXT    NOT NULL DEFAULT 'General',
    channel     TEXT    NOT NULL DEFAULT 'Online',
    units       INTEGER NOT NULL DEFAULT 1 CHECK (units > 0),
    unit_price  REAL    NOT NULL DEFAULT 0 CHECK (unit_price >= 0),
    customer    TEXT    NOT NULL DEFAULT '',
    notes       TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(date);
CREATE INDEX IF NOT EXISTS idx_sales_category ON sales(category);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

CATALOG = [
    ("Aurora Wireless Earbuds", "Electronics", 89.00, 3),
    ("Pulse Bluetooth Speaker", "Electronics", 64.50, 2),
    ("Nimbus Desk Lamp", "Home", 42.00, 3),
    ("Terra Ceramic Mug Set", "Home", 28.00, 4),
    ("Linen Throw Blanket", "Home", 74.00, 2),
    ("Everyday Canvas Tote", "Accessories", 32.00, 4),
    ("Minimalist Leather Wallet", "Accessories", 48.00, 3),
    ("Trail Water Bottle", "Accessories", 26.50, 3),
    ("Relaxed Fit Tee", "Apparel", 34.00, 4),
    ("Merino Crew Socks", "Apparel", 18.00, 5),
    ("Focus Herbal Tea", "Wellness", 14.00, 4),
    ("Recovery Foam Roller", "Wellness", 22.50, 2),
]

CUSTOMERS = [
    "Maya Chen", "Liam Patel", "Sofia Rossi", "Noah Williams", "Amara Okafor",
    "Ethan Brooks", "Isla Murphy", "Diego Alvarez", "Hana Sato", "Oliver Grant",
    "Priya Nair", "Lucas Meyer", "Ava Thompson", "Kwame Mensah", "Elena Petrova",
    "Jack Wilson", "Nadia Haddad", "Ben Carter", "Chloe Dubois", "Arjun Rao",
    "Freya Larsen", "Mateo Silva", "Zoe Kim", "Sam Taylor", "Leila Aziz",
]

CHANNELS = [("Online", 52), ("In-store", 30), ("Wholesale", 18)]
DEMO_DAYS = 120
DEMO_SALES = 320


class ValidationError(Exception):
    def __init__(self, errors):
        self.errors = errors if isinstance(errors, list) else [errors]
        super().__init__("; ".join(str(e) for e in self.errors))


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_meta(conn: sqlite3.Connection, key: str):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def seed_demo(conn: sqlite3.Connection) -> int:
    rng = random.Random(20261106)
    channel_names = [c for c, _ in CHANNELS]
    channel_weights = [w for _, w in CHANNELS]
    today = date.today()
    weights = [1.0 - 0.55 * (offset / (DEMO_DAYS - 1)) for offset in range(DEMO_DAYS)]
    rows = []
    for _ in range(DEMO_SALES):
        product, category, base_price, weight = rng.choices(CATALOG, weights=[c[3] for c in CATALOG], k=1)[0]
        channel = rng.choices(channel_names, weights=channel_weights, k=1)[0]
        # A gentle upward trend: recent days carry a little more volume.
        offset = rng.choices(range(DEMO_DAYS), weights=weights, k=1)[0]
        sold = today - timedelta(days=offset)
        if channel == "Wholesale":
            units = rng.randint(6, 24)
        else:
            units = rng.choices([1, 1, 1, 2, 2, 3, 4], k=1)[0]
        price = round(base_price * rng.uniform(0.92, 1.0) / 0.05) * 0.05
        price = round(price, 2)
        customer = ""
        if channel == "Wholesale":
            customer = rng.choice(CUSTOMERS) + " Studio"
        elif rng.random() < 0.45:
            customer = rng.choice(CUSTOMERS)
        rows.append((
            sold.isoformat(), product, category, channel, units, price, customer, "",
        ))
    conn.executemany(
        "INSERT INTO sales(date, product, category, channel, units, unit_price, customer, notes) "
        "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    set_meta(conn, "demo", "1")
    return len(rows)


def init_db() -> None:
    with db_connect() as conn:
        conn.executescript(SCHEMA)
        if get_meta(conn, "initialized") is None:
            count = conn.execute("SELECT COUNT(*) AS n FROM sales").fetchone()["n"]
            if count == 0:
                seed_demo(conn)
            set_meta(conn, "initialized", "1")


def clean_text(value, limit: int = 160) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()[:limit]


def is_iso_date(value: str) -> bool:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value or ""):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def parse_sale(payload) -> dict:
    if not isinstance(payload, dict):
        raise ValidationError("Each sale must be an object.")

    errors = []
    sale_date = clean_text(payload.get("date"), 10)
    if not is_iso_date(sale_date):
        errors.append("date must be YYYY-MM-DD")

    product = clean_text(payload.get("product"), 120)
    if not product:
        errors.append("product is required")

    category = clean_text(payload.get("category"), 60) or "General"
    channel = clean_text(payload.get("channel"), 40) or "Online"

    try:
        units = int(float(payload.get("units", 1)))
        if not 1 <= units <= 1_000_000:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("units must be a whole number of at least 1")
        units = 1

    try:
        unit_price = round(float(payload.get("unit_price", 0)), 2)
        if not 0 <= unit_price <= 100_000_000:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("unit_price must be 0 or more")
        unit_price = 0.0

    if errors:
        raise ValidationError(errors)

    return {
        "date": sale_date,
        "product": product,
        "category": category,
        "channel": channel,
        "units": units,
        "unit_price": unit_price,
        "customer": clean_text(payload.get("customer"), 120),
        "notes": clean_text(payload.get("notes"), 500),
    }


def query_filters(qs: dict) -> dict:
    def one(name: str) -> str | None:
        raw = qs.get(name, [""])
        value = raw[0].strip() if raw and isinstance(raw[0], str) else ""
        return value or None

    filters = {"start": None, "end": None, "channel": None, "category": None, "q": None}
    start = one("start")
    end = one("end")
    if start and is_iso_date(start):
        filters["start"] = start
    if end and is_iso_date(end):
        filters["end"] = end
    channel = one("channel")
    if channel and channel.lower() != "all":
        filters["channel"] = channel
    category = one("category")
    if category and category.lower() != "all":
        filters["category"] = category
    filters["q"] = one("q")
    return filters


def where_clause(filters: dict) -> tuple[str, list]:
    clauses, params = [], []
    if filters.get("start"):
        clauses.append("date >= ?")
        params.append(filters["start"])
    if filters.get("end"):
        clauses.append("date <= ?")
        params.append(filters["end"])
    if filters.get("channel"):
        clauses.append("channel = ?")
        params.append(filters["channel"])
    if filters.get("category"):
        clauses.append("category = ?")
        params.append(filters["category"])
    if filters.get("q"):
        needle = f"%{filters['q']}%"
        clauses.append("(product LIKE ? OR category LIKE ? OR customer LIKE ? OR notes LIKE ? OR channel LIKE ?)")
        params.extend([needle] * 5)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def fetch_sales(conn: sqlite3.Connection, filters: dict, limit: int | None = None) -> list[dict]:
    sql, params = where_clause(filters)
    sql = "SELECT * FROM sales" + sql + " ORDER BY date DESC, id DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    rows = []
    for row in conn.execute(sql, params):
        item = dict(row)
        item["total"] = round(item["units"] * item["unit_price"], 2)
        rows.append(item)
    return rows


def pct_change(current: float, previous: float):
    if previous is None:
        return None
    if previous == 0:
        return None if current == 0 else 100.0
    return round((current - previous) / previous * 100, 1)


def bucket_start(d: date, granularity: str) -> date:
    if granularity == "week":
        return d - timedelta(days=d.weekday())
    if granularity == "month":
        return d.replace(day=1)
    return d


def add_bucket(d: date, granularity: str) -> date:
    if granularity == "week":
        return d + timedelta(days=7)
    if granularity == "month":
        return (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return d + timedelta(days=1)


def build_summary(conn: sqlite3.Connection, filters: dict) -> dict:
    rows = fetch_sales(conn, filters)
    revenue = sum(r["total"] for r in rows)
    units = sum(r["units"] for r in rows)
    count = len(rows)

    previous = None
    if filters.get("start") and filters.get("end"):
        start = datetime.strptime(filters["start"], "%Y-%m-%d").date()
        end = datetime.strptime(filters["end"], "%Y-%m-%d").date()
        span = (end - start).days + 1
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=span - 1)
        prev_filters = {
            "start": prev_start.isoformat(),
            "end": prev_end.isoformat(),
            "channel": filters.get("channel"),
            "category": filters.get("category"),
            "q": None,
        }
        prev_rows = fetch_sales(conn, prev_filters)
        prev_revenue = sum(r["total"] for r in prev_rows)
        prev_units = sum(r["units"] for r in prev_rows)
        prev_count = len(prev_rows)
        previous = {
            "revenue": prev_revenue,
            "units": prev_units,
            "sales": prev_count,
            "avg": (prev_revenue / prev_count) if prev_count else 0,
            "count": prev_count,
        }

    changes = {
        "revenue": pct_change(revenue, previous["revenue"]) if previous else None,
        "units": pct_change(units, previous["units"]) if previous else None,
        "sales": pct_change(count, previous["sales"]) if previous else None,
        "avg": pct_change(revenue / count if count else 0, previous["avg"]) if previous else None,
    }

    if rows:
        series_start = datetime.strptime(filters["start"], "%Y-%m-%d").date() if filters.get("start") else datetime.strptime(min(r["date"] for r in rows), "%Y-%m-%d").date()
        series_end = datetime.strptime(filters["end"], "%Y-%m-%d").date() if filters.get("end") else datetime.strptime(max(r["date"] for r in rows), "%Y-%m-%d").date()
        span_days = (series_end - series_start).days + 1
        granularity = "day" if span_days <= 62 else ("week" if span_days <= 400 else "month")
    else:
        series_start = datetime.strptime(filters["start"], "%Y-%m-%d").date() if filters.get("start") else date.today()
        series_end = datetime.strptime(filters["end"], "%Y-%m-%d").date() if filters.get("end") else series_start
        granularity = "day"

    buckets: dict[str, dict] = {}
    cursor = bucket_start(series_start, granularity)
    end_bucket = bucket_start(series_end, granularity)
    while cursor <= end_bucket:
        key = cursor.isoformat()
        buckets[key] = {"date": key, "revenue": 0.0, "sales": 0, "units": 0}
        cursor = add_bucket(cursor, granularity)

    day_totals: dict[str, float] = {}
    category_map: dict[str, dict] = {}
    product_map: dict[str, dict] = {}
    channel_map: dict[str, dict] = {}

    for row in rows:
        d = datetime.strptime(row["date"], "%Y-%m-%d").date()
        key = bucket_start(d, granularity).isoformat()
        if key in buckets:
            buckets[key]["revenue"] += row["total"]
            buckets[key]["sales"] += 1
            buckets[key]["units"] += row["units"]

        cat = category_map.setdefault(row["category"], {"name": row["category"], "revenue": 0.0, "sales": 0, "units": 0})
        cat["revenue"] += row["total"]
        cat["sales"] += 1
        cat["units"] += row["units"]

        prod = product_map.setdefault(row["product"], {
            "name": row["product"], "category": row["category"],
            "revenue": 0.0, "sales": 0, "units": 0,
        })
        prod["revenue"] += row["total"]
        prod["sales"] += 1
        prod["units"] += row["units"]

        chan = channel_map.setdefault(row["channel"], {"name": row["channel"], "revenue": 0.0, "sales": 0, "units": 0})
        chan["revenue"] += row["total"]
        chan["sales"] += 1
        chan["units"] += row["units"]

        day_totals[row["date"]] = day_totals.get(row["date"], 0.0) + row["total"]

    def cleaned(items):
        return sorted(
            ({**item, "revenue": round(item["revenue"], 2)} for item in items),
            key=lambda x: x["revenue"],
            reverse=True,
        )

    points = []
    for bucket in buckets.values():
        points.append({
            "date": bucket["date"],
            "revenue": round(bucket["revenue"], 2),
            "sales": bucket["sales"],
            "units": bucket["units"],
        })

    best_day = None
    if day_totals:
        best_date = max(day_totals, key=day_totals.get)
        best_day = {"date": best_date, "revenue": round(day_totals[best_date], 2)}

    return {
        "totals": {
            "revenue": round(revenue, 2),
            "sales": count,
            "units": units,
            "avg": round(revenue / count, 2) if count else 0,
        },
        "changes": changes,
        "previous": previous,
        "series": {"granularity": granularity, "points": points},
        "categories": cleaned(category_map.values()),
        "products": cleaned(product_map.values())[:8],
        "channels": cleaned(channel_map.values()),
        "best_day": best_day,
        "recent": rows[:6],
    }


def meta_payload(conn: sqlite3.Connection) -> dict:
    total = conn.execute("SELECT COUNT(*) AS n FROM sales").fetchone()["n"]
    updated = conn.execute("SELECT MAX(created_at) AS t FROM sales").fetchone()["t"]
    categories = [r["category"] for r in conn.execute(
        "SELECT category, COUNT(*) AS n FROM sales GROUP BY category ORDER BY n DESC, category"
    )]
    channels = [r["channel"] for r in conn.execute(
        "SELECT channel, COUNT(*) AS n FROM sales GROUP BY channel ORDER BY n DESC, channel"
    )]
    products = [r["product"] for r in conn.execute(
        "SELECT product, COUNT(*) AS n FROM sales GROUP BY product ORDER BY n DESC, product LIMIT 500"
    )]
    return {
        "total": total,
        "categories": categories,
        "channels": channels,
        "products": products,
        "demo": get_meta(conn, "demo") == "1",
        "db_path": DB_PATH,
        "updated_at": (updated or "").replace(" ", "T") + "Z" if updated else None,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "Counter/1.0"
    protocol_version = "HTTP/1.1"

    # ---------------------------------------------------------------- helpers

    def log_message(self, fmt, *args):
        if args and str(args[0]).startswith(("4", "5")):
            sys.stderr.write("  %s\n" % (fmt % args))

    def _security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")

    def send_json(self, status: int, payload) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_error_json(self, status: int, message: str, errors=None) -> None:
        payload = {"error": message}
        if errors:
            payload["details"] = errors
        self.send_json(status, payload)

    def take_body(self) -> bytes:
        """Read the request body exactly once so keep-alive stays in sync."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return b""
        if length > 25_000_000:
            raise ValidationError("Request body is too large.")
        return self.rfile.read(length)

    def _host_name(self) -> str:
        host = (self.headers.get("Host") or "").strip().lower()
        if host.startswith("["):
            return host[1:].split("]", 1)[0]
        return host.rsplit(":", 1)[0]

    def _request_is_same_site(self) -> bool:
        """Block other websites from changing data through the local API."""
        local_only = BIND_HOST in LOOPBACK_NAMES
        if local_only and self._host_name() not in LOOPBACK_NAMES:
            return False
        source = self.headers.get("Origin") or self.headers.get("Referer")
        if not source:
            return True
        try:
            parsed = urlparse(source)
        except ValueError:
            return False
        if local_only and (parsed.hostname or "").lower() not in LOOPBACK_NAMES:
            return False
        return parsed.netloc.lower() == (self.headers.get("Host") or "").strip().lower()

    def read_json(self):
        raw = getattr(self, "_request_body", b"")
        if not raw:
            raw = self.take_body()
            self._request_body = raw
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValidationError("Request body must be valid JSON.")

    def serve_static(self, path: str) -> None:
        if path in ("", "/"):
            relative = "index.html"
        else:
            relative = path.lstrip("/")
        candidate = os.path.realpath(os.path.join(STATIC_DIR, relative))
        root = os.path.realpath(STATIC_DIR)
        if not (candidate == root or candidate.startswith(root + os.sep)) or not os.path.isfile(candidate):
            self.send_error_json(404, "Not found")
            return
        try:
            with open(candidate, "rb") as fh:
                body = fh.read()
        except OSError:
            self.send_error_json(404, "Not found")
            return
        mime = mimetypes.guess_type(candidate)[0] or "application/octet-stream"
        if mime.startswith("text/") or mime in ("application/javascript", "application/json"):
            mime += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self._security_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    # ------------------------------------------------------------------ verbs

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            if path == "/favicon.ico":
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            if path == "/api/meta":
                with db_connect() as conn:
                    self.send_json(200, meta_payload(conn))
                return

            if path == "/api/summary":
                filters = query_filters(query)
                with db_connect() as conn:
                    self.send_json(200, build_summary(conn, filters))
                return

            if path == "/api/sales":
                filters = query_filters(query)
                limit = None
                raw_limit = query.get("limit", [""])[0]
                if raw_limit.isdigit():
                    limit = max(1, min(int(raw_limit), 50_000))
                with db_connect() as conn:
                    items = fetch_sales(conn, filters, limit=limit)
                    self.send_json(200, {"items": items, "total": len(items)})
                return

            if path == "/api/export.csv":
                filters = query_filters(query)
                with db_connect() as conn:
                    items = fetch_sales(conn, filters)
                buffer = io.StringIO()
                writer = csv.writer(buffer)
                writer.writerow(["date", "product", "category", "channel", "units", "unit_price", "total", "customer", "notes"])
                for item in items:
                    writer.writerow([
                        item["date"], item["product"], item["category"], item["channel"],
                        item["units"], f'{item["unit_price"]:.2f}', f'{item["total"]:.2f}',
                        item["customer"], item["notes"],
                    ])
                body = buffer.getvalue().encode("utf-8-sig")
                filename = f"counter-sales-{date.today().isoformat()}.csv"
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(body)))
                self._security_headers()
                self.end_headers()
                self.wfile.write(body)
                return

            if path.startswith("/api/"):
                self.send_error_json(404, "Unknown API endpoint")
                return

            self.serve_static(path)

        except ValidationError as exc:
            self.send_error_json(400, "Invalid request", exc.errors)
        except Exception:
            traceback.print_exc()
            self.send_error_json(500, "Something went wrong on the server.")

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        try:
            self._request_body = self.take_body()
            if not self._request_is_same_site():
                self.send_error_json(403, "This request did not come from the Counter app.")
                return
            parsed = urlparse(self.path)
            if parsed.path == "/api/sales":
                payload = self.read_json()
                sale = parse_sale(payload)
                with db_connect() as conn:
                    cursor = conn.execute(
                        "INSERT INTO sales(date, product, category, channel, units, unit_price, customer, notes) "
                        "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                        (sale["date"], sale["product"], sale["category"], sale["channel"],
                         sale["units"], sale["unit_price"], sale["customer"], sale["notes"]),
                    )
                    created = dict(conn.execute("SELECT * FROM sales WHERE id = ?", (cursor.lastrowid,)).fetchone())
                created["total"] = round(created["units"] * created["unit_price"], 2)
                self.send_json(201, created)
                return

            if parsed.path == "/api/import":
                payload = self.read_json()
                rows = payload.get("rows") if isinstance(payload, dict) else None
                if not isinstance(rows, list):
                    raise ValidationError("Expected a 'rows' array.")
                if len(rows) > 20_000:
                    raise ValidationError("Import is limited to 20,000 rows at a time.")
                inserted, skipped, errors = 0, 0, []
                with db_connect() as conn:
                    for index, raw in enumerate(rows, start=1):
                        try:
                            sale = parse_sale(raw)
                            conn.execute(
                                "INSERT INTO sales(date, product, category, channel, units, unit_price, customer, notes) "
                                "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                                (sale["date"], sale["product"], sale["category"], sale["channel"],
                                 sale["units"], sale["unit_price"], sale["customer"], sale["notes"]),
                            )
                            inserted += 1
                        except ValidationError as exc:
                            skipped += 1
                            if len(errors) < 8:
                                errors.append({"row": index, "message": "; ".join(exc.errors)})
                self.send_json(200, {"inserted": inserted, "skipped": skipped, "errors": errors})
                return

            if parsed.path == "/api/seed":
                with db_connect() as conn:
                    count = conn.execute("SELECT COUNT(*) AS n FROM sales").fetchone()["n"]
                    added = seed_demo(conn) if count == 0 else 0
                self.send_json(200, {"inserted": added})
                return

            self.send_error_json(404, "Unknown API endpoint")

        except ValidationError as exc:
            self.send_error_json(400, "Invalid request", exc.errors)
        except Exception:
            traceback.print_exc()
            self.send_error_json(500, "Something went wrong on the server.")

    def do_PUT(self):
        try:
            self._request_body = self.take_body()
            if not self._request_is_same_site():
                self.send_error_json(403, "This request did not come from the Counter app.")
                return
            match = re.fullmatch(r"/api/sales/(\d+)", urlparse(self.path).path)
            if not match:
                self.send_error_json(404, "Unknown API endpoint")
                return
            sale_id = int(match.group(1))
            payload = self.read_json()
            sale = parse_sale(payload)
            with db_connect() as conn:
                exists = conn.execute("SELECT id FROM sales WHERE id = ?", (sale_id,)).fetchone()
                if not exists:
                    self.send_error_json(404, "Sale not found")
                    return
                conn.execute(
                    "UPDATE sales SET date = ?, product = ?, category = ?, channel = ?, units = ?, "
                    "unit_price = ?, customer = ?, notes = ? WHERE id = ?",
                    (sale["date"], sale["product"], sale["category"], sale["channel"],
                     sale["units"], sale["unit_price"], sale["customer"], sale["notes"], sale_id),
                )
                updated = dict(conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone())
            updated["total"] = round(updated["units"] * updated["unit_price"], 2)
            self.send_json(200, updated)
        except ValidationError as exc:
            self.send_error_json(400, "Invalid request", exc.errors)
        except Exception:
            traceback.print_exc()
            self.send_error_json(500, "Something went wrong on the server.")

    def do_DELETE(self):
        try:
            self._request_body = self.take_body()
            if not self._request_is_same_site():
                self.send_error_json(403, "This request did not come from the Counter app.")
                return
            path = urlparse(self.path).path
            if path == "/api/sales/all":
                with db_connect() as conn:
                    deleted = conn.execute("SELECT COUNT(*) AS n FROM sales").fetchone()["n"]
                    conn.execute("DELETE FROM sales")
                    set_meta(conn, "demo", "0")
                self.send_json(200, {"deleted": deleted})
                return
            match = re.fullmatch(r"/api/sales/(\d+)", path)
            if not match:
                self.send_error_json(404, "Unknown API endpoint")
                return
            sale_id = int(match.group(1))
            with db_connect() as conn:
                cursor = conn.execute("DELETE FROM sales WHERE id = ?", (sale_id,))
                deleted = cursor.rowcount
            if not deleted:
                self.send_error_json(404, "Sale not found")
                return
            self.send_json(200, {"deleted": 1})
        except Exception:
            traceback.print_exc()
            self.send_error_json(500, "Something went wrong on the server.")


def main():
    global DB_PATH, BIND_HOST
    parser = argparse.ArgumentParser(description="Counter — local sales dashboard")
    parser.add_argument("--port", type=int, default=8787, help="port to serve on (default: 8787)")
    parser.add_argument("--host", default="127.0.0.1", help="host to bind (default: 127.0.0.1)")
    parser.add_argument("--db", default=DB_PATH, help="path to the SQLite database")
    parser.add_argument("--no-open", action="store_true", help="don't open the browser automatically")
    args = parser.parse_args()

    BIND_HOST = args.host
    DB_PATH = os.path.abspath(os.path.expanduser(args.db))

    os.makedirs(STATIC_DIR, exist_ok=True)
    init_db()

    httpd = None
    port = args.port
    for offset in range(20):
        try:
            httpd = ThreadingHTTPServer((args.host, args.port + offset), Handler)
            port = args.port + offset
            break
        except OSError:
            continue
    if httpd is None:
        print("Could not find a free port between %d and %d." % (args.port, args.port + 19))
        sys.exit(1)

    url = f"http://{args.host}:{port}"
    print()
    print("  \033[1mCounter\033[0m — sales dashboard")
    print("  " + "-" * 38)
    print(f"  Running at  \033[36m{url}\033[0m")
    print(f"  Database    {DB_PATH}")
    print("  Stop with   Ctrl+C")
    print()

    if not args.no_open and args.host in ("127.0.0.1", "localhost", "0.0.0.0"):
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped. Your data is safe in sales.db.\n")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
