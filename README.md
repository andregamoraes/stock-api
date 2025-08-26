# Stock API — Django REST

Small service that aggregates Polygon daily OHLC data with MarketWatch scraping (performance + competitors), enriched with your own purchased amount stored in Postgres. 
Production-style error handling, caching, and logging included.

## Stack

- Python 3.11, Django 5, Django REST Framework
- Postgres 15 (Docker)
- requests, beautifulsoup4, lxml
- Docker / docker-compose
- Unit tests: unittest + Django TestCase + unittest.mock.patch

## Endpoints

### GET /api/stock/{stock_symbol}/
Returns the consolidated payload.

200 OK (example):
{
  "status": "ok",
  "purchased_amount": 2.5,
  "purchased_status": "purchased",
  "request_date": "2025-08-22",
  "company_code": "AAPL",
  "company_name": "Apple Inc.",
  "stock_values": {"open":1.0,"high":2.0,"low":0.5,"close":1.5},
  "performance_data": {
    "five_days": 1.23,
    "one_month": 3.45,
    "three_months": 6.78,
    "year_to_date": 9.01,
    "one_year": 12.34
  },
  "competitors": [
    {"name":"Microsoft Corp.","market_cap":{"currency":"$","value":3150000000000.0}}
  ]
}

Errors:
- 400 — {"status":"error","error":"invalid or unknown ticker"}
- 503 — {"status":"error","error":"ticker validation service temporarily unavailable"}
- 503 — {"status":"error","error":"could not retrieve recent OHLC data"}

### POST /api/stock/{stock_symbol}/
Body: {"amount": {number}} — adds a new purchase row. Validates ticker via Polygon.

201 Created: "2.5 units of stock AAPL were added to your stock record"
400: missing/invalid amount or unknown ticker
503: upstream validation down

Examples:
```bash
curl -s http://localhost:8000/api/stock/AAPL/
````

```bash
curl -s -X POST http://localhost:8000/api/stock/AAPL/ \
  -H "Content-Type: application/json" \
  -d '{"amount": 2.5}'
```


## Environment setup

1) Copy env file and set your POLYGON_API_KEY

```bash
cp .env.example .env
```

2) `.app.env` (MarketWatch cookie)

A `.app.env` file is **already committed** to the repo with a working `MARKETWATCH_COOKIE` I’m currently using.
If/when it stops working, simply replace the cookie value in this file locally and commit an update if you’d like
others to benefit.

The project loads both files in settings.py:
- .env for normal app/compose config,
- .app.env for scraper-only secrets (cookie).

3) Run with Docker
```bash
docker compose up --build
```

4) (Optional) Create Django superuser - (used for /admin if you want to browse DB)
```bash
docker compose exec web python manage.py createsuperuser
```

## Caching

- Per-ticker cache key: stock:{stock_symbol}
- TTL controlled by STOCK_CACHE_SECONDS (default 300s)
- Cache is busted on successful POST to ensure the next GET is fresh.

## Logging

- Logs to console with levels from LOG_LEVEL / DJANGO_LOG_LEVEL.
- Services log meaningful events (validation failures, upstream issues, scraping blocks).
- You can add a rotating file handler later if needed; console is fine for this assignment.

## Scraper notes (MarketWatch)

- Stable headers are set in code; the cookie is read from `.app.env` via MARKETWATCH_COOKIE.
- If the page returns captcha/bot HTML, we gracefully degrade: `performance` and `competitors` are empty; the API still returns `status: ok` (optional data shouldn’t break consumers).

## Polygon notes

- last_trading_day() is US/Eastern aware:
  - If weekday before 16:10 ET ⇒ use the previous weekday.
  - If weekend ⇒ walk back to Friday.
- get_daily_data() marks responses with _polygon_status:
  - "OK" on success.
  - "Invalid Date" when the API responds but that date isn’t available.
  - "ERROR" on network/HTTP errors (with _polygon_msg).
- The service retries up to 5 prior weekdays to skip holidays/early-closes; if still no data ⇒ returns 503.

## Running tests

If the app is **not** running:

```bash
docker-compose run --rm web python manage.py test -v 2
```

If the app is running:

```bash
docker-compose exec web python manage.py test -v 2
```

What’s covered:
- build_payload() happy path, invalid ticker (400), OHLC retry failure (503).
- last_trading_day() behavior around cutoff and weekends.
- View tests for GET/POST (validation paths).
- Scraper parser unit tests (_pct_to_float, _parse_market_cap) with pure strings (no network).

## Security

- Do not commit real secrets. `.env.example` shows keys; developers copy to `.env`.
- `.app.env` contains machine-specific cookie

