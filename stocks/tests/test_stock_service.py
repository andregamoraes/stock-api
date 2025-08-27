import datetime as dt
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase

from stocks.models import Stock
from stocks.services.stock_service import build_payload


class BuildPayloadTests(TestCase):
    @patch("stocks.services.stock_service.get_scrapping_data",
           return_value={"performance": {}, "competitors": []})
    @patch("stocks.services.stock_service.PolygonClient")
    def test_build_payload_ok(self, poly_cls, _scrap):
        # seed DB: already purchased 2.5 units
        Stock.objects.create(company_code="AAPL",
                             company_name="Apple Inc.",
                             amount=Decimal("2.5"))

        # Polygon mocks
        poly = poly_cls.return_value
        poly.last_trading_day.return_value = dt.date(2025, 8, 22)
        poly.get_company_info.return_value = {"name": "Apple Inc."}
        poly.get_daily_data.return_value = {
            "_polygon_status": "OK",
            "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5,
            "date": "2025-08-22", "symbol": "AAPL",
        }

        data, http = build_payload("aapl")
        self.assertEqual(http, 200)
        self.assertEqual(data["company_name"], "Apple Inc.")
        self.assertEqual(data["purchased_amount"], 2.5)
        self.assertEqual(data["stock_values"]["close"], 1.5)
        self.assertEqual(data["stock_values"]["high"], 2.0)
        self.assertEqual(data["stock_values"]["low"], 0.5)
        self.assertEqual(data["stock_values"]["open"], 1.0)
        self.assertEqual(data["company_code"], "AAPL")
        self.assertEqual(data["request_date"], "2025-08-22")
        self.assertEqual(data["purchased_status"], "purchased")

    @patch("stocks.services.stock_service.get_scrapping_data",
           return_value={"performance": {}, "competitors": []})
    @patch("stocks.services.stock_service.PolygonClient")
    def test_invalid_ticker_returns_400(self, poly_cls, _scrap):
        poly = poly_cls.return_value
        poly.last_trading_day.return_value = dt.date(2025, 8, 22)
        poly.get_company_info.return_value = {}  # invalid ticker

        data, http = build_payload("XXXX")

        self.assertEqual(http, 400)
        self.assertEqual(data["status"], "error")
        self.assertIn("invalid or unknown ticker", data["error"])

    @patch("stocks.services.stock_service.get_scrapping_data",
           return_value={"performance": {}, "competitors": []})
    @patch("stocks.services.stock_service.PolygonClient")
    def test_ohlc_not_available_after_retries_returns_503(self, poly_cls, _scrap):
        poly = poly_cls.return_value
        poly.last_trading_day.return_value = dt.date(2025, 8, 24)
        poly.get_company_info.return_value = {"name": "Apple Inc."}
        poly.get_daily_data.return_value = {"_polygon_status": "Invalid Date"}  # always fails

        data, http = build_payload("AAPL")

        self.assertEqual(http, 503)
        self.assertEqual(data["status"], "error")
        self.assertIn("could not retrieve recent OHLC data", data["error"])