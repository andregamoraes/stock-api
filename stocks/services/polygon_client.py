import os, logging, requests
import datetime as dt
from zoneinfo import ZoneInfo
from typing import Optional, Dict

log = logging.getLogger(__name__)

class PolygonClient:
    """
    Thin HTTP client for Polygon.io used by our services layer.
    """
    BASE_URL = os.getenv("POLYGON_BASE_URL")

    def __init__(self, api_key: Optional[str] = None, timeout: int = 10):
        self.api_key = api_key or os.getenv("POLYGON_API_KEY", "")
        self.timeout = timeout

    @staticmethod
    def last_trading_day() -> dt.date:
        """
        Choose a reference trading date in US/Eastern.
        - If Sat/Sun -> jump back to Friday
        - If it's a weekday but BEFORE the close (16:10 ET) -> use previous weekday
        (Holidays/early-closes aren't handled here.)
        """
        now_utc = dt.datetime.now(dt.timezone.utc)
        now_et = now_utc.astimezone(ZoneInfo("America/New_York"))
        d = now_et.date()

        # If weekend, go back to Friday
        while d.weekday() >= 5:  # 5=Sat, 6=Sun
            d -= dt.timedelta(days=1)

        cutoff = dt.time(16, 10)  # small buffer after the 16:00 ET close
        # If still the same weekday as 'today' but before cutoff -> go to previous weekday
        if d == now_et.date() and now_et.time() < cutoff:
            d -= dt.timedelta(days=1)
            while d.weekday() >= 5:
                d -= dt.timedelta(days=1)
        return d

    def get_company_info(self, symbol: str) -> Optional[Dict[str, str]]:
        """
        Resolve the company name for a given ticker using /v3/reference/tickers.
        Returns:
          - {"name": "..."} on success,
          - {} if ticker is invalid,
          - None if upstream is unavailable (network/HTTP failure).
        """

        url = self.BASE_URL + "/v3/reference/tickers"
        params = {
            "ticker": symbol.upper(),
            "apiKey": self.api_key
        }

        try:
            r = requests.get(url, params=params, timeout=self.timeout)
            r.raise_for_status()
            j = r.json()

            results = j.get("results")
            if results and len(results) > 0:
                company = results[0]
                name = company.get("name")
                return {"name": name} if name else {}
            else:
                return {}
        except Exception as e:
            log.exception("Polygon company info failed for %s: %s", symbol, e)
            return None

    def get_daily_data(self, symbol: str, date: dt.date) -> Dict:
        """
        Fetch daily OHLC using /v1/open-close/{symbol}/{date}.
        Returns a dict with '_polygon_status':
          - "OK" on success
          - "Invalid Date" if Polygon returns a non-OK status payload
          - "ERROR" if the HTTP call fails (includes '_polygon_msg')
        """

        url = self.BASE_URL + f"/v1/open-close/{symbol.upper()}/{date.strftime('%Y-%m-%d')}"
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}

        try:
            r = requests.get(url, headers=headers, timeout=self.timeout)
            r.raise_for_status()
            j = r.json()

            if j.get("status") and j.get("status") != "OK":
                return {"_polygon_status": "Invalid Date"}

            return {
                "_polygon_status": "OK",
                "open":  float(j.get("open"))  if j.get("open")  is not None else None,
                "high":  float(j.get("high"))  if j.get("high")  is not None else None,
                "low":   float(j.get("low"))   if j.get("low")   is not None else None,
                "close": float(j.get("close")) if j.get("close") is not None else None,
                "date":  j.get("from"),
                "symbol": j.get("symbol"),
            }
        except Exception as e:
            log.warning("Polygon failed for %s on %s: %s", symbol, date, e)
            return {
                "_polygon_status": "ERROR",
                "_polygon_msg": str(e),
            }

