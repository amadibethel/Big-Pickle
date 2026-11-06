#!/usr/bin/env python3
"""
Counter — shared data layer.

Used by both entry points:

* ``server.py``  — local HTTP server backed by SQLite (no dependencies).
* ``api/index.py`` — Vercel serverless function backed by Postgres.

The SQLite path stays dependency-free. Postgres support uses ``pg8000``
(pure Python) and is only imported when a database URL is configured.
"""

from __future__ import annotations

import os
import random
import re
import sqlite3
import ssl
import threading
import time
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, unquote, urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(BASE_DIR, "sales.db")
LOOPBACK_NAMES = {"127.0.0.1", "localhost", "::1"}

# Any of these environment variables switches the app to Postgres. The Neon
# integration on Vercel sets DATABASE_URL automatically.
DATABASE_ENV_VARS = (
    "DATABASE_URL",
    "POSTGRES_URL",
    "POSTGRES_URL_NON_POOLING",
    "NEON_DATABASE_URL",
)

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

PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS sales (
    id          BIGSERIAL PRIMARY KEY,
    date        TEXT    NOT NULL,
    product     TEXT    NOT NULL,
    category    TEXT    NOT NULL DEFAULT 'General',
    channel     TEXT    NOT NULL DEFAULT 'Online',
    units       INTEGER NOT NULL DEFAULT 1 CHECK (units > 0),
    unit_price  DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (unit_price >= 0),
    customer    TEXT    NOT NULL DEFAULT '',
    notes       TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
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

SALE_COLUMNS = ("date", "product", "category", "channel", "units", "unit_price", "customer", "notes")

_sqlite_path = os.environ.get("COUNTER_DB", DEFAULT_DB)
_init_lock = threading.Lock()
_initialized = False


class ValidationError(Exception):
    def __init__(self, errors):
        self.errors = errors if isinstance(errors, list) else [errors]
        super().__init__("; ".join(str(e) for e in self.errors))


# --------------------------------------------------------------------- config


def configure(sqlite_path: str | None = None) -> str:
    """Point the local SQLite backend at a specific database file."""
    global _sqlite_path
    if sqlite_path:
        _sqlite_path = os.path.abspath(os.path.expanduser(sqlite_path))
    return _sqlite_path


def sqlite_path() -> str:
    return _sqlite_path


def database_url() -> str:
    for name in DATABASE_ENV_VARS:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def using_postgres() -> bool:
    return bool(database_url())


def database_label() -> str:
    if not using_postgres():
        return _sqlite_path
    params = _pg_params(database_url())
    return f"Postgres · {params['host']}/{params['database']}"


# ----------------------------------------------------------------- connection


class _Result:
    """Small DB-API result wrapper that returns dict rows for both backends."""

    __slots__ = ("_rows", "rowcount", "lastrowid")

    def __init__(self, rows, rowcount=None, lastrowid=None):
        self._rows = rows
        self.rowcount = len(rows) if rowcount is None or rowcount < 0 else rowcount
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def __iter__(self):
        return iter(self._rows)

    def __len__(self):
        return len(self._rows)

    def __getitem__(self, index):
        return self._rows[index]


class SqliteConnection:
    backend = "sqlite"

    def __init__(self, path: str):
        self._raw = sqlite3.connect(path, timeout=15)
        self._raw.row_factory = sqlite3.Row
        self._raw.execute("PRAGMA journal_mode = WAL")
        self._raw.execute("PRAGMA foreign_keys = ON")

    def execute(self, sql: str, params=()) -> _Result:
        cursor = self._raw.execute(sql, tuple(params))
        rows = [dict(row) for row in cursor.fetchall()]
        return _Result(rows, cursor.rowcount, cursor.lastrowid)

    def executemany(self, sql: str, seq) -> _Result:
        cursor = self._raw.executemany(sql, seq)
        return _Result([], cursor.rowcount, cursor.lastrowid)

    def executescript(self, script: str) -> None:
        self._raw.executescript(script)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self._raw.commit()
            else:
                self._raw.rollback()
        finally:
            self._raw.close()
        return False


def _pg8000():
    try:
        import pg8000.dbapi as pg8000
    except ImportError as exc:  # pragma: no cover - only on misconfigured cloud
        raise RuntimeError(
            "Postgres support needs the pg8000 package. "
            "Install it with: python3 -m pip install -r requirements.txt"
        ) from exc
    return pg8000


def _pg_params(url: str) -> dict:
    parsed = urlparse(url)
    if parsed.scheme not in ("postgres", "postgresql"):
        raise RuntimeError("DATABASE_URL must start with postgres:// or postgresql://")
    query = parse_qs(parsed.query)
    host = parsed.hostname or "localhost"
    sslmode = (query.get("sslmode") or [""])[0].strip().lower()
    if not sslmode:
        sslmode = "disable" if host in LOOPBACK_NAMES else "require"
    return {
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "host": host,
        "port": parsed.port or 5432,
        "database": (parsed.path or "/").lstrip("/") or "postgres",
        "sslmode": sslmode,
    }


def _pg_ssl_context(sslmode: str):
    if sslmode in ("disable", "allow", "prefer", ""):
        return None
    return ssl.create_default_context()


def _pg_sql(sql: str) -> str:
    # pg8000 uses the DB-API "format" paramstyle, and Postgres spells the
    # case-insensitive search operator ILIKE. All of our SQL is internal.
    return re.sub(r"\bLIKE\b", "ILIKE", sql.replace("?", "%s"))


class PgConnection:
    backend = "postgres"

    def __init__(self, url: str):
        params = _pg_params(url)
        sslmode = params.pop("sslmode")
        self._raw = None
        last_error = None
        for attempt in range(2):
            try:
                self._raw = _pg8000().connect(
                    **params,
                    ssl_context=_pg_ssl_context(sslmode),
                    timeout=15,
                )
                break
            except Exception as exc:  # Neon can be slow to wake up
                last_error = exc
                if attempt == 0:
                    time.sleep(0.5)
        if self._raw is None:
            raise last_error

    def execute(self, sql: str, params=()) -> _Result:
        cursor = self._raw.cursor()
        try:
            cursor.execute(_pg_sql(sql), tuple(params))
            rows = []
            if cursor.description:
                names = [column[0] for column in cursor.description]
                for raw in cursor.fetchall():
                    rows.append({names[i]: raw[i] for i in range(len(names))})
            return _Result(rows, cursor.rowcount)
        finally:
            cursor.close()

    def executemany(self, sql: str, seq) -> _Result:
        cursor = self._raw.cursor()
        try:
            cursor.executemany(_pg_sql(sql), [tuple(row) for row in seq])
            return _Result([], cursor.rowcount)
        finally:
            cursor.close()

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                self.execute(statement)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self._raw.commit()
            else:
                self._raw.rollback()
        finally:
            self._raw.close()
        return False


def db_connect():
    url = database_url()
    if url:
        return PgConnection(url)
    if os.environ.get("VERCEL"):
        raise RuntimeError(
            "No database is connected. Open the project in Vercel, add the Neon "
            "integration (Storage → Marketplace → Neon), then redeploy. "
            "DATABASE_URL is injected automatically."
        )
    return SqliteConnection(_sqlite_path)


# ---------------------------------------------------------------------- model


def get_meta(conn, key: str):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def insert_sale(conn, sale: dict) -> int:
    sql = (
        "INSERT INTO sales(date, product, category, channel, units, unit_price, customer, notes) "
        "VALUES(?, ?, ?, ?, ?, ?, ?, ?)"
    )
    params = tuple(sale[column] for column in SALE_COLUMNS)
    if conn.backend == "postgres":
        row = conn.execute(sql + " RETURNING id", params).fetchone()
        return int(row["id"])
    return int(conn.execute(sql, params).lastrowid)


def insert_many(conn, sales: list[dict]) -> int:
    """Bulk insert; a single round trip per chunk keeps cloud imports fast."""
    if not sales:
        return 0
    values = [tuple(sale[column] for column in SALE_COLUMNS) for sale in sales]
    if conn.backend == "postgres":
        chunk_size = 2000
        for start in range(0, len(values), chunk_size):
            group = values[start:start + chunk_size]
            placeholders = ", ".join(["(?, ?, ?, ?, ?, ?, ?, ?)"] * len(group))
            sql = (
                "INSERT INTO sales(date, product, category, channel, units, unit_price, customer, notes) "
                f"VALUES {placeholders}"
            )
            conn.execute(sql, [value for row in group for value in row])
    else:
        conn.executemany(
            "INSERT INTO sales(date, product, category, channel, units, unit_price, customer, notes) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            values,
        )
    return len(values)


def seed_demo(conn) -> int:
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
        rows.append({
            "date": sold.isoformat(),
            "product": product,
            "category": category,
            "channel": channel,
            "units": units,
            "unit_price": price,
            "customer": customer,
            "notes": "",
        })
    insert_many(conn, rows)
    set_meta(conn, "demo", "1")
    return len(rows)


def init_db() -> None:
    if using_postgres():
        with db_connect() as conn:
            # Serialize first-run setup across concurrent cold starts.
            conn.execute("SELECT pg_advisory_xact_lock(?)", (727727,))
            conn.executescript(PG_SCHEMA)
            if get_meta(conn, "initialized") is None:
                count = conn.execute("SELECT COUNT(*) AS n FROM sales").fetchone()["n"]
                if count == 0:
                    seed_demo(conn)
                set_meta(conn, "initialized", "1")
        return

    with db_connect() as conn:
        conn.executescript(SCHEMA)
        if get_meta(conn, "initialized") is None:
            count = conn.execute("SELECT COUNT(*) AS n FROM sales").fetchone()["n"]
            if count == 0:
                seed_demo(conn)
            set_meta(conn, "initialized", "1")


def ensure_initialized() -> None:
    """Initialise once per process (serverless instances stay warm)."""
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        init_db()
        _initialized = True


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


def fetch_sales(conn, filters: dict, limit: int | None = None) -> list[dict]:
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


def build_summary(conn, filters: dict) -> dict:
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


def meta_payload(conn) -> dict:
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
        "cloud": using_postgres(),
        "db_path": database_label(),
        "updated_at": (updated or "").replace(" ", "T") + "Z" if updated else None,
    }
