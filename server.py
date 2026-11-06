#!/usr/bin/env python3
"""
Counter — a local-first sales dashboard.

    python3 server.py

Then open http://127.0.0.1:8787

By default everything is stored in a SQLite database next to this file, with
no third-party packages, no build step, and no cloud account. If a Postgres
connection string is present in DATABASE_URL (or POSTGRES_URL), the server
uses Postgres instead — that is the same path the Vercel app uses.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import mimetypes
import os
import re
import sys
import threading
import traceback
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import counter_core as core

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
BIND_HOST = "127.0.0.1"
LOOPBACK_NAMES = core.LOOPBACK_NAMES


def api_path(path: str, query: dict) -> str:
    """Accept both /api/meta and /api?route=meta (the Vercel-friendly form)."""
    if path in ("/api", "/api/"):
        route = (query.get("route") or [""])[0].strip()
        if route:
            return "/api/" + route.strip("/")
    return path


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
            raise core.ValidationError("Request body is too large.")
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
            raise core.ValidationError("Request body must be valid JSON.")

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
            query = parse_qs(parsed.query)
            path = api_path(parsed.path, query)

            if path == "/favicon.ico":
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            if path == "/api/meta":
                with core.db_connect() as conn:
                    self.send_json(200, core.meta_payload(conn))
                return

            if path == "/api/summary":
                filters = core.query_filters(query)
                with core.db_connect() as conn:
                    self.send_json(200, core.build_summary(conn, filters))
                return

            if path == "/api/sales":
                filters = core.query_filters(query)
                limit = None
                raw_limit = query.get("limit", [""])[0]
                if raw_limit.isdigit():
                    limit = max(1, min(int(raw_limit), 50_000))
                with core.db_connect() as conn:
                    items = core.fetch_sales(conn, filters, limit=limit)
                    self.send_json(200, {"items": items, "total": len(items)})
                return

            if path == "/api/export.csv":
                filters = core.query_filters(query)
                with core.db_connect() as conn:
                    items = core.fetch_sales(conn, filters)
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

            if path in ("/api", "/api/") or path.startswith("/api/"):
                self.send_error_json(404, "Unknown API endpoint")
                return

            self.serve_static(path)

        except core.ValidationError as exc:
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
            path = api_path(parsed.path, parse_qs(parsed.query))

            if path == "/api/sales":
                payload = self.read_json()
                sale = core.parse_sale(payload)
                with core.db_connect() as conn:
                    sale_id = core.insert_sale(conn, sale)
                    created = dict(conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone())
                created["total"] = round(created["units"] * created["unit_price"], 2)
                self.send_json(201, created)
                return

            if path == "/api/import":
                payload = self.read_json()
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
                self.send_json(200, {"inserted": inserted, "skipped": skipped, "errors": errors})
                return

            if path == "/api/seed":
                with core.db_connect() as conn:
                    count = conn.execute("SELECT COUNT(*) AS n FROM sales").fetchone()["n"]
                    added = core.seed_demo(conn) if count == 0 else 0
                self.send_json(200, {"inserted": added})
                return

            self.send_error_json(404, "Unknown API endpoint")

        except core.ValidationError as exc:
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
            parsed = urlparse(self.path)
            path = api_path(parsed.path, parse_qs(parsed.query))
            match = re.fullmatch(r"/api/sales/(\d+)", path)
            if not match:
                self.send_error_json(404, "Unknown API endpoint")
                return
            sale_id = int(match.group(1))
            payload = self.read_json()
            sale = core.parse_sale(payload)
            with core.db_connect() as conn:
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
        except core.ValidationError as exc:
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
            parsed = urlparse(self.path)
            path = api_path(parsed.path, parse_qs(parsed.query))
            if path == "/api/sales/all":
                with core.db_connect() as conn:
                    deleted = conn.execute("SELECT COUNT(*) AS n FROM sales").fetchone()["n"]
                    conn.execute("DELETE FROM sales")
                    core.set_meta(conn, "demo", "0")
                self.send_json(200, {"deleted": deleted})
                return
            match = re.fullmatch(r"/api/sales/(\d+)", path)
            if not match:
                self.send_error_json(404, "Unknown API endpoint")
                return
            sale_id = int(match.group(1))
            with core.db_connect() as conn:
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
    global BIND_HOST
    parser = argparse.ArgumentParser(description="Counter — local sales dashboard")
    parser.add_argument("--port", type=int, default=8787, help="port to serve on (default: 8787)")
    parser.add_argument("--host", default="127.0.0.1", help="host to bind (default: 127.0.0.1)")
    parser.add_argument("--db", default=core.sqlite_path(), help="path to the SQLite database")
    parser.add_argument("--no-open", action="store_true", help="don't open the browser automatically")
    args = parser.parse_args()

    BIND_HOST = args.host
    core.configure(args.db)

    os.makedirs(STATIC_DIR, exist_ok=True)
    core.init_db()

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
    print(f"  Database    {core.database_label()}")
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
