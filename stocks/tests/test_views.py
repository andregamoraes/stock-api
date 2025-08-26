# stocks/tests/test_views.py
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from stocks.models import Stock

BASE = "/api/stock"

class StockViewGetTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("stocks.views.get_payload_cached",
           return_value=({"status": "ok", "company_code": "AAPL"}, 200))
    def test_get_ok_propagates_payload_and_status(self, get_cached):
        resp = self.client.get(f"{BASE}/AAPL/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")
        get_cached.assert_called_once_with("AAPL")

    @patch("stocks.views.get_payload_cached",
           return_value=({"status": "error", "error": "invalid"}, 400))
    def test_get_error_propagates_status_code(self, get_cached):
        resp = self.client.get(f"{BASE}/XXXX/")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["status"], "error")
        get_cached.assert_called_once_with("XXXX")


class StockViewPostTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_post_missing_amount_400(self):
        resp = self.client.post(f"{BASE}/AAPL/", data={}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("amount is required", resp.json()["error"])

    def test_post_amount_not_number_400(self):
        resp = self.client.post(f"{BASE}/AAPL/", data={"amount": "abc"}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("amount must be a number", resp.json()["error"])

    def test_post_amount_le_zero_400(self):
        for v in ["0", 0, "-1", -0.1]:
            with self.subTest(v=v):
                resp = self.client.post(f"{BASE}/AAPL/", data={"amount": v}, format="json")
                self.assertEqual(resp.status_code, 400)
                self.assertIn("> 0", resp.json()["error"])

    @patch("stocks.views.bust_cache")
    @patch("stocks.views.PolygonClient")
    def test_post_creates_row_and_busts_cache(self, Poly, bust_cache):
        # no company_name in DB -> call Polygon
        poly = Poly.return_value
        poly.get_company_info.return_value = {"name": "Apple Inc."}

        resp = self.client.post(f"{BASE}/AAPL/", data={"amount": "2.5"}, format="json")
        self.assertEqual(resp.status_code, 201)

        # check data
        self.assertEqual(Stock.objects.count(), 1)
        s = Stock.objects.first()
        self.assertEqual(s.company_code, "AAPL")
        self.assertEqual(s.company_name, "Apple Inc.")
        self.assertEqual(s.amount, Decimal("2.5"))

        # deleted cache
        bust_cache.assert_called_once_with("AAPL")

    @patch("stocks.views.PolygonClient")
    def test_post_uses_company_name_from_db_without_polygon_call(self, Poly):
        # company_name in db
        Stock.objects.create(company_code="AAPL", company_name="Apple Inc.", amount=Decimal("1"))

        resp = self.client.post(f"{BASE}/AAPL/", data={"amount": "1"}, format="json")
        self.assertEqual(resp.status_code, 201)

        self.assertFalse(Poly.called)

    @patch("stocks.views.PolygonClient")
    def test_post_invalid_ticker_400(self, Poly):
        poly = Poly.return_value
        poly.get_company_info.return_value = {}  # no name -> invalid

        resp = self.client.post(f"{BASE}/XXXX/", data={"amount": "1"}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("invalid or unknown ticker", resp.json()["error"])

    @patch("stocks.views.PolygonClient")
    def test_post_upstream_unavailable_503(self, Poly):
        poly = Poly.return_value
        poly.get_company_info.side_effect = Exception("down")

        resp = self.client.post(f"{BASE}/AAPL/", data={"amount": "1"}, format="json")
        self.assertEqual(resp.status_code, 503)
        self.assertIn("upstream provider unavailable", resp.json()["error"])
