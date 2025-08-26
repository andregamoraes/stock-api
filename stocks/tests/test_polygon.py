import datetime as dt
from unittest.mock import patch
from django.test import SimpleTestCase

class LastTradingDayTests(SimpleTestCase):
    def _freeze_et(self, year, month, day, hour, minute=0):
        import stocks.services.polygon_client as pc

        class _FixedDateTime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return dt.datetime(year, month, day, hour, minute, tzinfo=dt.timezone.utc)

        return patch.object(pc.dt, "datetime", _FixedDateTime)

    def test_wednesday_after_close_keeps_wed(self):
        from stocks.services.polygon_client import PolygonClient
        with self._freeze_et(2025, 8, 20, 21):  # 17:00 ET (UTC-4) ⇒ after 16:10 ET
            d = PolygonClient.last_trading_day()
            self.assertEqual(d, dt.date(2025, 8, 20))

    def test_wednesday_before_close_uses_tuesday(self):
        from stocks.services.polygon_client import PolygonClient
        with self._freeze_et(2025, 8, 20, 17):  # 13:00 ET ⇒ before cutoff
            d = PolygonClient.last_trading_day()
            self.assertEqual(d, dt.date(2025, 8, 19))

    def test_sunday_uses_friday(self):
        from stocks.services.polygon_client import PolygonClient
        with self._freeze_et(2025, 8, 17, 15):  # sunday
            d = PolygonClient.last_trading_day()
            self.assertEqual(d, dt.date(2025, 8, 15))  # friday

    def test_saturday_uses_friday(self):
        from stocks.services.polygon_client import PolygonClient
        with self._freeze_et(2025, 8, 16, 15):  # saturday
            d = PolygonClient.last_trading_day()
            self.assertEqual(d, dt.date(2025, 8, 15))  # friday
