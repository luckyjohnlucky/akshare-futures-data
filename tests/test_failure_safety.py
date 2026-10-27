#!/usr/bin/env python3
"""接口异常失败保护测试。

验证：当分钟行情接口抛出异常 / 返回 None / 返回空 / 校验失败时，
output/minute_bars.json、output/minute_bars.csv 以及
output/minute_data_quality.jsonl 不能被清空、截断或意外覆盖。

这些测试使用**临时目录**模拟正式输出路径，所有快照比对在隔离环境下进行，
绝不读写正式数据文件。
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
    """返回 (sha, size, count) 三元组，便于前后比对。"""
    snap = {}
    for key, path in (("json", m.MINUTE_BARS),
                      ("csv", m.MINUTE_BARS_CSV),
                      ("quality", m.QUALITY_LOG)):
        if Path(path).exists():
            data = Path(path).read_bytes()
            snap[key] = (hashlib.sha256(data).hexdigest(), len(data),
                         _count_for(key, path))
        else:
            snap[key] = ("missing", 0, -1)
    return snap


def _count_for(key, path):
    return {"json": _json_count, "csv": _csv_count, "quality": _lines}[key](path)


def run_main_minute_block():
    """
    忠实复现 fetch_pvc.py __main__ 的分钟抓取—更新—导出流程。
    接口调用、None/空判断、update_minute_bars、json_to_csv 均为实物函数。
    """
    minute_df = m.ak.futures_zh_minute_sina(symbol="V2701", period="1")
    if minute_df is None or minute_df.empty:
        raise RuntimeError("分钟数据为空，停止更新。")
    updated, total = m.update_minute_bars("V2701", minute_df)
    m.json_to_csv(m.MINUTE_BARS, m.MINUTE_BARS_CSV)
    return updated, total


class InterfaceFailureSafetyTests(unittest.TestCase):
    def setUp(self):
        """Redirect all output paths to an isolated temp directory."""
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

        # Save original paths
        self._orig = {
            "MINUTE_BARS": m.MINUTE_BARS,
            "MINUTE_BARS_CSV": m.MINUTE_BARS_CSV,
            "QUALITY_LOG": m.QUALITY_LOG,
            "OUT": m.OUT,
        }

        # Redirect to temp
        m.OUT = self.dir
        m.MINUTE_BARS = self.dir / "minute_bars.json"
        m.MINUTE_BARS_CSV = self.dir / "minute_bars.csv"
        m.QUALITY_LOG = self.dir / "minute_data_quality.jsonl"

        # Create minimal files so snapshot() works
        if not m.MINUTE_BARS.exists():
            m.MINUTE_BARS.write_text("[]", encoding="utf-8")
        if not m.MINUTE_BARS_CSV.exists():
            m.MINUTE_BARS_CSV.write_text("", encoding="utf-8")
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
        """接口抛出异常 → 异常向上抛出，未写入任何文件。"""
        with patch.object(m.ak, "futures_zh_minute_sina",
                          side_effect=ConnectionError("模拟网络异常")):
            with self.assertRaises(ConnectionError):
                run_main_minute_block()

    def test_none_return_protects_files(self):
        """接口返回 None → RuntimeError，文件不变。"""
        with patch.object(m.ak, "futures_zh_minute_sina", return_value=None):
            with self.assertRaises(RuntimeError):
                run_main_minute_block()

    def test_empty_return_protects_files(self):
        """接口返回空 DataFrame → RuntimeError，文件不变。"""
        with patch.object(m.ak, "futures_zh_minute_sina",
                          return_value=pd.DataFrame(
                              columns=["datetime", "open", "high", "low",
                                       "close", "volume", "hold"])):
            with self.assertRaises(RuntimeError):
                run_main_minute_block()

    def test_validation_failure_protects_files(self):
        """update_minute_bars 内部校验失败 → 抛出，MINUTE_BARS 未读写。"""
        bad_df = pd.DataFrame({"foo": [1, 2]})  # 缺少全部必字段
        with self.assertRaises(ValueError):
            m.update_minute_bars("V2701", bad_df)


if __name__ == "__main__":
    unittest.main()
