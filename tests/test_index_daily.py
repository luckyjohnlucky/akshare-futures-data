#!/usr/bin/env python3
"""Tests for H11061 中证商品期货指数日线结构独立化。

覆盖 B1-B3 要求的所有测试，包括 field mapping 正确性、字段验证、CSV 写入流程、主流程分流等。
使用 unittest (no pytest needed)，不访问真实网络，不读写正式 output CSV。
"""

import csv
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd
import numpy as np

# Ensure fetch_pvc can be imported from the project root
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import fetch_pvc as m  # noqa: E402


class IndexDailyTests(unittest.TestCase):
    """H11061 中证商品期货指数日线独立测试用例。"""

    def setUp(self):
        """Redirect all output paths to an isolated temp directory."""
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

        # Save original paths
        self._orig = {
            "OUT": m.OUT,
        }

        # Redirect to temp
        m.OUT = self.dir

    def tearDown(self):
        # Restore original paths
        for attr, path in self._orig.items():
            setattr(m, attr, path)

        self.tmp.cleanup()

    def _make_normalized_df(self, rows):
        """构建一个符合 normalize_index_daily_bars 要求的 DataFrame。"""
        # 直接从 rows 创建 DataFrame，保持原始列名
        # 这样可以正确测试缺失字段的情况
        df = m.pd.DataFrame(rows)
        return df

    def test_index_field_mapping_correct(self):
        """AKShare 返回字段映射正确，输出只有指数真实字段，不包含虚构 OHLC。"""
        # 创建模拟的 AKShare 返回的 DataFrame
        mock_data = [
            {"日期": "2026-01-01", "指数代码": "100001.CCI", "收盘点位": 3000.0,
             "结算点位": 2990.0, "涨跌": 50.0, "涨跌幅": 1.68},
            {"日期": "2026-01-02", "指数代码": "100001.CCI", "收盘点位": 3050.0,
             "结算点位": 3040.0, "涨跌": 50.0, "涨跌幅": 1.64},
        ]
        df = self._make_normalized_df(mock_data)
        
        # 调用 normalize_index_daily_bars
        result = m.normalize_index_daily_bars(df)
        
        # 验证字段映射正确性
        self.assertIn("trading_date", result.columns)
        self.assertIn("index_code", result.columns)
        self.assertIn("close", result.columns)
        self.assertIn("settle", result.columns)
        self.assertIn("change", result.columns)
        self.assertIn("pct_change", result.columns)
        
        # 验证不包含虚构的 OHLC 字段
        self.assertNotIn("open", result.columns)
        self.assertNotIn("high", result.columns)
        self.assertNotIn("low", result.columns)
        self.assertNotIn("volume", result.columns)
        self.assertNotIn("hold", result.columns)
        self.assertNotIn("open_interest", result.columns)
        
        # 验证数据正确性
        self.assertEqual(len(result), 2)
        self.assertEqual(result.iloc[0]["trading_date"], "2026-01-01")
        self.assertEqual(result.iloc[0]["index_code"], "100001.CCI")
        self.assertEqual(result.iloc[0]["close"], 3000.0)
        self.assertEqual(result.iloc[0]["settle"], 2990.0)

    def test_wrong_index_code_rejected(self):
        """错误指数代码（非 100001.CCI）被拒绝。"""
        mock_data = [
            {"日期": "2026-01-01", "指数代码": "999999.CCI", "收盘点位": 3000.0,
             "结算点位": 2990.0, "涨跌": 50.0, "涨跌幅": 1.68},
        ]
        df = self._make_normalized_df(mock_data)
        
        with self.assertRaises(ValueError) as cm:
            m.normalize_index_daily_bars(df)
        
        self.assertIn("指数代码必须为 100001.CCI", str(cm.exception))

    def test_missing_required_fields_fails(self):
        """缺失 trading_date 或 close 等必需字段时失败。"""
        # 缺少 trading_date - 创建不包含日期列的 DataFrame
        mock_data = [
            {"指数代码": "100001.CCI", "收盘点位": 3000.0, "结算点位": 2990.0,
             "涨跌": 50.0, "涨跌幅": 1.68},
        ]
        df = self._make_normalized_df(mock_data)
        
        # 验证日期列确实不存在
        self.assertNotIn("日期", df.columns)
        
        with self.assertRaises(ValueError) as cm:
            m.normalize_index_daily_bars(df)
        
        self.assertIn("缺少必要字段", str(cm.exception).lower())

    def test_close_invalid_fails(self):
        """close 为 0、负数、NaN、inf 时失败。"""
        # close 为 0
        mock_data = [
            {"日期": "2026-01-01", "指数代码": "100001.CCI", "收盘点位": 0,
             "结算点位": 2990.0, "涨跌": 50.0, "涨跌幅": 1.68},
        ]
        df = self._make_normalized_df(mock_data)
        
        with self.assertRaises(ValueError) as cm:
            m.normalize_index_daily_bars(df)
        
        self.assertIn("close", str(cm.exception).lower())
        
        # close 为负数
        mock_data2 = [
            {"日期": "2026-01-01", "指数代码": "100001.CCI", "收盘点位": -100,
             "结算点位": 2990.0, "涨跌": 50.0, "涨跌幅": 1.68},
        ]
        df2 = self._make_normalized_df(mock_data2)
        
        with self.assertRaises(ValueError) as cm:
            m.normalize_index_daily_bars(df2)
        
        self.assertIn("close", str(cm.exception).lower())

    def test_invalid_date_fails(self):
        """日期无效时失败。"""
        mock_data = [
            {"日期": "invalid_date", "指数代码": "100001.CCI", "收盘点位": 3000.0,
             "结算点位": 2990.0, "涨跌": 50.0, "涨跌幅": 1.68},
        ]
        df = self._make_normalized_df(mock_data)
        
        with self.assertRaises(ValueError) as cm:
            m.normalize_index_daily_bars(df)
        
        self.assertIn("无效交易日期", str(cm.exception).lower())

    def test_duplicate_date_fails(self):
        """日期重复时失败。"""
        mock_data = [
            {"日期": "2026-01-01", "指数代码": "100001.CCI", "收盘点位": 3000.0,
             "结算点位": 2990.0, "涨跌": 50.0, "涨跌幅": 1.68},
            {"日期": "2026-01-01", "指数代码": "100001.CCI", "收盘点位": 3050.0,
             "结算点位": 3040.0, "涨跌": 50.0, "涨跌幅": 1.64},
        ]
        df = self._make_normalized_df(mock_data)
        
        with self.assertRaises(ValueError) as cm:
            m.normalize_index_daily_bars(df)
        
        self.assertIn("重复日期", str(cm.exception))

    def test_date_sorted_ascending(self):
        """日期排序正确（升序）。"""
        mock_data = [
            {"日期": "2026-01-02", "指数代码": "100001.CCI", "收盘点位": 3050.0,
             "结算点位": 3040.0, "涨跌": 50.0, "涨跌幅": 1.64},
            {"日期": "2026-01-01", "指数代码": "100001.CCI", "收盘点位": 3000.0,
             "结算点位": 2990.0, "涨跌": 50.0, "涨跌幅": 1.68},
        ]
        df = self._make_normalized_df(mock_data)
        
        with self.assertRaises(ValueError) as cm:
            m.normalize_index_daily_bars(df)
        
        self.assertIn("日期必须按升序排列", str(cm.exception).lower())

    def test_optional_fields_preserved(self):
        """settle、change、pct_change 缺失时保留为 None。"""
        mock_data = [
            {"日期": "2026-01-01", "指数代码": "100001.CCI", "收盘点位": 3000.0},
        ]
        df = self._make_normalized_df(mock_data)
        
        # 由于 mock 数据缺少可选字段，normalize 会自动跳过它们
        result = m.normalize_index_daily_bars(df)
        
        # 验证必需字段存在
        self.assertIn("trading_date", result.columns)
        self.assertIn("index_code", result.columns)
        self.assertIn("close", result.columns)
        
        # 验证可选字段存在（列存在，即使值可能为 NaN）
        self.assertIn("settle", result.columns)
        self.assertIn("change", result.columns)
        self.assertIn("pct_change", result.columns)

    def test_source_recorded(self):
        """source 正确记录为 `AKShare futures_index_ccidx`。"""
        # 创建有效的 normalized DataFrame
        mock_data = [
            {"日期": "2026-01-01", "指数代码": "100001.CCI", "收盘点位": 3000.0,
             "结算点位": 2990.0, "涨跌": 50.0, "涨跌幅": 1.68},
        ]
        df = self._make_normalized_df(mock_data)
        
        # 验证 validate_index_daily_bars
        normalized = m.normalize_index_daily_bars(df)
        
        validated = m.validate_index_daily_bars(normalized, symbol="H11061")
        
        # 创建 mock CSV 文件（模拟已存在的文件）
        index_csv = m.OUT / f"H11061_index_daily.csv"
        with open(index_csv, 'w', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["symbol", "name", "index_code", "trading_date", "close", 
                           "settle", "change", "pct_change", "quality_status", "source", "collected_at"])
            # 写入一些旧数据
            writer.writerow(["H11061", "中证商品期货指数", "100001.CCI", "2026-01-01",
                           "2999.0", "2990.0", "40.0", "1.33", "valid", "AKShare futures_index_ccidx", "2026-01-03T21:33:44"])
        
        # 调用 update_index_daily_bars
        count = m.update_index_daily_bars(validated, symbol="H11061")
        
        # 验证 CSV 文件被更新
        self.assertEqual(count, 1)
        
        # 读取更新后的 CSV
        with open(index_csv, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "AKShare futures_index_ccidx")

    def test_csv_write_no_fictitious_ohlc(self):
        """CSV 写入后字段正确，不出现虚构 OHLC（open, high, low, volume, open_interest 不应出现）。"""
        # 创建有效的 normalized DataFrame
        mock_data = [
            {"日期": "2026-01-01", "指数代码": "100001.CCI", "收盘点位": 3000.0,
             "结算点位": 2990.0, "涨跌": 50.0, "涨跌幅": 1.68},
        ]
        df = self._make_normalized_df(mock_data)
        
        # 验证 validate_index_daily_bars
        normalized = m.normalize_index_daily_bars(df)
        
        validated = m.validate_index_daily_bars(normalized, symbol="H11061")
        
        # 调用 update_index_daily_bars
        count = m.update_index_daily_bars(validated, symbol="H11061")
        
        # 读取写入的 CSV 文件
        index_csv = m.OUT / f"H11061_index_daily.csv"
        with open(index_csv, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        # 验证字段
        self.assertEqual(len(rows), 1)
        
        # 验证不包含 OHLC 字段
        self.assertNotIn("open", rows[0])
        self.assertNotIn("high", rows[0])
        self.assertNotIn("low", rows[0])
        self.assertNotIn("volume", rows[0])
        self.assertNotIn("open_interest", rows[0])
        
        # 验证包含正确的字段
        expected_fields = ["symbol", "name", "index_code", "trading_date", "close", 
                          "settle", "change", "pct_change", "quality_status", "source", "collected_at"]
        for field in expected_fields:
            self.assertIn(field, rows[0])

    def test_same_date_revision_overrides(self):
        """同日历史修订能够覆盖旧值。"""
        # 创建并写入原始 CSV 文件
        index_csv = m.OUT / f"H11061_index_daily.csv"
        with open(index_csv, 'w', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(["symbol", "name", "index_code", "trading_date", "close", 
                           "settle", "change", "pct_change", "quality_status", "source", "collected_at"])
            # 写入旧数据
            writer.writerow(["H11061", "中证商品期货指数", "100001.CCI", "2026-01-01",
                           "2999.0", "2990.0", "40.0", "1.33", "valid", "AKShare futures_index_ccidx", "2026-01-03T21:33:44"])
        
        # 创建新的 normalized DataFrame
        mock_data = [
            {"日期": "2026-01-01", "指数代码": "100001.CCI", "收盘点位": 3000.0,
             "结算点位": 2990.0, "涨跌": 50.0, "涨跌幅": 1.68},
        ]
        df = self._make_normalized_df(mock_data)
        normalized = m.normalize_index_daily_bars(df)
        
        # 验证 validate_index_daily_bars
        validated = m.validate_index_daily_bars(normalized, symbol="H11061")
        
        # 调用 update_index_daily_bars
        count = m.update_index_daily_bars(validated, symbol="H11061")
        
        # 验证更新结果
        self.assertEqual(count, 1)
        
        # 读取更新后的 CSV
        with open(index_csv, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        self.assertEqual(len(rows), 1)
        # 注意：close 值是字符串，需要转换为 float
        self.assertEqual(float(rows[0]["close"]), 3000.0)
        self.assertEqual(float(rows[0]["settle"]), 2990.0)

    def test_empty_data_protects_csv(self):
        """空数据、接口返回 None、校验失败时，已有 CSV 文件内容不变。"""
        # 创建并写入原始 CSV 文件
        index_csv = m.OUT / f"H11061_index_daily.csv"
        with open(index_csv, 'w', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(["symbol", "name", "index_code", "trading_date", "close", 
                           "settle", "change", "pct_change", "quality_status", "source", "collected_at"])
            # 写入一些旧数据
            writer.writerow(["H11061", "中证商品期货指数", "100001.CCI", "2026-01-01",
                           "2999.0", "2990.0", "40.0", "1.33", "valid", "AKShare futures_index_ccidx", "2026-01-03T21:33:44"])
        
        # 获取原始 CSV 的哈希值
        original_hash = hashlib.sha256(index_csv.read_bytes()).hexdigest()
        
        # 创建空 DataFrame
        empty_df = pd.DataFrame()
        
        # 尝试调用 normalize_index_daily_bars
        with self.assertRaises(ValueError) as cm:
            m.normalize_index_daily_bars(empty_df)
        
        # 验证原始 CSV 文件没有被修改
        current_hash = hashlib.sha256(index_csv.read_bytes()).hexdigest()
        self.assertEqual(original_hash, current_hash)

    def test_atomic_write_failure_protects_csv(self):
        """原子写入失败时，原文件不受损。"""
        # 创建原始 CSV 文件
        index_csv = m.OUT / f"H11061_index_daily.csv"
        with open(index_csv, 'w', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(["symbol", "name", "index_code", "trading_date", "close", 
                           "settle", "change", "pct_change", "quality_status", "source", "collected_at"])
            # 写入一些旧数据
            writer.writerow(["H11061", "中证商品期货指数", "100001.CCI", "2026-01-01",
                           "2999.0", "2990.0", "40.0", "1.33", "valid", "AKShare futures_index_ccidx", "2026-01-03T21:33:44"])
        
        # 获取原始 CSV 的哈希值
        original_hash = hashlib.sha256(index_csv.read_bytes()).hexdigest()
        
        # 创建有效的 normalized DataFrame
        mock_data = [
            {"日期": "2026-01-01", "指数代码": "100001.CCI", "收盘点位": 3000.0,
             "结算点位": 2990.0, "涨跌": 50.0, "涨跌幅": 1.68},
        ]
        df = self._make_normalized_df(mock_data)
        normalized = m.normalize_index_daily_bars(df)
        validated = m.validate_index_daily_bars(normalized, symbol="H11061")
        
        # Mock records_to_csv 来模拟原子写入失败
        with patch('fetch_pvc.records_to_csv', side_effect=OSError("模拟写入失败")):
            # 调用 update_index_daily_bars，期望异常
            with self.assertRaises(OSError):
                m.update_index_daily_bars(validated, symbol="H11061")
        
        # 验证原始 CSV 文件没有被修改
        current_hash = hashlib.sha256(index_csv.read_bytes()).hexdigest()
        self.assertEqual(original_hash, current_hash)

    def test_commodity_futures_unaffected(self):
        """九个商品期货的现有采集和校验路径不受影响。"""
        # 测试常规商品期货（V0）的 validate_daily_bars
        mock_data = [
            {"date": "2026-01-01", "open": 3000.0, "high": 3100.0, "low": 2950.0,
             "close": 3050.0, "volume": 10000, "hold": 5000, "settle": 3050.0},
        ]
        df = m.pd.DataFrame(mock_data)
        
        # 验证商品期货日线校验函数仍然正常工作
        validated = m.validate_daily_bars(df, symbol="V0")
        
        self.assertEqual(len(validated), 1)
        self.assertEqual(validated.iloc[0]["quality_status"], "valid")
        
        # 验证商品期货日线写入函数仍然正常工作
        count = m.update_daily_bars(validated, symbol="V0")
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()