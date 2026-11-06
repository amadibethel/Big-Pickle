# Counter — a local sales dashboard

A small, fast sales dashboard for your business. Log sales, import a CSV, and see
revenue, units, average sale value, category mix, and your best sellers. Every
number is calculated live from a SQLite database on your own computer.

No accounts, no subscriptions, no third-party packages.

![Counter](https://img.shields.io/badge/python-3.9%2B-3776AB) ![Counter](https://img.shields.io/badge/dependencies-0-c8f45c)

## Start it

**Option 1 — double-click**

Double-click `Start Counter.command`. A terminal opens, the app starts, and your
browser opens automatically at `http://127.0.0.1:8787`.

> If macOS asks for permission the first time, right-click the file → **Open**.

**Option 2 — terminal**

```bash
cd "/Users/Godfada/Desktop/Big Pickle"
python3 server.py
```

Stop the app with `Ctrl+C`. Your data stays in `sales.db`.

## What's inside

- **Overview** — revenue, sales, units, and average sale value with period-over-period
  comparisons; interactive revenue trend; category donut; top products; recent sales.
- **Transactions** — searchable, filterable, paginated list. Edit or delete any sale.
- **New sale** — add a transaction manually. Revenue is always `units × unit price`.
- **CSV import** — drag and drop an export from a spreadsheet, shop, or POS. Preview
  rows before importing and get a report of anything skipped.
- **CSV export** — download the current filtered view at any time.
- **Filters** — date presets, custom date range, channel, category, and display currency.
- **Sample data** — 320 realistic sales are loaded on first launch so the dashboard
  isn't empty. Clear them whenever you're ready (or from the banner).

## CSV format

The importer is forgiving about column order and header names. It looks for:

| Column       | Required | Aliases                                        | Default   |
| ------------ | :------: | ---------------------------------------------- | --------- |
| `date`       |    yes   | sale date, sold at, transaction date           | —         |
| `product`    |    yes   | item, product name, description                | —         |
| `units`      |    no    | quantity, qty, count                           | `1`       |
| `unit_price` |    no    | price, sale price, amount                      | `0`       |
| `category`   |    no    | type                                           | `General` |
| `channel`    |    no    | source, sales channel, platform                | `Online`  |
| `customer`   |    no    | customer name, client, buyer                   | blank     |
| `notes`      |    no    | note, memo, comment                            | blank     |

Dates should be `YYYY-MM-DD` (other common formats are understood too). Commas,
semicolons, and tabs are detected automatically.

A ready-to-fill template is available in **Import & data → CSV template**.

```csv
date,product,category,channel,units,unit_price,customer,notes
2026-11-06,Aurora Wireless Earbuds,Electronics,Online,1,89.00,Maya Chen,
2026-11-06,Terra Ceramic Mug Set,Home,In-store,2,28.00,,Gift wrap
2026-11-06,Merino Crew Socks,Apparel,Wholesale,12,18.00,Northside Studio,
```

## Your data

Everything lives in **`sales.db`** next to `server.py`. To back it up, copy that
file somewhere safe. To reset the app, stop it, delete `sales.db`, and start it
again — a fresh database with sample data is created.

The database is only reachable from this computer (`127.0.0.1`). Nothing is sent
anywhere. The API also rejects changes that come from other websites, so a tab
you have open elsewhere can't alter your sales.

## Command-line options

```text
python3 server.py [--port 8787] [--host 127.0.0.1] [--db path/to/file.db] [--no-open]
```

- `--port` — use a different port (the next free one is chosen automatically if busy).
- `--host` — bind to another interface (only do this if you understand the exposure).
- `--db` — use a different database file.
- `--no-open` — don't launch the browser automatically.

## Requirements

- Python 3.9 or newer (macOS ships with Python; this project was tested on 3.15).
- Any modern browser.
- That's it. `server.py` uses only the Python standard library.

## Project layout

```text
server.py              HTTP server + JSON API + SQLite persistence
static/index.html      app shell
static/styles.css      design system and responsive layout
static/app.js          dashboard, charts, forms, CSV import/export
sales.db               your data (created on first run)
Start Counter.command  double-click launcher for macOS
```

## Troubleshooting

**"Port already in use"** — Counter automatically tries the next port; check the
terminal output for the actual URL.

**Browser doesn't open** — visit `http://127.0.0.1:8787` manually.

**I deleted the sample data and want it back** — use **Import & data → Load sample
data**. This only works when the database is empty, so clear your sales first.

**The page looks stale** — reload the browser. The API is `no-store`; assets are
`no-cache`, so a normal reload is enough.
