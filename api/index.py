#!/usr/bin/env python3
"""
Counter — Vercel serverless API.

Vercel serves the files in ``static/`` at the site root and runs this WSGI app
at ``/api``. The browser calls ``/api?route=summary`` so every request reaches
this single function.

The database is hosted Postgres. Connect the Neon integration in Vercel and
``DATABASE_URL`` is injected automatically; the first request creates the
tables and loads the sample sales.
"""

from __future__ import annotations

import base64
import csv
import hmac
import io
import json
import os
import re
import sys
import traceback
from datetime import date
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _path in (ROOT, os.path.dirname(os.path.abspath(__file__))):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import counter_core as core  # noqa: E402

MAX_BODY = 4_500_000
SECURITY_HEADERS = [
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Frame-Options", "DENY"),
]


def _json(start_response, status: int, payload, head: bool = False):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "no-store"),
        *SECURITY_HEADERS,
    ]
    start_response(f"{status} {_reason(status)}", headers)
    return [b""] if head else [body]


def _csv_response(start_response, body: bytes, filename: str):
    headers = [
        ("Content-Type", "text/csv; charset=utf-8"),
        ("Content-Disposition", f'attachment; filename="{filename}"'),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "no-store"),
        *SECURITY_HEADERS,
    ]
    start_response("200 OK", headers)
    return [body]


def _reason(status: int) -> str:
    return {
        200: "OK",
        201: "Created",
        204: "No Content",
        400: "Bad Request",
        403: "Forbidden",
        404: "Not Found",
        500: "Internal Server Error",
        503: "Service Unavailable",
    }.get(status, "OK")


def _route(environ, query: dict) -> str:
    route = (query.get("route") or [""])[0].strip()
    if not route:
        path = environ.get("PATH_INFO") or "/"
        route = path[4:] if path.startswith("/api") else path
    return "/" + route.strip("/")


def _read_body(environ) -> bytes:
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length = 0
    if length <= 0:
        return b""
    if length > MAX_BODY:
        raise core.ValidationError(
            "Request body is too large. Vercel accepts up to 4.5 MB per request."
        )
    return environ["wsgi.input"].read(length)


def _read_json(environ):
    raw = environ.get("counter.body")
    if raw is None:
        raw = _read_body(environ)
        environ["counter.body"] = raw
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise core.ValidationError("Request body must be valid JSON.")


def _same_site(environ) -> bool:
    host = (environ.get("HTTP_HOST") or "").strip().lower()
    source = environ.get("HTTP_ORIGIN") or environ.get("HTTP_REFERER")
    if not source:
        return True
    try:
        parsed = urlparse(source)
    except ValueError:
        return False
    return (parsed.netloc or "").lower() == host


def _authorized(environ) -> bool:
    """Optional password for the cloud API. Set COUNTER_PASSWORD in Vercel."""
    password = os.environ.get("COUNTER_PASSWORD") or ""
    if not password:
        return True
    header = environ.get("HTTP_AUTHORIZATION") or ""
    if not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:]).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    _, _, supplied = decoded.partition(":")
    return hmac.compare_digest(supplied, password)



def _export_csv(filters: dict) -> bytes:
    with core.db_connect() as conn:
        items = core.fetch_sales(conn, filters)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "date", "product", "category", "channel", "units", "unit_price",
        "total", "customer", "notes",
    ])
    for item in items:
        writer.writerow([
            item["date"], item["product"], item["category"], item["channel"],
            item["units"], f'{item["unit_price"]:.2f}', f'{item["total"]:.2f}',
            item["customer"], item["notes"],
        ])
    return buffer.getvalue().encode("utf-8-sig")


