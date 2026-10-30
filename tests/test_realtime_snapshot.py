#!/usr/bin/env python3
"""Tests for real-time snapshot collection (fetch_sina_spot + collect_realtime_snapshot).

Covers:
- Normal Sina API response parsing
- API failure (network error, timeout) → returns None
- Invalid/empty response → returns None
- Snapshot record has correct fields
- source_time vs collected_at distinction (never confuse the two)
- Night session (21:00+) trading_date inference → next calendar day
- Day session trading_date inference → same calendar day
- last_close=0 → stored as last_close_raw=0, last_close=None
- Snapshot appended to realtime_snapshots.jsonl
- is_after_market_close() returns boolean for various weekdays/times

All tests use temp directories and mocks; no real network calls.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from zoneinfo import ZoneInfo

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import fetch_pvc as m  # noqa: E402

TZ = ZoneInfo("Asia/Shanghai")


def sina_text(date_str="2026-10-27", time_str="230000"):
    """Construct fake Sina API response matching the real 44-field format."""
    fields = [
        "PVC连续",       # 0: name
        time_str,         # 1: time (HHMMSS)
        "5150.000",       # 2: open
        "5217.000",       # 3: high
        "5125.000",       # 4: low
        "0.000",          # 5: last_close (0 = unavailable)
        "5175.000",       # 6: bid
        "5176.000",       # 7: ask
        "5174.000",       # 8: current_price
        "5174.500",       # 9: avg_price
        "5099.000",       # 10: last_settle_price
        "100",            # 11: buy_vol
        "200",            # 12: sell_vol
        "1032514.000",    # 13: open_interest
        "830210",         # 14: volume
        "连",             # 15: contract_code
        "PVC",            # 16: exchange
        date_str,         # 17: date (YYYY-MM-DD)
    ] + ["0"] * 25  # pad to 44 total fields

    fields_str = ",".join(fields)
    return f'var hq_str_nf_V0="{fields_str}";'


def make_mock_response(text):
    resp = Mock()
    resp.text = text
    resp.raise_for_status = Mock()
    return resp


class FetchSinaSpotTests(unittest.TestCase):
    """Tests for fetch_sina_spot()."""

    @patch("fetch_pvc.requests")
    def test_normal_response_returns_all_fields(self, mock_requests):
        """Full Sina response parsed into dict with all expected keys."""
        mock_requests.get.return_value = make_mock_response(sina_text())

        spot = m.fetch_sina_spot(symbol="V0")

        self.assertIsNotNone(spot)
        self.assertEqual(spot["name"], "PVC连续")
        self.assertEqual(spot["time"], "230000")
        self.assertEqual(spot["open"], "5150.000")
        self.assertEqual(spot["high"], "5217.000")
        self.assertEqual(spot["low"], "5125.000")
        self.assertEqual(spot["current_price"], "5174.000")
        self.assertEqual(spot["bid_price"], "5175.000")
        self.assertEqual(spot["ask_price"], "5176.000")
        self.assertEqual(spot["last_settle_price"], "5099.000")
        self.assertEqual(spot["open_interest"], "1032514.000")
        self.assertEqual(spot["volume"], "830210")
        self.assertEqual(spot["date"], "2026-10-27")

    @patch("fetch_pvc.requests")
    def test_network_error_returns_none(self, mock_requests):
        """Network error → returns None, no exception."""
        mock_requests.get.side_effect = Exception("Connection error")

        spot = m.fetch_sina_spot(symbol="V0")

        self.assertIsNone(spot)

    @patch("fetch_pvc.requests")
    def test_invalid_response_returns_none(self, mock_requests):
        """Non-matching response text → returns None."""
        mock_requests.get.return_value = make_mock_response("no data here")

        spot = m.fetch_sina_spot(symbol="V0")

        self.assertIsNone(spot)

    @patch("fetch_pvc.requests")
    def test_short_fields_returns_none(self, mock_requests):
        """Response with too few fields (< 18) → returns None."""
        mock_requests.get.return_value = make_mock_response(
            'var hq_str_nf_V0="a,b,c";'
        )

        spot = m.fetch_sina_spot(symbol="V0")

        self.assertIsNone(spot)


class CollectRealtimeSnapshotTests(unittest.TestCase):
    """Tests for collect_realtime_snapshot()."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._orig = {
            "OUT": m.OUT,
            "SNAPSHOTS_V0": m.get_snapshot_file("V0"),
        }
        m.OUT = self.dir

    def tearDown(self):
        for attr, val in self._orig.items():
            if attr == "OUT":
                setattr(m, attr, val)
        self.tmp.cleanup()

    @patch("fetch_pvc.requests")
    def test_snapshot_has_correct_fields(self, mock_requests):
        """Snapshot record contains all expected fields with correct types."""
        mock_requests.get.return_value = make_mock_response(sina_text())

        record = m.collect_realtime_snapshot()

        self.assertIsNotNone(record)
        self.assertEqual(record["symbol"], "V0")
        self.assertEqual(record["name"], "PVC连续")
        self.assertEqual(record["source"], "Sina HTTP API")
        self.assertEqual(record["source_date"], "2026-10-27")
        self.assertEqual(record["source_time"], "230000")
        self.assertEqual(record["bar_datetime"], "2026-10-27 23:00:00")
        self.assertEqual(record["data_type"], "realtime_snapshot")
        self.assertEqual(record["current_price"], 5174.0)
        self.assertEqual(record["bid_price"], 5175.0)
        self.assertEqual(record["ask_price"], 5176.0)
        self.assertEqual(record["open"], 5150.0)
        self.assertEqual(record["high"], 5217.0)
        self.assertEqual(record["low"], 5125.0)
        self.assertEqual(record["open_interest"], 1032514.0)
        self.assertEqual(record["volume"], 830210)
        self.assertEqual(record["last_settle_price"], 5099.0)
        self.assertEqual(record["last_close"], None)  # 0 → None
        self.assertEqual(record["last_close_raw"], 0.0)
        self.assertEqual(record["is_daily_bar_final"], False)

    @patch("fetch_pvc.requests")
    def test_source_time_distinct_from_collected_at(self, mock_requests):
        """source_time (HHMMSS) must not be confused with collected_at (ISO)."""
        mock_requests.get.return_value = make_mock_response(sina_text())

        record = m.collect_realtime_snapshot()

        self.assertEqual(record["source_time"], "230000")
        self.assertIn("collected_at", record)
        self.assertNotEqual(record["source_time"], record["collected_at"])
        # collected_at should be ISO format with timezone
        parsed = datetime.fromisoformat(record["collected_at"])
        self.assertIsNotNone(parsed.tzinfo)

    @patch("fetch_pvc.requests")
    def test_snapshot_appended_to_file(self, mock_requests):
        """Snapshot is appended to realtime_snapshots.jsonl."""
        mock_requests.get.return_value = make_mock_response(sina_text())

        m.collect_realtime_snapshot()

        self.assertTrue(m.get_snapshot_file("V0").exists())
        with open(m.get_snapshot_file("V0"), encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["symbol"], "V0")
        self.assertEqual(lines[0]["source_time"], "230000")

    @patch("fetch_pvc.requests")
    def test_night_session_trading_date_inferred(self, mock_requests):
        """Night session (21:00+) → trading_date is next calendar day."""
        mock_requests.get.return_value = make_mock_response(
            sina_text(date_str="2026-10-27", time_str="230000")
        )

        record = m.collect_realtime_snapshot()

        self.assertEqual(record["trading_date"], "2026-10-28")
        self.assertEqual(
            record["trading_date_method"],
            "inferred_next_calendar_day_for_night_session",
        )

    @patch("fetch_pvc.requests")
    def test_day_session_trading_date_inferred(self, mock_requests):
        """Day session (before 21:00) → trading_date matches source date."""
        mock_requests.get.return_value = make_mock_response(
            sina_text(date_str="2026-10-28", time_str="103000")
        )

        record = m.collect_realtime_snapshot()

        self.assertEqual(record["trading_date"], "2026-10-28")
        self.assertEqual(record["trading_date_method"], "calendar_day")

    @patch("fetch_pvc.requests")
    def test_invalid_time_format_rejected(self, mock_requests):
        """Invalid source_time format → rejected, no snapshot written."""
        mock_requests.get.return_value = make_mock_response(
            sina_text(date_str="2026-10-28", time_str="invalid")
        )

        result = m.collect_realtime_snapshot()

        self.assertIsNone(result)
        self.assertFalse(m.get_snapshot_file("V0").exists())

    @patch("fetch_pvc.requests")
    def test_invalid_date_rejected(self, mock_requests):
        """Invalid source_date (bad calendar date) → rejected, no snapshot written."""
        mock_requests.get.return_value = make_mock_response(
            sina_text(date_str="2026-13-01", time_str="143000")
        )

        result = m.collect_realtime_snapshot()

        self.assertIsNone(result)
        self.assertFalse(m.get_snapshot_file("V0").exists())

    @patch("fetch_pvc.requests")
    def test_missing_source_date_rejected(self, mock_requests):
        """Missing/empty source_date → rejected even though collected_at exists."""
        fields = [
            "PVC连续",
            "143000",
        ] + [""] * 16  # date field empty
        fields_str = ",".join(fields)
        mock_requests.get.return_value = make_mock_response(
            f'var hq_str_nf_V0="{fields_str}";'
        )

        result = m.collect_realtime_snapshot()

        self.assertIsNone(result)
        self.assertFalse(m.get_snapshot_file("V0").exists())

    @patch("fetch_pvc.requests")
    def test_bar_datetime_from_source_date_and_time(self, mock_requests):
        """bar_datetime must be built from real source date + source time, never collected_at."""
        mock_requests.get.return_value = make_mock_response(
            sina_text(date_str="2026-10-27", time_str="230000")
        )

        record = m.collect_realtime_snapshot()

        self.assertIsNotNone(record)
        self.assertEqual(record["bar_datetime"], "2026-10-27 23:00:00")
        self.assertEqual(record["source_date"], "2026-10-27")
        self.assertEqual(record["source_time"], "230000")
        # collected_at is a distinct ISO timestamp, not confused with bar time
        self.assertNotEqual(record["collected_at"], record["bar_datetime"])

    @patch("fetch_pvc.requests")
    def test_api_failure_returns_none(self, mock_requests):
        """Network error → returns None, no file written."""
        mock_requests.get.side_effect = Exception("Connection refused")

        result = m.collect_realtime_snapshot()

        self.assertIsNone(result)
        self.assertFalse(m.get_snapshot_file("V0").exists())

    @patch("fetch_pvc.requests")
    def test_empty_response_returns_none(self, mock_requests):
        """Empty/invalid Sina response → returns None, no file written."""
        mock_requests.get.return_value = make_mock_response("no match")

        result = m.collect_realtime_snapshot()

        self.assertIsNone(result)
        self.assertFalse(m.get_snapshot_file("V0").exists())

    @patch("fetch_pvc.requests")
    def test_volume_preserved_from_source(self, mock_requests):
        """Volume and open_interest are exact source values, not fabricated."""
        mock_requests.get.return_value = make_mock_response(
            sina_text(date_str="2026-10-28", time_str="143000")
        )

        record = m.collect_realtime_snapshot()

        self.assertEqual(record["volume"], 830210)
        self.assertEqual(record["open_interest"], 1032514.0)

    @patch("fetch_pvc.requests")
    def test_multiple_snapshots_appended(self, mock_requests):
        """Multiple collect calls with different source times append multiple lines."""
        mock_requests.get.return_value = make_mock_response(
            sina_text(date_str="2026-10-28", time_str="143000")
        )
        m.collect_realtime_snapshot()

        # Second call with different source time should append
        mock_requests.get.return_value = make_mock_response(
            sina_text(date_str="2026-10-28", time_str="143100")
        )
        m.collect_realtime_snapshot()

        with open(m.get_snapshot_file("V0"), encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        self.assertEqual(len(lines), 2)


class IsAfterMarketCloseTests(unittest.TestCase):
    """Tests for is_after_market_close()."""

    def test_returns_boolean(self):
        """is_after_market_close() returns a bool."""
        self.assertIsInstance(m.is_after_market_close(), bool)

    @patch("fetch_pvc.datetime")
    def test_friday_after_close(self, mock_dt):
        """Friday 15:00+ → True (day session closed, complete daily bar available)."""
        tz = ZoneInfo("Asia/Shanghai")
        friday_3pm = datetime(2026, 10, 30, 15, 0, 0, tzinfo=tz)  # Friday
        mock_dt.now.return_value = friday_3pm
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        self.assertTrue(m.is_after_market_close())

    @patch("fetch_pvc.datetime")
    def test_friday_before_close(self, mock_dt):
        """Friday before 15:00 → False."""
        tz = ZoneInfo("Asia/Shanghai")
        friday_10am = datetime(2026, 10, 30, 10, 0, 0, tzinfo=tz)  # Friday
        mock_dt.now.return_value = friday_10am
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        self.assertFalse(m.is_after_market_close())

    @patch("fetch_pvc.datetime")
    def test_weekday_after_close(self, mock_dt):
        """Weekday (Mon-Thu) 15:00+ → True (day session closed)."""
        tz = ZoneInfo("Asia/Shanghai")
        monday_3pm = datetime(2026, 10, 26, 15, 0, 0, tzinfo=tz)  # Monday
        mock_dt.now.return_value = monday_3pm
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        self.assertTrue(m.is_after_market_close())

    @patch("fetch_pvc.datetime")
    def test_weekday_before_close(self, mock_dt):
        """Weekday (Mon-Thu) before 15:00 → False."""
        tz = ZoneInfo("Asia/Shanghai")
        monday_10am = datetime(2026, 10, 26, 10, 0, 0, tzinfo=tz)  # Monday
        mock_dt.now.return_value = monday_10am
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        self.assertFalse(m.is_after_market_close())

    @patch("fetch_pvc.datetime")
    def test_saturday_returns_false(self, mock_dt):
        """Saturday → False (no trading)."""
        tz = ZoneInfo("Asia/Shanghai")
        saturday = datetime(2026, 10, 31, 10, 0, 0, tzinfo=tz)
        mock_dt.now.return_value = saturday
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        self.assertFalse(m.is_after_market_close())

    @patch("fetch_pvc.datetime")
    def test_sunday_day_returns_false(self, mock_dt):
        """Sunday before 23:00 → False (daytime, night session not yet started)."""
        tz = ZoneInfo("Asia/Shanghai")
        sunday = datetime(2026, 11, 1, 10, 0, 0, tzinfo=tz)
        mock_dt.now.return_value = sunday
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        self.assertFalse(m.is_after_market_close())


if __name__ == "__main__":
    unittest.main()
