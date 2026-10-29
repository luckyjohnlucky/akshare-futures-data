#!/usr/bin/env python3
"""分钟线未来时间戳质量处理的测试。

覆盖：正常记录、未来时间记录、重复异常记录、空数据情况。
使用 unittest（无需 pytest），不访问网络。
"""

import csv
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

# 确保能从项目根导入 fetch_pvc
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import fetch_pvc as m  # noqa: E402


def make_minute_df(rows):
    """构造可通过 validate_minute_bars 的分钟 DataFrame。"""
    cols = ["datetime", "open", "high", "low", "close", "volume", "hold"]
    return m.pd.DataFrame(rows, columns=cols)


class SeparateFutureTimestampsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = os.path.join(self.tmp.name, "minute_data_quality.jsonl")
        self.symbol = "V2701"
        # 采集时间 09:01:30，容差 1 分钟 → 阈值 09:02:30
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
        """全部落在采集时间(+容差) 之前，无未来记录。"""
        return [
            {"datetime": "2026-01-01 09:00:00", "open": 1.0, "high": 1.1,
             "low": 0.9, "close": 1.0, "volume": 10, "hold": 5},
            {"datetime": "2026-01-01 09:01:00", "open": 1.0, "high": 1.1,
             "low": 0.9, "close": 1.0, "volume": 10, "hold": 5},
            {"datetime": "2026-01-01 09:02:00", "open": 1.0, "high": 1.1,
             "low": 0.9, "close": 1.0, "volume": 10, "hold": 5},
        ]

    def test_normal_records_kept(self):
        """行情时间不晚于采集时间(+容差)的记录全部保留，不写质控日志。"""
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
        """未来时间记录被剔除并写入质控日志，含 issue 标记。"""
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
        # 保留采集时间与行情时间的区别
        self.assertEqual(rec["collected_at"], self.collected_at.isoformat())
        for field in ["open", "high", "low", "close", "volume", "open_interest"]:
            self.assertIn(field, rec)

    def test_timestamp_not_modified(self):
        """过滤不得修改时间戳（不把 09:01 改成 21:01 等）。"""
        df = make_minute_df(self._rows())
        valid = m.separate_future_timestamps(df, self.symbol, self.collected_at,
                                             log_path=self.log)
        for raw, kept in zip(self._rows(), valid.to_dict("records")):
            self.assertEqual(raw["datetime"], kept["datetime"])

    def test_duplicate_anomaly_not_rewritten(self):
        """同一条 (symbol, datetime) 异常记录不重复写入。"""
        df = make_minute_df(self._rows())
        m.separate_future_timestamps(df, self.symbol, self.collected_at,
                                     log_path=self.log)
        # 再次运行，09:05 仍为未来，应被跳过写入
        m.separate_future_timestamps(df, self.symbol, self.collected_at,
                                     log_path=self.log)
        with open(self.log, encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        self.assertEqual(len(lines), 1)

    def test_empty_data(self):
        """空数据不崩溃，原样返回空，未写质控日志。"""
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
        """bar <= collected_at 的记录原样保留。"""
        recs = [self._rec("V2701", "2026-10-28 09:00:00",
                          "2026-10-28T09:05:00+08:00")]
        kept = m.filter_future_anomalies(recs, log_path=self.log)
        self.assertEqual(len(kept), 1)
        self.assertFalse(os.path.exists(self.log))

    def test_old_anomaly_removed_and_logged(self):
        """bar > collected_at + 容差 的旧记录被移除并写入质控日志。"""
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
        """同一条异常记录多次过滤不重复写入日志。"""
        rec = self._rec("V2701", "2026-10-28 09:01:00",
                        "2026-10-27 01:44:55+08:00")
        m.filter_future_anomalies([rec], log_path=self.log)
        m.filter_future_anomalies([rec], log_path=self.log)
        with open(self.log, encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        self.assertEqual(len(lines), 1)

    def test_missing_collected_at_kept(self):
        """缺少 collected_at 的记录原样保留（不擅自删除）。"""
        recs = [self._rec("V2701", "2026-10-28 09:01:00", None)]
        kept = m.filter_future_anomalies(recs, log_path=self.log)
        self.assertEqual(len(kept), 1)


class UpdateMinuteBarsIntegrationTests(unittest.TestCase):
    """端到端：update_minute_bars 不应把未来记录写入 CSV。"""

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
        """采集后的未来分钟不进入数据集，但被记录到质控日志。"""
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