def app(environ, start_response):
    method = (environ.get("REQUEST_METHOD") or "GET").upper()
    head = method == "HEAD"
    query = parse_qs(environ.get("QUERY_STRING") or "")
    route = _route(environ, query)

    try:
        if method == "OPTIONS":
            start_response("204 No Content", [("Allow", "GET, POST, PUT, DELETE, HEAD"), ("Content-Length", "0")])
            return [b""]

        if not _authorized(environ):
            body = json.dumps({"error": "Password required."}).encode("utf-8")
            start_response("401 Unauthorized", [
                ("WWW-Authenticate", 'Basic realm="Counter", charset="UTF-8"'),
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(body))),
                *SECURITY_HEADERS,
            ])
            return [b""] if head else [body]

        if method != "GET" and not _same_site(environ):
            return _json(start_response, 403, {"error": "This request did not come from the Counter app."}, head)

        core.ensure_initialized()

        # --------------------------------------------------------------- GET

        if method in ("GET", "HEAD"):
            if route == "/meta":
                with core.db_connect() as conn:
                    return _json(start_response, 200, core.meta_payload(conn), head)

            if route == "/summary":
                filters = core.query_filters(query)
                with core.db_connect() as conn:
                    return _json(start_response, 200, core.build_summary(conn, filters), head)

            if route == "/sales":
                filters = core.query_filters(query)
                limit = None
                raw_limit = query.get("limit", [""])[0]
                if raw_limit.isdigit():
                    limit = max(1, min(int(raw_limit), 50_000))
                with core.db_connect() as conn:
                    items = core.fetch_sales(conn, filters, limit=limit)
                return _json(start_response, 200, {"items": items, "total": len(items)}, head)

            if route == "/export.csv":
                filters = core.query_filters(query)
                body = _export_csv(filters)
                filename = f"counter-sales-{date.today().isoformat()}.csv"
                return _csv_response(start_response, body, filename)

            return _json(start_response, 404, {"error": "Unknown API endpoint"}, head)

        # -------------------------------------------------------------- POST

        if method == "POST":
            if route == "/sales":
                payload = _read_json(environ)
                sale = core.parse_sale(payload)
                with core.db_connect() as conn:
                    sale_id = core.insert_sale(conn, sale)
                    created = dict(conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone())
                created["total"] = round(created["units"] * created["unit_price"], 2)
                return _json(start_response, 201, created)

            if route == "/import":
                payload = _read_json(environ)
                rows = payload.get("rows") if isinstance(payload, dict) else None
                if not isinstance(rows, list):
                    raise core.ValidationError("Expected a 'rows' array.")
                if len(rows) > 20_000:
                    raise core.ValidationError("Import is limited to 20,000 rows at a time.")
                valid, skipped, errors = [], 0, []
                for index, raw in enumerate(rows, start=1):
                    try:
                        valid.append(core.parse_sale(raw))
                    except core.ValidationError as exc:
                        skipped += 1
                        if len(errors) < 8:
                            errors.append({"row": index, "message": "; ".join(exc.errors)})
                with core.db_connect() as conn:
                    inserted = core.insert_many(conn, valid)
                return _json(start_response, 200, {"inserted": inserted, "skipped": skipped, "errors": errors})

            if route == "/seed":
                with core.db_connect() as conn:
                    count = conn.execute("SELECT COUNT(*) AS n FROM sales").fetchone()["n"]
                    added = core.seed_demo(conn) if count == 0 else 0
                return _json(start_response, 200, {"inserted": added})

            return _json(start_response, 404, {"error": "Unknown API endpoint"})

        # --------------------------------------------------------------- PUT

        if method == "PUT":
            match = re.fullmatch(r"/sales/(\d+)", route)
            if not match:
                return _json(start_response, 404, {"error": "Unknown API endpoint"})
            sale_id = int(match.group(1))
            payload = _read_json(environ)
            sale = core.parse_sale(payload)
            with core.db_connect() as conn:
                exists = conn.execute("SELECT id FROM sales WHERE id = ?", (sale_id,)).fetchone()
                if not exists:
                    return _json(start_response, 404, {"error": "Sale not found"})
                conn.execute(
                    "UPDATE sales SET date = ?, product = ?, category = ?, channel = ?, units = ?, "
                    "unit_price = ?, customer = ?, notes = ? WHERE id = ?",
                    (sale["date"], sale["product"], sale["category"], sale["channel"],
                     sale["units"], sale["unit_price"], sale["customer"], sale["notes"], sale_id),
                )
                updated = dict(conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone())
            updated["total"] = round(updated["units"] * updated["unit_price"], 2)
            return _json(start_response, 200, updated)

        # ------------------------------------------------------------ DELETE

        if method == "DELETE":
            if route == "/sales/all":
                with core.db_connect() as conn:
                    deleted = conn.execute("SELECT COUNT(*) AS n FROM sales").fetchone()["n"]
                    conn.execute("DELETE FROM sales")
                    core.set_meta(conn, "demo", "0")
                return _json(start_response, 200, {"deleted": deleted})
            match = re.fullmatch(r"/sales/(\d+)", route)
            if not match:
                return _json(start_response, 404, {"error": "Unknown API endpoint"})
            sale_id = int(match.group(1))
            with core.db_connect() as conn:
                cursor = conn.execute("DELETE FROM sales WHERE id = ?", (sale_id,))
                deleted = cursor.rowcount
            if not deleted:
                return _json(start_response, 404, {"error": "Sale not found"})
            return _json(start_response, 200, {"deleted": 1})

        start_response("405 Method Not Allowed", [("Allow", "GET, POST, PUT, DELETE, HEAD"), ("Content-Length", "0")])
        return [b""]

    except core.ValidationError as exc:
        return _json(start_response, 400, {"error": "Invalid request", "details": exc.errors}, head)
    except RuntimeError as exc:
        # Configuration problems (missing database, missing driver) have
        # actionable messages written for the person deploying the app.
        traceback.print_exc()
        return _json(start_response, 500, {"error": str(exc)}, head)
    except Exception:
        traceback.print_exc()
        return _json(start_response, 500, {"error": "Something went wrong on the server."}, head)


# Vercel detects either ``app`` or ``application`` as the WSGI entrypoint.
application = app
