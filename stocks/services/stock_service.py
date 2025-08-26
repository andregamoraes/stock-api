import os
import logging
import datetime as dt
from decimal import Decimal
from typing import Dict, Any, Optional, Tuple

from django.core.cache import cache
from django.db.models import Sum

from ..models import Stock
from .polygon_client import PolygonClient
from .marketwatch_scraper import get_scrapping_data

log = logging.getLogger(__name__)

TTL = int(os.getenv("STOCK_CACHE_SECONDS", "300"))
_CACHE_PREFIX = "stock:"


def _cache_key(symbol: str) -> str:
    return f"{_CACHE_PREFIX}{symbol.upper()}"


def _latest_company_name(symbol: str) -> Optional[str]:
    """
    Return the most recent non-empty company_name stored in DB for this ticker.
    """
    return (
        Stock.objects
        .filter(company_code=symbol.upper())
        .exclude(company_name__isnull=True)
        .exclude(company_name__exact="")
        .values_list("company_name", flat=True)
        .first()
    )


def build_payload(symbol: str) -> Tuple[Dict[str, Any], int]:
    """
    Build the consolidated payload:
      - purchased position from DB
      - last trading day OHLC from Polygon
      - performance + competitors from MarketWatch

    On invalid ticker, return {"status":"error", "error": "...", "http_status": 400}.
    Upstream hiccups should degrade to None fields instead of raising.
    """
    symbol = symbol.upper()
    poly = PolygonClient()

    # Sum purchased amount
    total: Decimal = (
        Stock.objects.filter(company_code=symbol)
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )
    purchased_status = "purchased" if total > 0 else "none"

    # Company name: DB → Polygon
    company_name = _latest_company_name(symbol)
    if not company_name:
        info = poly.get_company_info(symbol)
        if info is None:
            log.warning("Polygon company lookup unavailable for %s; returning 503.", symbol)
            return {"status": "error",
                    "error": "ticker validation service temporarily unavailable"}, 503

        company_name = info.get("name")
        if not company_name:
            log.info("Ticker %s not found/invalid on Polygon; returning 400.", symbol)
            return {"status": "error",
                    "error": "invalid or unknown ticker"}, 400

    # Last trading day
    trade_date = poly.last_trading_day()

    # Get recent OHLC (try up to 5 calendar days back to skip holidays)
    d = trade_date
    ohlc = {}
    for _ in range(5):
        ohlc = poly.get_daily_data(symbol, d)
        if ohlc.get("_polygon_status") == "OK":
            break
        d -= dt.timedelta(days=1)
        while d.weekday() >= 5:
            d -= dt.timedelta(days=1)
    if ohlc.get("_polygon_status") != "OK":
        log.warning(
            "could not retrieve recent OHLC data: %s (last status=%s)",
            trade_date, ohlc.get("_polygon_status")
        )
        return {
            "status": "error",
            "error": "could not retrieve recent OHLC data",
        }, 503

    # MarketWatch scrapping (non-critical; degrade to empty data on failure)
    scrap = get_scrapping_data(symbol)
    performance = scrap.get("performance", {}) or {}
    competitors = scrap.get("competitors", []) or []

    return {
        "status": "ok",
        "purchased_amount": float(total),
        "purchased_status": purchased_status,
        "request_date": (ohlc.get("date") or trade_date.isoformat()),
        "company_code": symbol,
        "company_name": company_name,
        "stock_values": {
            "open":  ohlc.get("open"),
            "high":  ohlc.get("high"),
            "low":   ohlc.get("low"),
            "close": ohlc.get("close"),
        },
        "performance_data": {
            "five_days":     performance.get("five_days"),
            "one_month":     performance.get("one_month"),
            "three_months":  performance.get("three_months"),
            "year_to_date":  performance.get("year_to_date"),
            "one_year":      performance.get("one_year"),
        },
        "competitors": competitors,
    }, 200


def get_payload_cached(symbol: str) -> Tuple[Dict[str, Any], int]:
    """
    Read from cache; on miss, compute and (only) cache successful results.
    Errors are returned as-is but are not cached.
    """
    key = _cache_key(symbol)
    data = cache.get(key)
    if data is not None:
        return data, 200

    data, http_status = build_payload(symbol)
    if http_status == 200:
        cache.set(key, data, TTL)
    return data, http_status



def bust_cache(symbol: str) -> None:
    """
    Remove the cached payload for this ticker.
    """
    cache.delete(_cache_key(symbol))
