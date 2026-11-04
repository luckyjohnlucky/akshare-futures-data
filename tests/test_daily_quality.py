#!/usr/bin/env python3
"""Tests for daily bar quality handling.

Covers: confirmed errors deletion, known bad date marking, unknown anomaly marking,
status persistence, CSV atomic writes, symbol validation.
Uses unittest (no pytest needed), does not access the network.
"""

import csv
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

# Ensure fetch_pvc can be imported from the project root
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import fetch_pvc as m  # noqa: E402


class DailyQualityTests(unittest.TestCase):
    def setUp(self):
        """Redirect all output paths to an isolated temp directory."""
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

        # Save original paths
        self._orig = {
            "DAILY_BARS_CSV_V0": m.get_daily_csv("V0"),
            "OUT": m.OUT,
        }

        # Redirect to temp
        m.OUT = self.dir
        self._setup_csv_files()

    def _setup_csv_files(self):
        """Create minimal CSV files so tests work."""
        daily_csv = m.get_daily_csv("V0")
        if not daily_csv.exists():
            daily_csv.write_text("", encoding="utf-8")

    def tearDown(self):
        # Restore original paths
        for attr, path in self._orig.items():
            setattr(m, attr, path)

        self.tmp.cleanup()

    def _make_df(self, rows, include_quality_status=False):
        """Construct a daily DataFrame that can pass validation."""
        cols = ["date", "open", "high", "low", "close", "volume", "hold", "settle"]
        if include_quality_status:
            cols.append("quality_status")
        # Add symbol column to match real-world usage
        if any("symbol" in row for row in rows):
            cols.insert(0, "symbol")
        df = m.pd.DataFrame(rows, columns=cols)
        # Ensure symbol column exists and is set for all rows
        if "symbol" not in df.columns:
            df["symbol"] = "V0"
        return df

    def test_ta0_confirmed_error_is_deleted(self):
        """Confirmed TA0 OHLC anomaly (2006-12-28) is deleted."""
        # TA0 confirmed error on 2006-12-28: high < open AND high >= close, low < open
        # From confirmed_errors: {"high_open": True, "low_open": False, "high_close": False, "low_close": False}
        df = self._make_df([
            {"symbol": "TA0", "date": "2006-12-28", "open": 3000.0, "high": 2950.0,  # high < open, high >= close
             "low": 2500.0, "close": 2950.0, "volume": 10000, "hold": 5000, "settle": 2950.0},  # low < open
        ], include_quality_status=False)
        validated = m.validate_daily_bars(df, symbol="TA0")
        # The confirmed error record should be deleted, returning empty DataFrame
        self.assertEqual(len(validated), 0)

    def test_v0_not_affected_by_ta0_confirmed_error(self):
        """V0 with same OHLC pattern as TA0 confirmed error is NOT deleted."""
        # V0 on 2006-12-28: high < open (same OHLC pattern as TA0 confirmed error)
        df = self._make_df([
            {"symbol": "V0", "date": "2006-12-28", "open": 3000.0, "high": 2900.0,  # high < open
             "low": 2850.0, "close": 2950.0, "volume": 10000, "hold": 5000, "settle": 2950.0},
        ])
        validated = m.validate_daily_bars(df, symbol="V0")
        # V0 record should NOT be deleted (not in confirmed_errors for V0)
        self.assertEqual(len(validated), 1)

    def test_known_bad_date_marked_invalid_ohlc(self):
        """Known bad date (2011-01-03) is marked invalid_ohlc."""
        df = self._make_df([
            {"symbol": "V0", "date": "2011-01-03", "open": 3000.0, "high": 2900.0,  # high < open, invalid OHLC
             "low": 2950.0, "close": 2950.0, "volume": 10000, "hold": 5000, "settle": 2950.0},
        ])
        validated = m.validate_daily_bars(df, symbol="V0")
        # Record should be preserved
        self.assertEqual(len(validated), 1)
        # quality_status should be invalid_ohlc (known bad date with invalid OHLC)
        self.assertEqual(validated.iloc[0]["quality_status"], "invalid_ohlc")

    def test_unknown_ohlc_anomaly_marked_invalid_ohlc(self):
        """Unknown OHLC anomaly (2026-06-15) is marked invalid_ohlc with warning."""
        df = self._make_df([
            {"symbol": "V0", "date": "2026-06-15", "open": 3000.0, "high": 2900.0,  # high < open, anomaly
             "low": 2850.0, "close": 2950.0, "volume": 10000, "hold": 5000, "settle": 2950.0},
        ])
        with self.assertLogs(m.logger, level="WARNING") as cm:
            validated = m.validate_daily_bars(df, symbol="V0")
            # Should have logged warning about unknown anomaly
            self.assertTrue(any("检测到" in log and "条未知 OHLC 异常记录" in log for log in cm.output))
        # Record should be preserved
        self.assertEqual(len(validated), 1)
        # quality_status should be invalid_ohlc (unknown anomaly)
        self.assertEqual(validated.iloc[0]["quality_status"], "invalid_ohlc")

    def test_normal_data_marked_valid(self):
        """Normal OHLC data is marked valid with no record loss."""
        df = self._make_df([
            {"symbol": "V0", "date": "2026-01-01", "open": 3000.0, "high": 3100.0,
             "low": 2950.0, "close": 3050.0, "volume": 10000, "hold": 5000, "settle": 3050.0},
            {"symbol": "V0", "date": "2026-01-02", "open": 3050.0, "high": 3150.0,
             "low": 3000.0, "close": 3100.0, "volume": 12000, "hold": 6000, "settle": 3100.0},
        ])
        validated = m.validate_daily_bars(df, symbol="V0")
        # All records should be preserved
        self.assertEqual(len(validated), 2)
        # All should have valid quality_status
        self.assertTrue((validated["quality_status"] == "valid").all())

    def test_quality_status_persists_through_csv(self):
        """quality_status persists when writing to and reading from CSV."""
        # Create DataFrame with invalid_ohlc status (invalid OHLC)
        df = self._make_df([
            {"symbol": "V0", "date": "2026-01-01", "open": 3000.0, "high": 2900.0,  # high < open, invalid OHLC
             "low": 2850.0, "close": 2950.0, "volume": 10000, "hold": 5000, "settle": 2950.0,
             "quality_status": "invalid_ohlc"},
        ], include_quality_status=True)
        # Update daily bars
        count = m.update_daily_bars(df, symbol="V0")
        self.assertEqual(count, 1)
        # Re-read CSV
        records = m.csv_to_records(m.get_daily_csv("V0"))
        self.assertEqual(len(records), 1)
        # quality_status should still be invalid_ohlc
        self.assertEqual(records[0]["quality_status"], "invalid_ohlc")

    def test_new_record_overrides_old_with_invalid_ohlc(self):
        """New invalid_ohlc record overrides old valid record on same date."""
        # First write a valid record (2026-01-15)
        valid_df = self._make_df([
            {"symbol": "V0", "date": "2026-01-15", "open": 3000.0, "high": 3100.0,
             "low": 2950.0, "close": 3050.0, "volume": 10000, "hold": 5000, "settle": 3050.0,
             "quality_status": "valid"},
        ], include_quality_status=True)
        m.update_daily_bars(valid_df, symbol="V0")
        # Then write an invalid_ohlc record (same date) with invalid OHLC
        invalid_df = self._make_df([
            {"symbol": "V0", "date": "2026-01-15", "open": 3000.0, "high": 2900.0,  # OHLC anomaly
             "low": 2850.0, "close": 2950.0, "volume": 10000, "hold": 5000, "settle": 2950.0,
             "quality_status": "invalid_ohlc"},
        ], include_quality_status=True)
        m.update_daily_bars(invalid_df, symbol="V0")
        # Re-read CSV
        records = m.csv_to_records(m.get_daily_csv("V0"))
        # Only one record should exist, with invalid_ohlc status
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["quality_status"], "invalid_ohlc")

    def test_validation_failure_blocks_update(self):
        """Validation failure raises ValueError and blocks CSV update."""
        # Create DataFrame with duplicate dates (will cause validation failure)
        df = self._make_df([
            {"symbol": "V0", "date": "2026-01-01", "open": 3000.0, "high": 3100.0,
             "low": 2950.0, "close": 3050.0, "volume": 10000, "hold": 5000, "settle": 3050.0},
            {"symbol": "V0", "date": "2026-01-01", "open": 3050.0, "high": 3150.0,  # Same date, duplicate
             "low": 3000.0, "close": 3100.0, "volume": 12000, "hold": 6000, "settle": 3100.0},
        ])
        # Get original CSV hash if file exists
        daily_csv = m.get_daily_csv("V0")
        original_hash = None
        if daily_csv.exists():
            original_hash = hashlib.sha256(daily_csv.read_bytes()).hexdigest()
        # Try to validate daily bars, expecting ValueError
        with self.assertRaises(ValueError):
            m.validate_daily_bars(df, symbol="V0")
        # CSV file should not be modified
        if original_hash is not None:
            current_hash = hashlib.sha256(daily_csv.read_bytes()).hexdigest()
            self.assertEqual(original_hash, current_hash)

    def test_atomic_write_failure_protects_csv(self):
        """Atomic write failure leaves original CSV unchanged and cleans temp file."""
        # Create valid DataFrame to update
        df = self._make_df([
            {"symbol": "V0", "date": "2026-01-01", "open": 3000.0, "high": 3100.0,
             "low": 2950.0, "close": 3050.0, "volume": 10000, "hold": 5000, "settle": 3050.0,
             "quality_status": "valid"},
        ], include_quality_status=True)
        daily_csv = m.get_daily_csv("V0")
        # Get original CSV hash if file exists
        original_hash = None
        if daily_csv.exists():
            original_hash = hashlib.sha256(daily_csv.read_bytes()).hexdigest()
        # Mock os.replace to raise OSError
        temp_path = None
        try:
            with patch('os.replace', side_effect=OSError("模拟 replace 失败")) as mock_replace:
                # Call update_daily_bars, expecting OSError
                with self.assertRaises(OSError):
                    m.update_daily_bars(df, symbol="V0")
                # Temp file should not exist
                temp_path = daily_csv.with_name(daily_csv.name + ".tmp")
                self.assertFalse(temp_path.exists(),
                                 "Temp file should be deleted on failure")
        finally:
            # Clean up temp file if it exists
            if temp_path and temp_path.exists():
                temp_path.unlink()
        # Original CSV should not be modified
        if original_hash is not None:
            current_hash = hashlib.sha256(daily_csv.read_bytes()).hexdigest()
            self.assertEqual(original_hash, current_hash)

    def test_symbol_empty_string_rejected(self):
        """Empty string symbol is rejected with ValueError."""
        df = self._make_df([
            {"symbol": "V0", "date": "2026-01-01", "open": 3000.0, "high": 3100.0,
             "low": 2950.0, "close": 3050.0, "volume": 10000, "hold": 5000, "settle": 3050.0},
        ])
        with self.assertRaises(ValueError) as cm:
            m.validate_daily_bars(df, symbol="")
        self.assertIn("symbol", str(cm.exception).lower())

    def test_symbol_none_rejected(self):
        """None symbol is rejected with ValueError."""
        df = self._make_df([
            {"symbol": "V0", "date": "2026-01-01", "open": 3000.0, "high": 3100.0,
             "low": 2950.0, "close": 3050.0, "volume": 10000, "hold": 5000, "settle": 3050.0},
        ])
        with self.assertRaises(ValueError) as cm:
            m.validate_daily_bars(df, symbol=None)
        self.assertIn("symbol", str(cm.exception).lower())


if __name__ == "__main__":
    unittest.main()
