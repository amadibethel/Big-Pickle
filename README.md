# Counter — a sales dashboard

A small, fast sales dashboard for your business. Log sales, import a CSV, and see
revenue, units, average sale value, category mix, and your best sellers. Every
number is calculated live from your sales data.

Run it locally with **zero dependencies** and a SQLite file on your computer, or
deploy it to **Vercel** with a hosted Postgres database (Neon).

No accounts, no subscriptions, no build step.

![Counter](https://img.shields.io/badge/python-3.9%2B-3776AB) ![Counter](https://img.shields.io/badge/local_dependencies-0-c8f45c)

## Start it locally

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

## Deploy to Vercel

The cloud build uses the same dashboard and the same API shape, but Vercel
cannot keep a Python process or a SQLite file alive. There it runs as:

- `static/` — the dashboard, served from Vercel's CDN.
- `api/index.py` — one Python serverless function for the whole JSON API.
- **Neon Postgres** — the hosted database (free tier is fine).

### 1. Push the project to GitHub

```bash
cd "/Users/Godfada/Desktop/Big Pickle"
git add .
git commit -m "Add Vercel deployment"
git push
```

### 2. Import it in Vercel

1. Open [vercel.com/new](https://vercel.com/new) and import the repository.
2. Leave the framework preset as **Other**. `vercel.json` already sets the
   output directory to `static`; there is no build command.
3. Click **Deploy**. The first deploy will show a database error until step 3.

### 3. Add the Postgres database

In the Vercel project: **Storage → Create Database → Neon** (Marketplace).
Create a free database and connect it to this project for **Production**,
**Preview**, and **Development**.

The integration injects `DATABASE_URL` automatically. Redeploy (or run
**Redeploy** on the latest deployment). On the first request Counter creates its
tables and loads the 320 sample sales, exactly like the local app.

That's it — open the deployment URL.

### Optional: protect the cloud app

A deployment is reachable by anyone who has the link, and this app has no user
accounts. Two options:

- **Vercel Deployment Protection** (Project → Settings → Deployment Protection)
  — the strongest option; it puts your whole deployment behind Vercel's login.
- **`COUNTER_PASSWORD`** — add an environment variable in Vercel (Settings →
  Environment Variables) to require HTTP Basic auth on all `/api` requests.
  Any username works; use this value as the password when the browser prompts.

### Cloud limitations

- **Database:** data lives in Postgres, not `sales.db`. Use Neon's dashboard for
  backups and branching.
- **Request size:** Vercel accepts up to **4.5 MB** per request. CSV imports are
  sent as JSON, so keep imports well under that (a few thousand rows at a time).
- **Cold starts:** free Neon databases can pause when idle. The first request
  after a pause may take a few seconds.
- **No local file access:** files in `static/` and the function bundle are
  read-only. Uploads and exports are handled in memory.
- **Time limit:** API functions are configured with `maxDuration: 60` seconds.

If you set `DATABASE_URL` locally (or any of `POSTGRES_URL`,
`POSTGRES_URL_NON_POOLING`, `NEON_DATABASE_URL`), `python3 server.py` uses
Postgres too — handy for testing the cloud path. Install the single cloud
dependency first: `python3 -m pip install -r requirements.txt`.

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

**Local:** everything lives in **`sales.db`** next to `server.py`. To back it up,
copy that file somewhere safe. To reset the app, stop it, delete `sales.db`, and
start it again — a fresh database with sample data is created. The database is
only reachable from this computer (`127.0.0.1`). Nothing is sent anywhere. The
API also rejects changes that come from other websites, so a tab you have open
elsewhere can't alter your sales.

**Vercel:** everything lives in the Postgres database connected through the
Neon integration. Back it up or reset it from Neon. The app is public on the
internet, so use Deployment Protection or `COUNTER_PASSWORD` if the numbers are
private.

## Command-line options

```text
python3 server.py [--port 8787] [--host 127.0.0.1] [--db path/to/file.db] [--no-open]
```

- `--port` — use a different port (the next free one is chosen automatically if busy).
- `--host` — bind to another interface (only do this if you understand the exposure).
- `--db` — use a different SQLite database file.
- `--no-open` — don't launch the browser automatically.

## Requirements

- **Local:** Python 3.9 or newer (tested on 3.15) and any modern browser. That's
  it — `server.py` uses only the Python standard library.
- **Vercel:** the `pg8000` driver from `requirements.txt`, installed by Vercel
  automatically. No other cloud dependencies.

## Project layout

```text
server.py              local HTTP server + static files + JSON API
counter_core.py        shared sales model, SQLite/Postgres storage
api/index.py           Vercel serverless WSGI entrypoint
vercel.json            static output + function configuration
requirements.txt       pg8000, used only by the cloud build
static/index.html      app shell
static/styles.css      design system and responsive layout
static/app.js          dashboard, charts, forms, CSV import/export
sales.db               your local data (created on first run)
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

**Vercel says "No database is connected"** — the Neon integration is not linked
to the environment you opened. Connect it to Production/Preview/Development and
redeploy.

**Vercel shows a password prompt** — `COUNTER_PASSWORD` is set; any username plus
that password works.
