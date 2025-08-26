import math
from unittest.mock import patch, Mock
from django.test import SimpleTestCase

from stocks.services import marketwatch_scraper as mw


class ScraperHelperTests(SimpleTestCase):
    def test_pct_to_float_variants(self):
        cases = {
            "+3.25%": 3.25,
            "0 %": 0.0,
            "n/a": None,
            "": None,
            None: None,
        }
        for txt, expected in cases.items():
            with self.subTest(txt=txt):
                self.assertEqual(mw._pct_to_float(txt), expected)

    def test_parse_market_cap(self):
        cases = [
            ("$3.75T", ("$", 3.75e12)),
            ("US$ 2.37T", ("US$", 2.37e12)),
            ("€512.3B", ("€", 512.3e9)),
            ("₩465.45T", ("₩", 465.45e12)),
            ("N/A", (None, None)),
            ("", (None, None)),
            ("—", (None, None)),
        ]
        for txt, (cur, val) in cases:
            with self.subTest(txt=txt):
                c, v = mw._parse_market_cap(txt)
                self.assertEqual(c, cur)
                if val is None:
                    self.assertIsNone(v)
                else:
                    self.assertTrue(math.isclose(v, val, rel_tol=1e-9))


class GetScrappingDataTests(SimpleTestCase):
    @patch("stocks.services.marketwatch_scraper.requests.get")
    def test_antibot_detected_returns_empty_defaults(self, mock_get):
        mock_get.return_value = Mock(text="<html>captcha-delivery.com</html>")

        with patch.object(mw, "COOKIE", "X=abc"):
            data = mw.get_scrapping_data("AAPL")

        self.assertTrue(all(v is None for v in data["performance"].values()))
        self.assertEqual(data["competitors"], [])

    @patch("stocks.services.marketwatch_scraper.requests.get")
    def test_missing_sections_does_not_crash(self, mock_get):
        mock_get.return_value = Mock(text="<html><body><p>No tables here</p></body></html>")

        with patch.object(mw, "COOKIE", "X=abc"):
            data = mw.get_scrapping_data("AAPL")

        self.assertTrue(all(v is None for v in data["performance"].values()))
        self.assertEqual(data["competitors"], [])
