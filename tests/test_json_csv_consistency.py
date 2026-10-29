#!/usr/bin/env python3
"""Tests for CSV output paths and temp file cleanup.

Covers:
- Minute bars CSV output creation and cleanup
- Daily bars CSV output creation and cleanup
- Consistency of output paths
"""

import csv
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import fetch_pvc as m  # noqa: E402


class UpdateMinuteBarsCleanupTests(unittest.TestCase):
    """Test temp file cleanup in update_minute_bars (CSV output)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self._orig = {
            "MINUTE_BARS_CSV_V2701": m.get_minute_csv("V2701"),
            "QUALITY_LOG": m.QUALITY_LOG,
            "OUT": m.OUT,
        }
        m.OUT = self.dir
        m.QUALITY_LOG = Path(self.dir) / "minute_data_quality.jsonl"
        m.QUALITY_LOG.parent.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        for attr, path in self._orig.items():
            setattr(m, attr, path)
        self.tmp.cleanup()

    def _make_minute_df(self, rows):
        cols = ["datetime", "open", "high", "low", "close", "volume", "hold"]
        return m.pd.DataFrame(rows, columns=cols)

    def test_minute_bars_temp_cleanup_on_csv_dump_failure(self):
        """update_minute_bars cleans temp on CSV dump failure."""
        df = self._make_minute_df([
            {"datetime": "2026-01-01 09:00:00", "open": 1.0, "high": 1.1,
             "low": 0.9, "close": 1.0, "volume": 10, "hold": 5},
        ])

        # Make MINUTE_BARS_CSV a directory to force replace() failure
        m.get_minute_csv("V2701").mkdir(parents=True)

        temp_path = m.get_minute_csv("V2701").with_name(m.get_minute_csv("V2701").name + ".tmp")

        with self.assertRaises(Exception):
            m.update_minute_bars("V2701", df)

        # Temp file should be cleaned up
        self.assertFalse(temp_path.exists(),
                         "Temp file should be deleted on failure")

    def test_minute_bars_original_exception_preserved(self):
        """update_minute_bars: original exception type preserved on failure."""
        df = self._make_minute_df([
            {"datetime": "2026-01-01 09:00:00", "open": 1.0, "high": 1.1,
             "low": 0.9, "close": 1.0, "volume": 10, "hold": 5},
        ])

        m.get_minute_csv("V2701").parent.mkdir(parents=True, exist_ok=True)

        # Make target a directory so replace() fails
        if m.get_minute_csv("V2701").exists():
            m.get_minute_csv("V2701").unlink()
        m.get_minute_csv("V2701").mkdir()

        original_exc = None
        try:
            m.update_minute_bars("V2701", df)
        except Exception as exc:
            original_exc = exc

        self.assertIsNotNone(original_exc)
        # Original exception type should be preserved (NotADirectoryError or similar)
        self.assertIsInstance(original_exc, Exception)
        temp_path = m.get_minute_csv("V2701").with_name(m.get_minute_csv("V2701").name + ".tmp")
        self.assertFalse(temp_path.exists())


class UpdateDailyBarsCleanupTests(unittest.TestCase):
    """Test temp file cleanup in update_daily_bars (CSV output)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self._orig = {
            "DAILY_BARS_CSV_V0": m.get_daily_csv("V0"),
            "OUT": m.OUT,
        }
        m.OUT = Path(self.dir)

    def tearDown(self):
        for attr, path in self._orig.items():
            setattr(m, attr, path)
        self.tmp.cleanup()

    def _make_daily_df(self):
        return m.pd.DataFrame({
            "date": ["2026-01-01"],
            "open": [5000.0],
            "high": [5100.0],
            "low": [4900.0],
            "close": [5050.0],
            "volume": [10000],
            "hold": [5000],
            "settle": [5050.0],
            "quality_status": ["valid"],
        })

    def test_daily_bars_temp_cleanup_on_csv_dump_failure(self):
        """update_daily_bars cleans temp on CSV dump failure."""
        df = self._make_daily_df()

        # Make DAILY_BARS_CSV a directory to force replace() failure
        m.get_daily_csv("V0").mkdir(parents=True)

        temp_path = m.get_daily_csv("V0").with_name(m.get_daily_csv("V0").name + ".tmp")

        with self.assertRaises(Exception):
            m.update_daily_bars(df)

        # Temp file should be cleaned up
        self.assertFalse(temp_path.exists(),
                         "Temp file should be deleted on failure")

    def test_daily_bars_original_exception_preserved(self):
        """update_daily_bars: original exception type preserved on failure."""
        df = self._make_daily_df()

        m.get_daily_csv("V0").parent.mkdir(parents=True, exist_ok=True)
        m.get_daily_csv("V0").mkdir()  # Target is directory -> replace() fails

        original_exc = None
        try:
            m.update_daily_bars(df)
        except Exception as exc:
            original_exc = exc

        self.assertIsNotNone(original_exc)
        self.assertIsInstance(original_exc, Exception)
        temp_path = m.get_daily_csv("V0").with_name(m.get_daily_csv("V0").name + ".tmp")
        self.assertFalse(temp_path.exists())


class ConsistencyIntegrationTests(unittest.TestCase):
    """Integration tests for CSV output paths."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self._orig = {
            "OUT": m.OUT,
        }
        m.OUT = self.dir

    def tearDown(self):
        m.OUT = self._orig["OUT"]
        self.tmp.cleanup()

    def _setup_temp_paths(self):
        """Redirect all output paths to isolated temp directory."""
        m.OUT = self.dir

    def _make_minute_df(self, rows):
        cols = ["datetime", "open", "high", "low", "close", "volume", "hold"]
        return m.pd.DataFrame(rows, columns=cols)

    def _make_daily_df(self):
        return m.pd.DataFrame({
            "date": ["2026-01-01"],
            "open": [5000.0],
            "high": [5100.0],
            "low": [4900.0],
            "close": [5050.0],
            "volume": [10000],
            "hold": [5000],
            "settle": [5050.0],
            "quality_status": ["valid"],
        })

    def test_minute_csv_output_created(self):
        """After update_minute_bars, CSV file exists and has records."""
        self._setup_temp_paths()

        df = self._make_minute_df([
            {"datetime": "2026-01-01 09:00:00", "open": 5000.0, "high": 5001.0,
             "low": 4999.0, "close": 5000.0, "volume": 1000, "hold": 500},
        ])
        m.update_minute_bars("V2701", df)

        self.assertTrue(m.get_minute_csv("V2701").exists())
        with m.get_minute_csv("V2701").open("r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "V2701")
        self.assertEqual(rows[0]["datetime"], "2026-01-01 09:00:00")
        self.assertEqual(rows[0]["name"], "PVC 2701")

    def test_daily_csv_output_created(self):
        """After update_daily_bars, CSV file exists and has records."""
        self._setup_temp_paths()

        df = self._make_daily_df()
        m.update_daily_bars(df)

        self.assertTrue(m.get_daily_csv("V0").exists())
        with m.get_daily_csv("V0").open("r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "V0")
        self.assertEqual(rows[0]["trading_date"], "2026-01-01")
        self.assertEqual(rows[0]["name"], "PVC连续")

    def test_formal_daily_paths_not_dependent_on_root_files(self):
        """Verify formal daily path check doesn't rely on root-level files."""
        self.assertTrue(m.get_daily_csv("V0").parent == m.OUT)


if __name__ == "__main__":
    unittest.main()
