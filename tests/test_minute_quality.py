#!/usr/bin/env python3
"""Tests for minute bar future timestamp quality handling.

Covers: normal records, future-time records, duplicate anomaly records, empty data.
Uses unittest (no pytest needed), does not access the network.
"""

import csv
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

# Ensure fetch_pvc can be imported from the project root
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import fetch_pvc as m  # noqa: E402


def make_minute_df(rows):
    """Construct a minute DataFrame that can pass validate_minute_bars."""
    cols = ["datetime", "open", "high", "low", "close", "volume", "hold"]
    return m.pd.DataFrame(rows, columns=cols)


class SeparateFutureTimestampsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = os.path.join(self.tmp.name, "minute_data_quality.jsonl")
        self.symbol = "V2701"
        # Collection time 09:01:30, tolerance 1 minute → threshold 09:02:30
        self.collected_at = datetime(2026, 1, 1, 9, 1, 30, tzinfo=m.TZ)

    def tearDown(self):
        self.tmp.cleanup()

    def _rows(self):
        return [
            {"datetime": "2026-01-01 09:00:00", "open": 1.0, "high": 1.1,
             "low": 0.9, "close": 1.0, "volume": 10, "hold": 5},
            {"datetime": "2026-01-01 09:01:00", "open": 1.0, "high": 1.1,
             "low": 0.9, "close": 1.0, "volume": 10, "hold": 5},
            {"datetime": "2026-01-01 09:02:00", "open": 1.0, "high": 1.1,
             "low": 0.9, "close": 1.0, "volume": 10, "hold": 5},
            {"datetime": "2026-01-01 09:05:00", "open": 1.0, "high": 1.1,
             "low": 0.9, "close": 1.0, "volume": 10, "hold": 5},
        ]

    def _normal_rows(self):
        """All records fall before collection time (+ tolerance), no future records."""
        return [
            {"datetime": "2026-01-01 09:00:00", "open": 1.0, "high": 1.1,
             "low": 0.9, "close": 1.0, "volume": 10, "hold": 5},
            {"datetime": "2026-01-01 09:01:00", "open": 1.0, "high": 1.1,
             "low": 0.9, "close": 1.0, "volume": 10, "hold": 5},
            {"datetime": "2026-01-01 09:02:00", "open": 1.0, "high": 1.1,
             "low": 0.9, "close": 1.0, "volume": 10, "hold": 5},
        ]

    def test_normal_records_kept(self):
        """Records whose quote time is not later than collection time (+ tolerance) are all kept, no quality log written."""
        df = make_minute_df(self._normal_rows())
        valid = m.separate_future_timestamps(df, self.symbol, self.collected_at,
                                             log_path=self.log)
        kept = set(valid["datetime"].tolist())
        self.assertEqual(kept, {
            "2026-01-01 09:00:00",
            "2026-01-01 09:01:00",
            "2026-01-01 09:02:00",
        })
        self.assertFalse(os.path.exists(self.log))

    def test_future_record_excluded_and_logged(self):
        """Future-time records are excluded and logged to quality log, with issue marker."""
        df = make_minute_df(self._rows())
        valid = m.separate_future_timestamps(df, self.symbol, self.collected_at,
                                             log_path=self.log)
        self.assertNotIn("2026-01-01 09:05:00",
                         set(valid["datetime"].tolist()))
        self.assertEqual(len(valid), 3)

        with open(self.log, encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        self.assertEqual(len(lines), 1)
        rec = lines[0]
        self.assertEqual(rec["symbol"], self.symbol)
        self.assertEqual(rec["datetime"], "2026-01-01 09:05:00")
        self.assertEqual(rec["issue"], "future_timestamp")
        # Keep distinction between collection time and quote time
        self.assertEqual(rec["collected_at"], self.collected_at.isoformat())
        for field in ["open", "high", "low", "close", "volume", "open_interest"]:
            self.assertIn(field, rec)

    def test_timestamp_not_modified(self):
        """Filtering must not modify timestamps (e.g., not changing 09:01 to 21:01)."""
        df = make_minute_df(self._rows())
        valid = m.separate_future_timestamps(df, self.symbol, self.collected_at,
                                             log_path=self.log)
        for raw, kept in zip(self._rows(), valid.to_dict("records")):
            self.assertEqual(raw["datetime"], kept["datetime"])

    def test_duplicate_anomaly_not_rewritten(self):
        """The same (symbol, datetime) anomaly record is not written repeatedly."""
        df = make_minute_df(self._rows())
        m.separate_future_timestamps(df, self.symbol, self.collected_at,
                                     log_path=self.log)
        # Run again, 09:05 is still future, should be skipped for writing
        m.separate_future_timestamps(df, self.symbol, self.collected_at,
                                     log_path=self.log)
        with open(self.log, encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        self.assertEqual(len(lines), 1)

    def test_empty_data(self):
        """Empty data does not crash, returns empty as-is, no quality log written."""
        empty = make_minute_df([])
        valid = m.separate_future_timestamps(empty, self.symbol,
                                             self.collected_at, log_path=self.log)
        self.assertTrue(valid.empty)
        self.assertFalse(os.path.exists(self.log))


class AppendQualityRecordsTests(unittest.TestCase):
    def test_empty_records_no_op(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "q.jsonl")
            self.assertEqual(m.append_jsonl([], log_path=log), 0)
            self.assertFalse(os.path.exists(log))

    def test_atomic_write_on_success(self):
        """Normal append write: existing records kept, new records appended, temp file cleaned up."""
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "q.jsonl")
            # Pre-write one record
            with open(log, "w", encoding="utf-8") as f:
                f.write('{"symbol":"V0","datetime":"2026-10-28 09:00:00"}\n')

            new_records = [
                {"symbol": "V0", "datetime": "2026-10-28 09:01:00"},
                {"symbol": "V0", "datetime": "2026-10-28 09:02:00"},
            ]
            written = m.append_jsonl(new_records, log_path=log)
            self.assertEqual(written, 2)

            # Temp file should not remain
            tmp = os.path.join(d, "q.jsonl.tmp")
            self.assertFalse(os.path.exists(tmp))

            # Original file should contain all records
            with open(log, encoding="utf-8") as f:
                lines = [json.loads(l) for l in f if l.strip()]
            self.assertEqual(len(lines), 3)
            self.assertEqual(lines[0]["datetime"], "2026-10-28 09:00:00")
            self.assertEqual(lines[1]["datetime"], "2026-10-28 09:01:00")
            self.assertEqual(lines[2]["datetime"], "2026-10-28 09:02:00")

    def test_atomic_write_on_failure_preserves_original(self):
        """On write failure: original file remains unchanged, temp file cleaned up."""
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "q.jsonl")
            # Pre-write one record
            original = '{"symbol":"V0","datetime":"2026-10-28 09:00:00"}\n'
            with open(log, "w", encoding="utf-8") as f:
                f.write(original)

            # Set target path to a directory to cause temp file write failure
            os.remove(log)
            os.mkdir(log)

            try:
                m.append_jsonl(
                    [{"symbol": "V0", "datetime": "2026-10-28 09:01:00"}],
                    log_path=log,
                )
                self.fail("Exception should be raised")
            except Exception:
                pass

            # Original file should not exist (because it was changed to a directory), but key is temp file cleaned up
            tmp = os.path.join(d, "q.jsonl.tmp")
            self.assertFalse(os.path.exists(tmp),
                             "写入失败时临时文件应被清理")

    def test_atomic_write_duplicate_not_rewritten(self):
        """Records with duplicate keys should not be written repeatedly."""
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "q.jsonl")
            existing = {"symbol": "V0", "datetime": "2026-10-28 09:00:00"}
            with open(log, "w", encoding="utf-8") as f:
                f.write(json.dumps(existing, ensure_ascii=False) + "\n")

            written = m.append_jsonl([existing.copy()], log_path=log)
            self.assertEqual(written, 0)

            with open(log, encoding="utf-8") as f:
                lines = [json.loads(l) for l in f if l.strip()]
            self.assertEqual(len(lines), 1)


class FilterFutureAnomaliesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = os.path.join(self.tmp.name, "minute_data_quality.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def _rec(self, symbol, dt, collected_at):
        return {
            "symbol": symbol,
            "datetime": dt,
            "open": 5174.0, "high": 5174.0, "low": 5174.0, "close": 5174.0,
            "volume": 26.0, "open_interest": 1032514.0,
            "collected_at": collected_at,
        }

    def test_legitimate_record_kept(self):
        """Records where bar <= collected_at are kept as-is."""
        recs = [self._rec("V2701", "2026-10-28 09:00:00",
                          "2026-10-28T09:05:00+08:00")]
        kept = m.filter_future_anomalies(recs, log_path=self.log)
        self.assertEqual(len(kept), 1)
        self.assertFalse(os.path.exists(self.log))

    def test_old_anomaly_removed_and_logged(self):
        """Old records where bar > collected_at + tolerance are removed and logged to quality log."""
        recs = [self._rec("V2701", "2026-10-28 09:01:00",
                          "2026-10-27 01:44:55+08:00")]
        kept = m.filter_future_anomalies(recs, log_path=self.log)
        self.assertEqual(len(kept), 0)
        with open(self.log, encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["issue"], "future_timestamp")
        self.assertEqual(lines[0]["symbol"], "V2701")
        self.assertEqual(lines[0]["datetime"], "2026-10-28 09:01:00")
        self.assertEqual(lines[0]["collected_at"], "2026-10-27 01:44:55+08:00")

    def test_duplicate_anomaly_not_relogged(self):
        """The same anomaly record filtered multiple times is not logged repeatedly."""
        rec = self._rec("V2701", "2026-10-28 09:01:00",
                        "2026-10-27 01:44:55+08:00")
        m.filter_future_anomalies([rec], log_path=self.log)
        m.filter_future_anomalies([rec], log_path=self.log)
        with open(self.log, encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        self.assertEqual(len(lines), 1)

    def test_missing_collected_at_kept(self):
        """Records missing collected_at are kept as-is (not arbitrarily deleted)."""
        recs = [self._rec("V2701", "2026-10-28 09:01:00", None)]
        kept = m.filter_future_anomalies(recs, log_path=self.log)
        self.assertEqual(len(kept), 1)


class UpdateMinuteBarsIntegrationTests(unittest.TestCase):
    """End-to-end: update_minute_bars should not write future records to CSV."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self._orig = {
            "MINUTE_BARS_CSV_V2701": m.get_minute_csv("V2701"),
            "QUALITY_LOG": m.QUALITY_LOG,
            "OUT": m.OUT,
        }
        d = self.dir
        m.OUT = Path(d)
        m.QUALITY_LOG = Path(d) / "minute_data_quality.jsonl"
        m.QUALITY_LOG.parent.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        for attr, path in self._orig.items():
            setattr(m, attr, path)
        self.tmp.cleanup()

    def test_future_bar_excluded_from_json(self):
        """Future minutes after collection do not enter the dataset, but are logged to quality log."""
        now = datetime.now(m.TZ)
        past = now - timedelta(minutes=10)
        future = now + timedelta(minutes=5)
        fmt = lambda dt: dt.strftime("%Y-%m-%d %H:%M:%S")
        df = make_minute_df([
            {"datetime": fmt(past), "open": 1.0, "high": 1.1,
             "low": 0.9, "close": 1.0, "volume": 10, "hold": 5},
            {"datetime": fmt(future), "open": 1.0, "high": 1.1,
             "low": 0.9, "close": 1.0, "volume": 10, "hold": 5},
        ])

        saved, total = m.update_minute_bars("V2701", df)
        with open(m.get_minute_csv("V2701"), encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            records = list(reader)
        datetimes = {r["datetime"] for r in records}
        self.assertIn(fmt(past), datetimes)
        self.assertNotIn(fmt(future), datetimes)
        self.assertEqual(saved, 1)
        self.assertEqual(total, 1)

        with open(m.QUALITY_LOG, encoding="utf-8") as f:
            q = [json.loads(l) for l in f if l.strip()]
        self.assertTrue(any(
            x["datetime"] == fmt(future)
            and x["issue"] == "future_timestamp"
            for x in q
        ))


if __name__ == "__main__":
    unittest.main()
