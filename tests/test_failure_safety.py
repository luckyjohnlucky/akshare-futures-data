#!/usr/bin/env python3
"""Interface exception failure protection tests.

Verify: when the minute quote interface throws exceptions / returns None / returns empty /
validation fails, output/V0_minute_bars.csv and
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
    minute_csv = m.get_minute_csv("V0")
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
    minute_df = m.ak.futures_zh_minute_sina(symbol="V0", period="1")
    if minute_df is None or minute_df.empty:
        raise RuntimeError("分钟数据为空，停止更新。")
    updated, total = m.update_minute_bars("V0", minute_df)
    return updated, total


class InterfaceFailureSafetyTests(unittest.TestCase):
    def setUp(self):
        """Redirect all output paths to an isolated temp directory."""
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

        # Save original paths
        self._orig = {
            "MINUTE_BARS_CSV_V0": m.get_minute_csv("V0"),
            "QUALITY_LOG": m.QUALITY_LOG,
            "OUT": m.OUT,
        }

        # Redirect to temp
        m.OUT = self.dir
        m.QUALITY_LOG = self.dir / "minute_data_quality.jsonl"

        # Create minimal files so snapshot() works
        minute_csv = m.get_minute_csv("V0")
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
            m.update_minute_bars("V0", bad_df)


class RunCollectionTests(unittest.TestCase):
    """run_collection() exit-code and aggregation tests (mock only, no network/files)."""

    def _ok(self, tt, sym):
        return m.TaskResult(tt, sym, "success")

    # 1. all succeed
    def test_all_success_returns_zero(self):
        with patch.object(m, "_run_minute_bars", return_value=m.TaskResult("minute", "V0", "success")), \
             patch.object(m, "_run_daily_bars", return_value=m.TaskResult("daily", "V0", "success")):
            self.assertEqual(m.run_collection(["V0"]), 0)

    # 2. single daily failure
    def test_single_daily_failure_nonzero(self):
        with patch.object(m, "_run_minute_bars", return_value=m.TaskResult("minute", "V0", "success")), \
             patch.object(m, "_run_daily_bars", return_value=m.TaskResult("daily", "V0", "failed", "RuntimeError", "daily boom")):
            self.assertNotEqual(m.run_collection(["V0"]), 0)

    # 3. single minute failure
    def test_single_minute_failure_nonzero(self):
        with patch.object(m, "_run_minute_bars", return_value=m.TaskResult("minute", "V0", "failed", "ConnectionError", "net down")), \
             patch.object(m, "_run_daily_bars", return_value=m.TaskResult("daily", "V0", "success")):
            self.assertNotEqual(m.run_collection(["V0"]), 0)

    # 4. multiple failures all collected
    def test_multiple_failures_all_collected(self):
        with patch.object(m, "_run_minute_bars", return_value=m.TaskResult("minute", "V0", "failed", "E1", "m1")), \
             patch.object(m, "_run_daily_bars", return_value=m.TaskResult("daily", "V0", "failed", "E2", "m2")):
            with self.assertLogs(m.logger, level="ERROR") as cm:
                code = m.run_collection(["V0"])
            self.assertNotEqual(code, 0)
            joined = " ".join(cm.output)
            self.assertIn("E1", joined)
            self.assertIn("E2", joined)
            self.assertIn("minute", joined)
            self.assertIn("daily", joined)

    # 5. partial success still runs, nonzero
    def test_partial_success_runs_and_nonzero(self):
        def minute_ok(sym):
            return m.TaskResult("minute", sym, "success")
        def daily_fail(sym):
            return m.TaskResult("daily", sym, "failed", "RuntimeError", "bad")
        with patch.object(m, "_run_minute_bars", side_effect=minute_ok), \
             patch.object(m, "_run_daily_bars", side_effect=daily_fail):
            self.assertNotEqual(m.run_collection(["V0"]), 0)

    # 6. uncaught exception in a future is caught by scheduler
    def test_uncaught_future_exception_caught(self):
        def boom(sym):
            raise RuntimeError("uncradle boom")
        with patch.object(m, "_run_minute_bars", return_value=m.TaskResult("minute", "V0", "success")), \
             patch.object(m, "_run_daily_bars", side_effect=boom):
            with self.assertLogs(m.logger, level="ERROR") as cm:
                code = m.run_collection(["V0"])
            self.assertNotEqual(code, 0)
            self.assertTrue(any("boom" in line or "RuntimeError" in line or "调度器" in line for line in cm.output))

    # 7. log contains task type, symbol, error type and message
    def test_log_contains_type_symbol_exc_and_msg(self):
        with patch.object(m, "_run_minute_bars", return_value=m.TaskResult("minute", "TA0", "success")), \
             patch.object(m, "_run_daily_bars", return_value=m.TaskResult("daily", "TA0", "failed", "ValueError", "length mismatch!")):
            with self.assertLogs(m.logger, level="ERROR") as cm:
                self.assertNotEqual(m.run_collection(["TA0"]), 0)
            joined = " ".join(cm.output)
            self.assertIn("daily", joined)
            self.assertIn("TA0", joined)
            self.assertIn("ValueError", joined)
            self.assertIn("length mismatch!", joined)

    # 8. daily runs on every trigger (no time gate)
    def test_daily_runs_before_close(self):
        with patch.object(m, "fetch_and_update_daily_bars", return_value=2) as mock_fetch:
            result = m._run_daily_bars("V0")
            self.assertEqual(result.status, "success")
            self.assertEqual(result.outcome, "success")
            mock_fetch.assert_called_once_with("V0", "完整")

    def test_daily_changed_returns_success_outcome(self):
        with patch.object(m, "fetch_and_update_daily_bars", return_value=2):
            result = m._run_daily_bars("V0")
            self.assertEqual(result.status, "success")
            self.assertEqual(result.outcome, "success")

    def test_daily_no_new_data_outcome(self):
        with patch.object(m, "fetch_and_update_daily_bars", return_value=0):
            result = m._run_daily_bars("V0")
            self.assertEqual(result.status, "success")
            self.assertEqual(result.outcome, "no_new_data")

    def test_daily_failure_nonzero_via_run_collection(self):
        with patch.object(m, "_run_minute_bars", return_value=m.TaskResult("minute", "V0", "success")), \
             patch.object(m, "_run_daily_bars", wraps=m._run_daily_bars) as wrapped, \
             patch.object(m, "fetch_and_update_daily_bars", side_effect=RuntimeError("daily boom")):
            self.assertNotEqual(m.run_collection(["V0"]), 0)
            wrapped.assert_called_once_with("V0")

    def test_worker_count_is_six(self):
        import inspect
        source = inspect.getsource(m.run_collection)
        self.assertIn("max_workers=6", source)

    def test_run_collection_all_skipped_or_no_new_data(self):
        """All-skipped/no_new_data tasks: return 0, failed 0, no CSV write."""
        import itertools
        minute_results = [
            m.TaskResult("minute", "V0", "success", outcome="skipped"),
            m.TaskResult("minute", "TA0", "success", outcome="skipped"),
        ]
        daily_results = [
            m.TaskResult("daily", "V0", "success", outcome="no_new_data"),
            m.TaskResult("daily", "TA0", "success", outcome="no_new_data"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            before = {p.name: hashlib.md5(p.read_bytes()).hexdigest() for p in tmp_dir.iterdir()}
            orig_out = m.OUT
            m.OUT = tmp_dir
            try:
                with patch.object(m, "_run_minute_bars", side_effect=itertools.cycle(minute_results)) as mock_m, \
                     patch.object(m, "_run_daily_bars", side_effect=itertools.cycle(daily_results)) as mock_d, \
                     patch.object(m, "records_to_csv") as mock_csv, \
                     patch.object(m, "append_jsonl") as mock_jsonl:
                    with self.assertLogs(m.logger, level="INFO") as cm:
                        code = m.run_collection(["V0", "TA0"])
                self.assertEqual(code, 0)
                # 2 symbols x (1 minute + 1 daily) = 4 tasks, all collected
                self.assertEqual(mock_m.call_count, 2)
                self.assertEqual(mock_d.call_count, 2)
                joined = " ".join(cm.output)
                self.assertIn("总任务 4", joined)
                self.assertIn("成功 0", joined)
                self.assertIn("无新数据 2", joined)
                self.assertIn("跳过 2", joined)
                self.assertIn("失败 0", joined)
                self.assertNotIn("退出码 1", joined)
                mock_csv.assert_not_called()
                mock_jsonl.assert_not_called()
                after = {p.name: hashlib.md5(p.read_bytes()).hexdigest() for p in tmp_dir.iterdir()}
                self.assertEqual(before, after)
            finally:
                m.OUT = orig_out

    def test_task_result_outcome_compatibility(self):
        r = m.TaskResult("daily", "V0", "success")
        self.assertEqual(r.outcome, "success")
        self.assertTrue(r.ok)
        r2 = m.TaskResult("daily", "V0", "success", outcome="skipped")
        self.assertEqual(r2.outcome, "skipped")
        r3 = m.TaskResult("daily", "V0", "failed", "E", "m", outcome="skipped")
        self.assertEqual(r3.outcome, "failed")
        self.assertFalse(r3.ok)

    # 9. empty list submits nothing and returns 0
    def test_empty_list_no_tasks_zero(self):
        with patch.object(m, "_run_minute_bars") as mock_m, \
             patch.object(m, "_run_daily_bars") as mock_d:
            self.assertEqual(m.run_collection([]), 0)
            mock_m.assert_not_called()
            mock_d.assert_not_called()

    # 10. wrapper returning None is a failure
    def test_none_result_is_failure(self):
        with patch.object(m, "_run_minute_bars", return_value=None), \
             patch.object(m, "_run_daily_bars", return_value=m.TaskResult("daily", "V0", "success")):
            with self.assertLogs(m.logger, level="ERROR") as cm:
                code = m.run_collection(["V0"])
            self.assertNotEqual(code, 0)
            self.assertTrue(any("None" in line for line in cm.output))


if __name__ == "__main__":
    unittest.main()
