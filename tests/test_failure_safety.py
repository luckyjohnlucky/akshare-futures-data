#!/usr/bin/env python3
"""Interface exception failure protection tests.

Verify: when the minute quote interface throws exceptions / returns None / returns empty /
validation fails, output/V2701_minute_bars.csv and
output/minute_data_quality.jsonl must not be emptied, truncated, or accidentally overwritten.

These tests use **temporary directories** to simulate formal output paths; all snapshot
comparisons are performed in an isolated environment, never reading or writing formal data files.
"""

import csv
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import fetch_pvc as m  # noqa: E402


def _sha(p):
    if not Path(p).exists():
        return "missing"
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _json_count(p):
    if not Path(p).exists():
        return -1
    return len(json.loads(Path(p).read_text(encoding="utf-8")))


def _csv_count(p):
    if not Path(p).exists():
        return -1
    with Path(p).open("r", encoding="utf-8-sig", newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


def _lines(p):
    if not Path(p).exists():
        return -1
    with Path(p).open("r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def snapshot():
    """Return (sha, size, count) tuple for before/after comparison."""
    snap = {}
    minute_csv = m.get_minute_csv("V2701")
    for key, path in (("csv", minute_csv),
                      ("quality", m.QUALITY_LOG)):
        if Path(path).exists():
            data = Path(path).read_bytes()
            snap[key] = (hashlib.sha256(data).hexdigest(), len(data),
                         _count_for(key, path))
        else:
            snap[key] = ("missing", 0, -1)
    return snap


def _count_for(key, path):
    return {"csv": _csv_count, "quality": _lines}[key](path)


def run_main_minute_block():
    """
    Faithfully reproduce the fetch_pvc.py __main__ minute fetch-update-export flow.
    Interface calls, None/empty checks, and update_minute_bars are all real functions.
    """
    minute_df = m.ak.futures_zh_minute_sina(symbol="V2701", period="1")
    if minute_df is None or minute_df.empty:
        raise RuntimeError("分钟数据为空，停止更新。")
    updated, total = m.update_minute_bars("V2701", minute_df)
    return updated, total


class InterfaceFailureSafetyTests(unittest.TestCase):
    def setUp(self):
        """Redirect all output paths to an isolated temp directory."""
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

        # Save original paths
        self._orig = {
            "MINUTE_BARS_CSV_V2701": m.get_minute_csv("V2701"),
            "QUALITY_LOG": m.QUALITY_LOG,
            "OUT": m.OUT,
        }

        # Redirect to temp
        m.OUT = self.dir
        m.QUALITY_LOG = self.dir / "minute_data_quality.jsonl"

        # Create minimal files so snapshot() works
        minute_csv = m.get_minute_csv("V2701")
        if not minute_csv.exists():
            minute_csv.write_text("", encoding="utf-8")
        if not m.QUALITY_LOG.exists():
            m.QUALITY_LOG.write_text("", encoding="utf-8")

        self.before = snapshot()

    def tearDown(self):
        after = snapshot()
        self.assertEqual(self.before, after,
                         "接口异常路径意外修改了正式行情/质控文件！")

        # Restore original paths
        for attr, path in self._orig.items():
            setattr(m, attr, path)

        self.tmp.cleanup()

    def test_interface_raises_propagates_and_files_intact(self):
        """Interface throws exception → exception propagates upward, no file written."""
        with patch.object(m.ak, "futures_zh_minute_sina",
                          side_effect=ConnectionError("模拟网络异常")):
            with self.assertRaises(ConnectionError):
                run_main_minute_block()

    def test_none_return_protects_files(self):
        """Interface returns None → RuntimeError, file unchanged."""
        with patch.object(m.ak, "futures_zh_minute_sina", return_value=None):
            with self.assertRaises(RuntimeError):
                run_main_minute_block()

    def test_empty_return_protects_files(self):
        """Interface returns empty DataFrame → RuntimeError, file unchanged."""
        with patch.object(m.ak, "futures_zh_minute_sina",
                          return_value=pd.DataFrame(
                              columns=["datetime", "open", "high", "low",
                                       "close", "volume", "hold"])):
            with self.assertRaises(RuntimeError):
                run_main_minute_block()

    def test_validation_failure_protects_files(self):
        """update_minute_bars internal validation fails → raised, CSV file not read/written."""
        bad_df = pd.DataFrame({"foo": [1, 2]})  # Missing all required fields
        with self.assertRaises(ValueError):
            m.update_minute_bars("V2701", bad_df)


if __name__ == "__main__":
    unittest.main()
