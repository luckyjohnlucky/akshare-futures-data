#!/usr/bin/env python3
"""Collect PVC futures contract real-time snapshots and historical daily bars."""
from __future__ import annotations

import csv
import json
import logging
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

import requests

_original_requests_get = requests.get

def _requests_get_with_timeout(*args, **kwargs):
    if "timeout" not in kwargs or kwargs["timeout"] is None:
        kwargs["timeout"] = (10, 30)
    response = _original_requests_get(*args, **kwargs)
    response.raise_for_status()
    return response

requests.get = _requests_get_with_timeout
requests.api.get = _requests_get_with_timeout

import akshare as ak
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

HTTP_CONNECT_TIMEOUT = 10
HTTP_READ_TIMEOUT = 30
HTTP_TIMEOUT = (HTTP_CONNECT_TIMEOUT, HTTP_READ_TIMEOUT)
RETRYABLE_HTTP_STATUS_CODES = {429, 500, 502, 503, 504}


def _is_retryable_exception(exc: Exception) -> bool:
    if isinstance(exc, requests.Timeout):
        return True
    if isinstance(exc, requests.ConnectionError):
        return True
    if isinstance(exc, requests.HTTPError):
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        return status_code in RETRYABLE_HTTP_STATUS_CODES
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    return False


def _retryable_call(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    *args,
    **kwargs,
):
    """Retry call with exponential backoff.

    Only retry retryable exceptions (requests.Timeout, requests.ConnectionError,
    HTTP 429/500/502/503/504, TimeoutError, ConnectionError); ValueError,
    RuntimeError, other data format exceptions, and non-retryable HTTP status
    codes are raised directly without retry.

    Parameters:
        func: Function to call
        max_retries: Maximum number of retries
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
    """
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            if not _is_retryable_exception(exc):
                raise
            last_exc = exc
            if attempt < max_retries:
                delay = min(base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5), max_delay)
                logger.warning(
                    "调用 %s 失败（第 %d/%d 次）：%s，%.1f 秒后重试",
                    func.__name__, attempt, max_retries, exc, delay,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "调用 %s 失败（已达最大重试 %d 次）：%s",
                    func.__name__, max_retries, exc,
                )
    raise last_exc


OUT = Path(__file__).resolve().parent / "output"
TZ = ZoneInfo("Asia/Shanghai")

SYMBOL_NAME_MAP = {
    "V0": "PVC连续",
    "TA0": "PTA连续",
    "MA0": "甲醇连续",
    "PP0": "PP连续",
    "L0": "塑料连续",
    "SA0": "纯碱连续",
    "FG0": "玻璃连续",
    "RB0": "螺纹钢连续",
    "HC0": "热卷连续",
    "H11061": "中证商品期货指数",
}

# 需主动采集的合约列表（九个商品期货主力连续 + 1个指数）
# 只有列在此列表中的合约才会被主循环提交采集任务
ACTIVE_CONTRACTS = ["V0", "TA0", "MA0", "PP0", "L0", "SA0", "FG0", "RB0", "HC0", "H11061"]


def get_daily_csv(symbol: str) -> Path:
    """Return the daily CSV path for the given symbol."""
    return OUT / f"{symbol}_daily_bars.csv"


def get_minute_csv(symbol: str) -> Path:
    """Return the minute CSV path for the given symbol."""
    return OUT / f"{symbol}_minute_bars.csv"


QUALITY_LOG = OUT / "minute_data_quality.jsonl"
FUTURE_TIMESTAMP_TOLERANCE = timedelta(minutes=1)


def clean(value: Any) -> Any:
    """Convert Pandas/Numpy values to serializable plain Python values."""
    if value is None or pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, (int, float, str, bool)):
        return value
    return str(value)


def normalize_index_daily_bars(df: pd.DataFrame) -> pd.DataFrame:
    """Convert ak.futures_index_ccidx(symbol='中证商品期货指数') 的返回数据转换为指数专用结构。
    
    Args:
        df: 从 AKShare futures_index_ccidx 获取的原始 DataFrame
        
    Returns:
        包含 trading_date, index_code, close, settle, change, pct_change 列的标准化 DataFrame
        
    Raises:
        ValueError: 当数据无效时抛出
    """
    # 检查 df 是否为 None 或空
    if df is None or df.empty:
        raise ValueError("指数日线数据为空")
    
    # 中英文字段映射
    column_map = {
        '日期': 'trading_date',
        '指数代码': 'index_code', 
        '收盘点位': 'close',
        '结算点位': 'settle',
        '涨跌': 'change',
        '涨跌幅': 'pct_change',
    }
    
    # 检查必需的中文列名
    required_chinese_cols = ['日期', '指数代码', '收盘点位']
    if not all(col in df.columns for col in required_chinese_cols):
        missing_cols = [col for col in required_chinese_cols if col not in df.columns]
        raise ValueError(f"指数日线数据缺少必要字段：{missing_cols}")
    
    # 只保留需要的列并重命名
    available_cols = [col for col in column_map.keys() if col in df.columns]
    normalized = df[available_cols].rename(columns=column_map)
    
    # 验证指数代码
    invalid_codes = normalized[~normalized['index_code'].astype(str).str.strip().eq('100001.CCI')]
    if not invalid_codes.empty:
        examples = invalid_codes['index_code'].head(5).tolist()
        raise ValueError(f"指数代码必须为 100001.CCI，但发现了 {len(invalid_codes)} 条记录：{examples}")
    
    # 验证日期格式
    dates = pd.to_datetime(normalized['trading_date'], errors='coerce')
    if dates.isna().any():
        bad_rows = normalized.index[dates.isna()].tolist()[:10]
        raise ValueError(f"指数日线存在无效交易日期：{bad_rows}")
    
    # 检查重复日期
    normalized_dates = dates.dt.strftime("%Y-%m-%d")
    duplicated = normalized_dates[normalized_dates.duplicated(keep=False)]
    if not duplicated.empty:
        examples = sorted(set(duplicated.tolist()))[:10]
        raise ValueError(f"指数日线存在重复日期：{examples}")
    
    # 检查日期排序（升序）
    if not normalized_dates.is_monotonic_increasing:
        raise ValueError("指数日线日期必须按升序排列")
    
    # 日期转换为 %Y-%m-%d 字符串格式
    normalized['trading_date'] = normalized_dates
    
    # close 必须是有限、正数
    close_values = pd.to_numeric(normalized['close'], errors='coerce')
    if close_values.isna().any():
        invalid_indices = normalized.index[close_values.isna()].tolist()[:10]
        raise ValueError(f"close 字段存在缺失或非数值，行索引示例：{invalid_indices}")
    
    if not np.isfinite(close_values).all():
        invalid_indices = normalized.index[~np.isfinite(close_values)].tolist()[:10]
        raise ValueError(f"close 字段存在非有限数值，行索引示例：{invalid_indices}")
    
    if (close_values <= 0).any():
        invalid_indices = normalized.index[close_values <= 0].tolist()[:10]
        raise ValueError(f"close 字段存在小于或等于 0 的值，行索引示例：{invalid_indices}")
    
    normalized['close'] = close_values
    
    # 确保可选字段存在，如果不存在则设置为 None
    for field in ['settle', 'change', 'pct_change']:
        if field not in normalized.columns:
            normalized[field] = None
    
    # 只保留需要的字段
    required_fields = ['trading_date', 'index_code', 'close', 'settle', 'change', 'pct_change']
    result = normalized[required_fields].copy()
    
    return result


def validate_index_daily_bars(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """独立校验函数，独立于商品期货的 validate_daily_bars。
    
    Args:
        df: 指数日线数据 DataFrame
        symbol: 合约代码，必须为 "H11061"
        
    Returns:
        包含 quality_status 列的校验通过的 DataFrame
        
    Raises:
        ValueError: 当校验失败时抛出
    """
    # symbol 必须为非空字符串
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol 必须为非空字符串")
    
    if symbol != "H11061":
        raise ValueError(f"指数日线只支持 symbol=H11061，但得到了：{symbol}")
    
    # 必需字段校验
    required_fields = ["trading_date", "index_code", "close"]
    missing = [field for field in required_fields if field not in df.columns]
    if missing:
        raise ValueError(f"指数日线缺少必要字段：{missing}")
    
    # 空数据校验
    if df.empty:
        raise ValueError("指数日线数据为空")
    
    data = df.copy()
    
    # 日期校验
    dates = pd.to_datetime(data["trading_date"], errors="coerce")
    if dates.isna().any():
        bad_rows = data.index[dates.isna()].tolist()[:10]
        raise ValueError(f"指数日线存在无效交易日期，行索引示例：{bad_rows}")
    
    # 日期重复校验
    normalized_dates = dates.dt.strftime("%Y-%m-%d")
    duplicated = normalized_dates[normalized_dates.duplicated(keep=False)]
    if not duplicated.empty:
        examples = sorted(set(duplicated.tolist()))[:10]
        raise ValueError(f"指数日线存在重复日期：{examples}")
    
    # 日期升序校验
    if not normalized_dates.is_monotonic_increasing:
        raise ValueError("指数日线日期必须按升序排列")
    
    # index_code 校验
    data["index_code"] = data["index_code"].astype(str).str.strip()
    invalid_codes = data[~data["index_code"].eq("100001.CCI")]
    if not invalid_codes.empty:
        examples = invalid_codes["index_code"].head(5).tolist()
        raise ValueError(f"指数代码必须为 100001.CCI，但发现了 {len(invalid_codes)} 条记录：{examples}")
    
    # close 必须是有限、正数
    close_values = pd.to_numeric(data["close"], errors="coerce")
    if close_values.isna().any():
        invalid_indices = data.index[close_values.isna()].tolist()[:10]
        raise ValueError(f"close 字段存在缺失或非数值，行索引示例：{invalid_indices}")
    
    if not np.isfinite(close_values).all():
        invalid_indices = data.index[~np.isfinite(close_values)].tolist()[:10]
        raise ValueError(f"close 字段存在非有限数值，行索引示例：{invalid_indices}")
    
    if (close_values <= 0).any():
        invalid_indices = data.index[close_values <= 0].tolist()[:10]
        raise ValueError(f"close 字段存在小于或等于 0 的值，行索引示例：{invalid_indices}")
    
    data["close"] = close_values
    
    # settle、change、pct_change 缺失时保留为 None
    for field in ["settle", "change", "pct_change"]:
        if field in data.columns:
            # 将空值转换为 None
            data[field] = data[field].where(pd.notnull(data[field]), None)
    
    # 标记质量状态
    data["quality_status"] = "valid"
    
    return data


def update_index_daily_bars(df: pd.DataFrame, symbol: str = "H11061") -> int:
    """独立于 update_daily_bars 的指数日线写入函数。
    
    Args:
        df: 校验通过的指数日线数据
        symbol: 合约代码，默认 "H11061"
        
    Returns:
        更新记录数
    """
    # 验证 symbol
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol 必须为非空字符串")
    
    if symbol != "H11061":
        raise ValueError(f"指数日线只支持 symbol=H11061，但得到了：{symbol}")
    
    # 元数据
    name = "中证商品期货指数"
    index_code = "100001.CCI"
    source = "AKShare futures_index_ccidx"
    collected_at_str = datetime.now(TZ).isoformat()
    
    # 构建记录
    records_by_key = {}
    
    # 读取现有文件
    index_csv = OUT / f"{symbol}_index_daily.csv"
    if index_csv.exists():
        old_records = csv_to_records(index_csv)
        for item in old_records:
            if not isinstance(item, dict) or not item.get("symbol") or not item.get("trading_date"):
                raise ValueError("指数日线历史文件存在缺少 symbol/trading_date 的记录")
            key = (item["symbol"], item["trading_date"])
            records_by_key[key] = item
    
    # 处理新记录
    for _, row in df.iterrows():
        trading_date = pd.to_datetime(row["trading_date"]).date().isoformat()
        
        # 验证必需字段
        if pd.isna(row.get("close")) or row["close"] is None:
            raise ValueError(f"交易日期 {trading_date} 缺少 close 字段")
        
        # 保留原始 float 值类型，避免转换为整数
        close_val = row["close"]
        if pd.isna(close_val):
            close_val = None
        
        settle_val = row.get("settle")
        if pd.isna(settle_val):
            settle_val = None
        
        change_val = row.get("change")
        if pd.isna(change_val):
            change_val = None
        
        pct_change_val = row.get("pct_change")
        if pd.isna(pct_change_val):
            pct_change_val = None
        
        record = {
            "symbol": symbol,
            "name": name,
            "index_code": index_code,
            "trading_date": trading_date,
            "close": close_val,
            "settle": settle_val,
            "change": change_val,
            "pct_change": pct_change_val,
            "quality_status": clean(row.get("quality_status")) or "valid",
            "source": source,
            "collected_at": collected_at_str,
        }
        
        # 相同交易日更新
        records_by_key[(symbol, trading_date)] = record
    
    # 按 symbol, trading_date 排序
    result = sorted(
        records_by_key.values(),
        key=lambda item: (item["symbol"], item["trading_date"]),
    )
    
    # 写入文件（原子写入）
    count = records_to_csv(result, index_csv)
    return count


def number(value: Any) -> Optional[float | int]:
    value = clean(value)
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(f):
        return None
    return int(f) if f == int(f) else f


def validate_daily_bars(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Validate historical daily bars: dates, values, and OHLC logic; delete confirmed source data errors."""
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol 必须为非空字符串")
    
    required = {
        "date", "open", "high", "low", "close",
        "volume", "hold", "settle",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"历史日线缺少必要字段：{sorted(missing)}")

    if df.empty:
        raise ValueError("历史日线为空")

    data = df.copy()

    # Dates must be valid and non-duplicate
    dates = pd.to_datetime(data["date"], errors="coerce")
    if dates.isna().any():
        bad_rows = data.index[dates.isna()].tolist()[:10]
        raise ValueError(f"存在无效交易日期，行索引示例：{bad_rows}")

    normalized_dates = dates.dt.strftime("%Y-%m-%d")
    duplicated = normalized_dates[normalized_dates.duplicated(keep=False)]
    if not duplicated.empty:
        examples = sorted(set(duplicated.tolist()))[:10]
        raise ValueError(f"历史日线存在重复日期：{examples}")

    # Prices must be finite positive numbers; settle allows source data to use 0 for missing
    price_columns = ["open", "high", "low", "close"]
    for column in price_columns:
        values = pd.to_numeric(data[column], errors="coerce")
        if values.isna().any():
            raise ValueError(f"价格字段 {column} 存在缺失或非数值")
        if not np.isfinite(values).all():
            raise ValueError(f"价格字段 {column} 存在非有限数值")
        if (values <= 0).any():
            raise ValueError(f"价格字段 {column} 存在小于或等于 0 的值")
        data[column] = values

    settle = pd.to_numeric(data["settle"], errors="coerce")
    # NaN indicates missing (source data uses 0 for missing, written as None); allowed;
    # but non-NaN non-finite values (inf) and negative values are not allowed.
    if (~settle.isna() & ~np.isfinite(settle)).any():
        raise ValueError("结算价存在非有限值")
    if (~settle.isna() & (settle < 0)).any():
        raise ValueError("结算价存在负值")
    data["settle"] = settle

    # OHLC relationship must hold
    invalid = (
        (data["high"] < data[["open", "close", "low"]].max(axis=1))
        | (data["low"] > data[["open", "close", "high"]].min(axis=1))
    )

    # Confirmed source data errors - delete these records directly
    confirmed_errors = {
        # TA0 anomalies (6 records)
        "TA0": {
            "2006-12-28": {"high_open": True, "low_open": False, "high_close": False, "low_close": False},
            "2007-03-27": {"high_open": True, "low_open": False, "high_close": False, "low_close": False},
            "2007-05-11": {"high_open": True, "low_open": False, "high_close": False, "low_close": False},
            "2007-05-28": {"high_open": False, "low_open": True, "high_close": False, "low_close": False},
            "2007-07-10": {"high_open": True, "low_open": False, "high_close": False, "low_close": False},
            "2008-10-07": {"high_open": False, "low_open": False, "high_close": True, "low_close": False},
        },
        # L0 anomaly (1 record)
        "L0": {
            "2007-07-31": {"high_open": True, "low_open": False, "high_close": False, "low_close": False},
        },
        # HC0 anomaly (1 record)
        "HC0": {
            "2021-12-30": {"high_open": False, "low_open": False, "high_close": False, "low_close": True},
        },
    }
    
    # Identify records to delete
    records_to_delete = []
    for symbol_err, errors in confirmed_errors.items():
        if symbol_err != symbol:
            continue
        for date, error_types in errors.items():
            # Strict symbol matching - use the symbol parameter passed to the function
            if "symbol" in data.columns:
                symbol_match = data["symbol"] == symbol
            else:
                # If no symbol column exists, we can't filter by symbol, so skip this symbol entirely
                symbol_match = pd.Series(False, index=data.index)
            
            date_match = normalized_dates == date
            
            # Get OHLC values for this record
            open_vals = pd.to_numeric(data["open"], errors="coerce")
            high_vals = pd.to_numeric(data["high"], errors="coerce")
            low_vals = pd.to_numeric(data["low"], errors="coerce")
            close_vals = pd.to_numeric(data["close"], errors="coerce")
            
            # Check if all error conditions match
            high_open_match = error_types["high_open"]
            low_open_match = error_types["low_open"]
            high_close_match = error_types["high_close"]
            low_close_match = error_types["low_close"]
            
            if (symbol_match & date_match).any():
                # For each matching record, check the actual OHLC values
                for idx in data.index:
                    if (normalized_dates[idx] == date and
                            ("symbol" not in data.columns or data.at[idx, "symbol"] == symbol)):
                        open_val = open_vals[idx]
                        high_val = high_vals[idx]
                        low_val = low_vals[idx]
                        close_val = close_vals[idx]
                        
                        actual_high_open = high_val < open_val
                        actual_low_open = low_val > open_val
                        actual_high_close = high_val < close_val
                        actual_low_close = low_val > close_val
                        
                        if (actual_high_open == high_open_match and
                                actual_low_open == low_open_match and
                                actual_high_close == high_close_match and
                                actual_low_close == low_close_match):
                            records_to_delete.append(idx)
    
    # Remove confirmed error records
    if records_to_delete:
        data = data.drop(index=records_to_delete).reset_index(drop=True)
        logger.warning(f"已删除 {len(records_to_delete)} 条确认的 OHLC 异常记录")
    
    # Recalculate invalid mask after removing confirmed errors
    dates = pd.to_datetime(data["date"], errors="coerce")
    if dates.isna().any():
        bad_rows = data.index[dates.isna()].tolist()[:10]
        raise ValueError(f"存在无效交易日期，行索引示例：{bad_rows}")
    normalized_dates = dates.dt.strftime("%Y-%m-%d")
    invalid = (
        (data["high"] < data[["open", "close", "low"]].max(axis=1))
        | (data["low"] > data[["open", "close", "high"]].min(axis=1))
    )
    
    # Mark remaining known anomalies
    known_bad_dates = {"2011-01-03", "2020-08-06"}
    known_bad = normalized_dates.isin(known_bad_dates) & invalid
    unexpected_bad = invalid & ~known_bad

    # Volume and open interest must be non-negative finite values
    for column in ["volume", "hold"]:
        values = pd.to_numeric(data[column], errors="coerce")
        if values.isna().any():
            raise ValueError(f"字段 {column} 存在缺失或非数值")
        if not np.isfinite(values).all():
            raise ValueError(f"字段 {column} 存在非有限数值")
        if (values < 0).any():
            raise ValueError(f"字段 {column} 存在负值")
        data[column] = values

    # Volume and open interest are not allowed to be missing; return standardized copy after processing
    data["quality_status"] = "valid"
    data.loc[known_bad, "quality_status"] = "invalid_ohlc"
    data.loc[unexpected_bad, "quality_status"] = "invalid_ohlc"
    if unexpected_bad.any():
        bad_dates = normalized_dates[unexpected_bad].unique().tolist()[:10]
        logger.warning(
            "检测到 %d 条未知 OHLC 异常记录，已标记 invalid_ohlc，日期示例：%s",
            int(unexpected_bad.sum()), bad_dates,
        )

    data["date"] = normalized_dates
    return data


_jsonl_locks: dict[Path, threading.Lock] = {}
_jsonl_locks_guard = threading.Lock()


def _get_jsonl_lock(log_path: Path) -> threading.Lock:
    resolved = log_path.resolve()
    with _jsonl_locks_guard:
        lock = _jsonl_locks.get(resolved)
        if lock is None:
            lock = threading.Lock()
            _jsonl_locks[resolved] = lock
        return lock


def append_jsonl(records: list[dict], log_path: Path | None = None, key_fields: tuple[str, ...] = ("symbol", "datetime")) -> int:
    """Append records to a JSONL file with deduplication (atomic write).

    Write strategy: read existing content -> append new records -> write to temp file ->
    atomically replace the original file.
    Avoid leaving half-written broken JSON when the process crashes.

    Parameters:
        records: List of records to write
        log_path: Target JSONL file path, defaults to QUALITY_LOG
        key_fields: Tuple of field names used for deduplication, defaults to ("symbol", "datetime")

    Returns:
        Number of records actually written.
    """
    if not records:
        return 0

    log_path = Path(log_path) if log_path else QUALITY_LOG
    lock = _get_jsonl_lock(log_path)

    with lock:
        log_path.parent.mkdir(parents=True, exist_ok=True)

        existing = set()
        existing_lines = []
        if log_path.exists():
            with log_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    existing_lines.append(line)
                    try:
                        item = json.loads(line)
                        existing.add(tuple(item.get(k) for k in key_fields))
                    except json.JSONDecodeError:
                        # Damaged line kept, not used for deduplication key judgment
                        pass

        new_lines = []
        for item in records:
            key = tuple(item.get(k) for k in key_fields)
            if key in existing:
                continue
            existing.add(key)
            new_lines.append(json.dumps(item, ensure_ascii=False, allow_nan=False))

        if not new_lines:
            return 0

        all_lines = existing_lines + new_lines
        temp_path = log_path.with_name(log_path.name + ".tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as f:
                for line in all_lines:
                    f.write(line + "\n")
            temp_path.replace(log_path)
        except Exception:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass
            raise
        return len(new_lines)


def records_to_csv(records: list[dict], csv_path: Path) -> int:
    """
    Write a list of records directly to a UTF-8 BOM encoded CSV file.
    Column names are the union of all record fields, preserving original field names
    and first occurrence order.
    Write to a temp file, atomically replace after success, avoiding half-finished output.
    """
    if not records:
        # No records: do not modify existing file, return 0 directly to avoid accidentally clearing old data
        if not csv_path.exists():
            return 0
        return 0

    fieldnames = []
    seen = set()
    for item in records:
        for key in item.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)

    temp_path = csv_path.with_name(csv_path.name + ".tmp")
    try:
        with temp_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=fieldnames, extrasaction="ignore"
            )
            writer.writeheader()
            for item in records:
                cleaned = {
                    k: (v.strip() if isinstance(v, str) else v)
                    for k, v in item.items()
                }
                writer.writerow(cleaned)
        temp_path.replace(csv_path)
    except Exception:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass
        raise
    return len(records)


def csv_to_records(csv_path: Path) -> list[dict]:
    """Read records from a CSV file. Return an empty list if the file does not exist."""
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [row for row in reader]

def update_daily_bars(df: pd.DataFrame, symbol: str = "V0") -> int:
    """
    Historical daily bars use (symbol, trading_date) as the unique key.
    Merge, deduplicate after reading from the historical interface, and write back to CSV as a whole.
    """
    records_by_key = {}

    daily_csv = get_daily_csv(symbol)
    if daily_csv.exists():
        old_records = csv_to_records(daily_csv)
        for item in old_records:
            if not isinstance(item, dict) or not item.get("symbol") or not item.get("trading_date"):
                raise ValueError("日线历史文件存在缺少 symbol/trading_date 的记录")
            key = (item["symbol"], item["trading_date"])
            records_by_key[key] = item

    collected_at_str = datetime.now(TZ).isoformat()

    for _, row in df.iterrows():
        trading_date = pd.to_datetime(row["date"]).date().isoformat()
        settle_raw = number(row.get("settle"))
        record = {
            "symbol": symbol,
            "name": SYMBOL_NAME_MAP.get(symbol, "PVC连续"),
            "trading_date": trading_date,
            "open": number(row.get("open")),
            "high": number(row.get("high")),
            "low": number(row.get("low")),
            "close": number(row.get("close")),
            "volume": clean(row.get("volume")),
            "open_interest": clean(row.get("hold")),
            "settle_raw": settle_raw,
            "settle": None if settle_raw == 0 else settle_raw,
            "quality_status": clean(row.get("quality_status")) or "valid",
            "source": "AKShare futures_zh_daily_sina",
            "collected_at": collected_at_str,
        }
        records_by_key[(symbol, trading_date)] = record

    result = sorted(
        records_by_key.values(),
        key=lambda item: (item["symbol"], item["trading_date"]),
    )
    count = records_to_csv(result, daily_csv)
    return count


def validate_minute_bars(df: pd.DataFrame) -> pd.DataFrame:
    required = {"datetime", "open", "high", "low", "close", "volume", "hold"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"分钟数据缺少字段：{sorted(missing)}")
    if df.empty:
        raise ValueError("分钟数据为空")

    data = df[list(required)].copy()
    data["datetime"] = pd.to_datetime(data["datetime"], errors="coerce")
    if data["datetime"].isna().any():
        raise ValueError("分钟数据存在无效时间戳")
    data["datetime"] = data["datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")

    if data["datetime"].duplicated().any():
        raise ValueError("本次分钟数据存在重复时间戳")

    for col in ["open", "high", "low", "close", "volume", "hold"]:
        data[col] = pd.to_numeric(data[col], errors="coerce")
        if data[col].isna().any() or not np.isfinite(data[col]).all():
            raise ValueError(f"分钟字段 {col} 存在无效数值")

    price_cols = ["open", "high", "low", "close"]
    if (data[price_cols] <= 0).any().any():
        raise ValueError("分钟 OHLC 存在非正数")
    if (data["high"] < data[["open", "low", "close"]].max(axis=1)).any():
        raise ValueError("分钟数据最高价关系异常")
    if (data["low"] > data[["open", "high", "close"]].min(axis=1)).any():
        raise ValueError("分钟数据最低价关系异常")
    if (data[["volume", "hold"]] < 0).any().any():
        raise ValueError("分钟成交量或持仓量为负数")

    return data.sort_values("datetime").reset_index(drop=True)


def parse_market_datetime(value: Any, tz: ZoneInfo = TZ) -> pd.Timestamp:
    """
    Unify quote minute timestamps as timezone-aware pandas Timestamps.
    Input without timezone is localized to tz; input with timezone is converted to tz,
    avoiding cross-timezone confusion.
    Returns pd.NaT if unparseable.
    """
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return pd.NaT
    ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize(tz)
    else:
        ts = ts.tz_convert(tz)
    return ts

def separate_future_timestamps(
    data: pd.DataFrame,
    symbol: str,
    collected_at: datetime,
    log_path: Optional[Path] = None,
) -> pd.DataFrame:
    """
    Based on timezone-aware collection time (collected_at), identify records whose
    quote time is later than collection time plus tolerance (FUTURE_TIMESTAMP_TOLERANCE).

    Behavior:
    - Future-time records are marked issue="future_timestamp", not written to the valid
      minute bar dataset; their time, symbol, OHLC, volume, open interest, and collection
      time are logged to the quality log (output/minute_data_quality.jsonl).
      The same (symbol, datetime) record is not written repeatedly.
    - The timestamp itself is not modified (e.g., not changing 09:01 to 21:01).
    - Time comparison is unified in Asia/Shanghai timezone.
    - Returns a DataFrame containing only normal records (sorted by datetime, index reset).
    """
    if data.empty:
        return data.copy()

    threshold = pd.Timestamp(collected_at) + FUTURE_TIMESTAMP_TOLERANCE
    future_records = []
    keep_mask = []

    for _, row in data.iterrows():
        bar_dt = parse_market_datetime(row["datetime"])
        if pd.isna(bar_dt):
            # Unparseable timestamps are not judged in this function, kept to maintain original behavior.
            keep_mask.append(True)
            continue
        if bar_dt > threshold:
            future_records.append({
                "symbol": symbol,
                "datetime": row["datetime"],
                "open": number(row["open"]),
                "high": number(row["high"]),
                "low": number(row["low"]),
                "close": number(row["close"]),
                "volume": number(row["volume"]),
                "open_interest": number(row["hold"]),
                "collected_at": collected_at.isoformat(),
                "issue": "future_timestamp",
            })
            keep_mask.append(False)
        else:
            keep_mask.append(True)

    if future_records:
        append_jsonl(future_records, log_path)

    valid = data[keep_mask].copy()
    return valid.sort_values("datetime").reset_index(drop=True)


def filter_future_anomalies(
    records: list[dict], log_path: Optional[Path] = None
) -> list[dict]:
    """
    Validate the merged dataset by each record's own collected_at.

    Judgment rule (unified in Asia/Shanghai timezone):
        record.datetime > record.collected_at + FUTURE_TIMESTAMP_TOLERANCE
    Records matching this are considered future-timestamp anomalies, removed from the
    final dataset, and logged to the quality control log.

    This step runs after merging historical data, used to clean up anomaly records
    remaining in old files that were not filtered historically, preventing old file
    anomalies from being retained again.
    - Do not modify the original time of anomaly records.
    - The same (symbol, datetime) anomaly record is not written repeatedly to the log.
    - Records missing available time pairs (datetime/collected_at) are kept as-is.
    """
    kept = []
    anomalies = []
    for item in records:
        bar_dt = parse_market_datetime(item.get("datetime"))
        coll_dt = parse_market_datetime(item.get("collected_at"))
        if pd.isna(bar_dt) or pd.isna(coll_dt):
            kept.append(item)
            continue
        if bar_dt > coll_dt + FUTURE_TIMESTAMP_TOLERANCE:
            anomalies.append({
                "symbol": item.get("symbol"),
                "datetime": item.get("datetime"),
                "open": item.get("open"),
                "high": item.get("high"),
                "low": item.get("low"),
                "close": item.get("close"),
                "volume": item.get("volume"),
                "open_interest": item.get("open_interest"),
                "collected_at": item.get("collected_at"),
                "issue": "future_timestamp",
            })
        else:
            kept.append(item)

    if anomalies:
        append_jsonl(anomalies, log_path)
    return kept


def update_minute_bars(symbol: str, df: pd.DataFrame) -> tuple[int, int]:
    data = validate_minute_bars(df)
    collected_at = datetime.now(TZ)
    data = separate_future_timestamps(data, symbol, collected_at)
    minute_csv = get_minute_csv(symbol)
    old_records = []

    if minute_csv.exists():
        old_records = csv_to_records(minute_csv)

    records = {}
    for item in old_records:
        if not isinstance(item, dict) or not item.get("symbol") or not item.get("datetime"):
            raise ValueError("分钟历史文件存在缺少 symbol/datetime 的记录")
        key = (item["symbol"], item["datetime"])
        if key in records:
            raise ValueError(f"分钟历史文件已有重复记录：{key}")
        records[key] = item

    collected_at_str = collected_at.isoformat()
    for _, row in data.iterrows():
        timestamp = row["datetime"]
        key = (symbol, timestamp)
        if key in records:
            # Old record keeps original collected_at, only update quote fields
            records[key].update({
                "open": number(row["open"]),
                "high": number(row["high"]),
                "low": number(row["low"]),
                "close": number(row["close"]),
                "volume": number(row["volume"]),
                "open_interest": number(row["hold"]),
                "source": "AKShare futures_zh_minute_sina",
                "name": SYMBOL_NAME_MAP.get(symbol, "PVC连续"),
            })
        else:
            records[key] = {
                "symbol": symbol,
                "name": SYMBOL_NAME_MAP.get(symbol, "PVC连续"),
                "datetime": timestamp,
                "open": number(row["open"]),
                "high": number(row["high"]),
                "low": number(row["low"]),
                "close": number(row["close"]),
                "volume": number(row["volume"]),
                "open_interest": number(row["hold"]),
                "source": "AKShare futures_zh_minute_sina",
                "collected_at": collected_at_str,
            }

    merged = sorted(records.values(), key=lambda x: (x["symbol"], x["datetime"]))
    merged = filter_future_anomalies(merged)
    count = records_to_csv(merged, minute_csv)
    return len(data), count


class QualityValidationError(ValueError):
    """Raised when quality validation removes all candidate daily rows."""


def _normalize_daily_settle(value):
    n = number(value)
    return None if n == 0 else n


def _get_field(row, key):
    try:
        return row.get(key)
    except AttributeError:
        return row[key] if key in row else None


def _daily_record_changed(existing, new_row) -> bool:
    old = (
        number(existing.get("open")), number(existing.get("high")),
        number(existing.get("low")), number(existing.get("close")),
        number(existing.get("volume")), number(existing.get("open_interest")),
        _normalize_daily_settle(existing.get("settle")),
        existing.get("quality_status") or "valid",
    )
    new = (
        number(_get_field(new_row, "open")), number(_get_field(new_row, "high")),
        number(_get_field(new_row, "low")), number(_get_field(new_row, "close")),
        number(_get_field(new_row, "volume")), number(_get_field(new_row, "hold")),
        _normalize_daily_settle(_get_field(new_row, "settle")),
        clean(_get_field(new_row, "quality_status")) or "valid",
    )
    return old != new


def _index_record_changed(existing, new_row) -> bool:
    old = (
        number(existing.get("close")), number(existing.get("settle")),
        number(existing.get("change")), number(existing.get("pct_change")),
        existing.get("quality_status") or "valid",
    )
    new = (
        number(_get_field(new_row, "close")), number(_get_field(new_row, "settle")),
        number(_get_field(new_row, "change")), number(_get_field(new_row, "pct_change")),
        clean(_get_field(new_row, "quality_status")) or "valid",
    )
    return old != new


def is_after_day_session_close() -> bool:
    """After day session close, complete daily bars can be collected.

    DCE day session trading time: 09:00-15:00.
    Night session: 21:00-23:00 (next trading day).
    Daily bars are collected during 15:00-21:00 only; night session (21:00-23:00)
    is skipped to avoid incomplete data.
    Returns False on weekend closure and night session (21:00-23:00).
    """
    now = datetime.now(TZ)
    weekday = now.weekday()  # 0=Mon … 5=Sat, 6=Sun
    hhmm = int(now.strftime("%H%M"))

    if weekday >= 5:  # Weekend closure
        return False
    # Weekdays: collect daily bars only between 15:00 and 21:00
    # Night session (21:00-23:00) is skipped; data belongs to next trading day
    return 1500 <= hhmm < 2100


def is_after_market_close() -> bool:
    """Determine whether the current Beijing time is past the PVC trading day close.

    Consistent with is_after_day_session_close(): complete daily bars can be collected
    after day session at 15:00.
    No longer distinguish 23:00 night session close; night session is assigned to the
    next trading day, handled by infer_trading_date for date inference.
    """
    return is_after_day_session_close()

def fetch_and_update_daily_bars(symbol: str, session_label: str) -> Optional[int]:
    """
    获取并更新日线行情。

    增量采集策略：
    - 先读取本地已有数据的最新交易日期
    - 调用 AKShare 接口获取全量日线
    - 只保留比本地最新日期更新的记录
    - 如果没有新数据，直接返回 0，不写入文件

    Parameters:
        symbol: 合约代码，e.g. "V0", "TA0", "H11061"（中证商品期货指数）
        session_label: 会话标签，e.g. "日 session", "完整"

    Returns:
        新增记录数，失败返回 None
    """
    if symbol == "H11061":
        try:
            daily_df = _retryable_call(ak.futures_index_ccidx, symbol='中证商品期货指数')
            if daily_df is None or daily_df.empty:
                raise RuntimeError(f"{symbol} 指数数据为空，停止更新。")

            normalized = normalize_index_daily_bars(daily_df)
            index_csv = OUT / f"{symbol}_index_daily.csv"
            existing_records = csv_to_records(index_csv) if index_csv.exists() else []
            existing_by_date = {}
            last_trading_date = None
            if existing_records:
                for item in existing_records:
                    if item.get("trading_date"):
                        existing_by_date[str(item["trading_date"])] = item
                if existing_by_date:
                    last_trading_date = max(existing_by_date)
            if last_trading_date is not None:
                candidate = normalized[normalized["trading_date"] >= last_trading_date]
            else:
                candidate = normalized
            if candidate is None or candidate.empty:
                return 0
            validated = validate_index_daily_bars(candidate, symbol=symbol)
            if validated.empty:
                raise QualityValidationError(f"{symbol} 质量校验移除全部候选记录")
            changed_rows = []
            for _, row in validated.iterrows():
                key = str(row["trading_date"])
                existing = existing_by_date.get(key)
                if existing is None or _index_record_changed(existing, row):
                    changed_rows.append(row)
            if not changed_rows:
                logger.info(f"日线 {symbol}（{session_label}）：无变化，跳过写入")
                return 0
            changed_df = pd.DataFrame(changed_rows)
            update_index_daily_bars(changed_df, symbol=symbol)
            logger.info(
                f"日线 {symbol}（{session_label}）：本次变更 {len(changed_rows)} 条；CSV output/{symbol}_index_daily.csv",
            )
            return len(changed_rows)

        except Exception as e:
            logger.error(
                f"日线 {symbol}（{session_label}）：ERROR - 指数数据异常，类型={type(e).__name__}，消息={e}",
            )
            raise

    existing_csv = get_daily_csv(symbol)
    last_trading_date = None
    existing_records = csv_to_records(existing_csv) if existing_csv.exists() else []
    existing_by_date = {}
    if existing_records:
        for item in existing_records:
            if item.get("trading_date"):
                existing_by_date[str(item["trading_date"])] = item
        if existing_by_date:
            last_trading_date = max(existing_by_date)

    daily_df = _retryable_call(ak.futures_zh_daily_sina, symbol=symbol)
    if daily_df is None or daily_df.empty:
        raise RuntimeError(f"{symbol} 日线数据为空，停止更新。")

    required = {"date", "open", "high", "low", "close", "volume", "hold", "settle"}
    missing = required - set(daily_df.columns)
    if missing:
        raise ValueError(f"{symbol} 日线数据缺少字段：{sorted(missing)}")

    daily_df = daily_df.copy()
    daily_df['date'] = pd.to_datetime(daily_df['date']).dt.strftime('%Y-%m-%d')

    if last_trading_date is not None:
        candidate_df = daily_df[daily_df['date'] >= last_trading_date]
    else:
        candidate_df = daily_df
    if candidate_df.empty:
        return 0

    validated = validate_daily_bars(candidate_df, symbol=symbol)
    if validated.empty:
        raise QualityValidationError(f"{symbol} 质量校验移除全部候选记录")
    changed_rows = []
    for _, row in validated.iterrows():
        key = str(row["date"])
        existing = existing_by_date.get(key)
        if existing is None or _daily_record_changed(existing, row):
            changed_rows.append(row)
    if not changed_rows:
        logger.info(
            f"日线 {symbol}（{session_label}）：无变化（本地最新：{last_trading_date}），跳过采集"
        )
        return 0
    changed_df = pd.DataFrame(changed_rows)
    update_daily_bars(changed_df, symbol=symbol)
    logger.info(
        f"日线 {symbol}（{session_label}）：本次变更 {len(changed_rows)} 条；CSV {get_daily_csv(symbol)}",
    )
    return len(changed_rows)


class TaskResult:
    """Result of one collection task (minute/daily for one symbol).

    Parameters:
        task_type: "minute" or "daily"
        symbol: contract/index code, e.g. "V0"
        status: "success" (ran or skipped) or "failed"
        error_type: exception class name, if failed
        error_message: exception message, if failed
    """

    def __init__(self, task_type, symbol, status, error_type=None, error_message=None, outcome=None):
        self.task_type = task_type
        self.symbol = symbol
        self.status = status
        self.error_type = error_type
        self.error_message = error_message
        if status == "failed":
            self.outcome = "failed"
        elif outcome in {"no_new_data", "skipped"}:
            self.outcome = outcome
        else:
            self.outcome = "success"

    @property
    def ok(self) -> bool:
        return self.status != "failed"

    def __repr__(self):
        if self.ok:
            return f"<TaskResult {self.task_type} {self.symbol}: success>"
        return (
            f"<TaskResult {self.task_type} {self.symbol}: failed "
            f"{self.error_type}: {self.error_message}>"
        )


def _run_minute_bars(symbol: str) -> TaskResult:
    """Run minute-bar collection for one symbol on every trigger."""
    try:
        minute_df = _retryable_call(ak.futures_zh_minute_sina, symbol=symbol, period="1")
        if minute_df is None or minute_df.empty:
            raise RuntimeError(f"{symbol} 分钟数据为空，停止更新。")
        updated, total = update_minute_bars(symbol, minute_df)
        logger.info(
            "分钟线 %s：ACTIVE，本次校验 %d 条；文件累计 %d 条；CSV %s",
            symbol, updated, total, get_minute_csv(symbol),
        )
        return TaskResult("minute", symbol, "success", outcome="success")
    except ValueError as exc:
        if "Length mismatch" in str(exc):
            logger.error(
                "分钟线 %s：UNKNOWN - 接口返回 Length mismatch，无法确认挂牌状态，类型=%s，消息=%s，允许后续重试",
                symbol, type(exc).__name__, exc,
            )
        else:
            logger.error(
                "分钟线 %s：ERROR - 数据格式异常，类型=%s，消息=%s，允许后续重试",
                symbol, type(exc).__name__, exc,
            )
        return TaskResult("minute", symbol, "failed", type(exc).__name__, str(exc))
    except Exception as exc:
        logger.error(
            "分钟线 %s：ERROR - 接口异常，类型=%s，消息=%s，允许后续重试",
            symbol, type(exc).__name__, exc,
        )
        return TaskResult("minute", symbol, "failed", type(exc).__name__, str(exc))


def _run_daily_bars(symbol: str) -> TaskResult:
    """Run daily-bar collection for one symbol on every trigger."""
    try:
        changed = fetch_and_update_daily_bars(symbol, "完整")
        logger.info(
            "日线 %s：ACTIVE，采集成功；CSV %s",
            symbol,
            f"output/{symbol}_index_daily.csv"
            if symbol == "H11061"
            else get_daily_csv(symbol),
        )
        if changed == 0:
            return TaskResult("daily", symbol, "success", outcome="no_new_data")
        return TaskResult("daily", symbol, "success", outcome="success")
    except ValueError as exc:
        if "Length mismatch" in str(exc):
            logger.error(
                "日线 %s：UNKNOWN - 接口返回 Length mismatch，无法确认挂牌状态，类型=%s，消息=%s，允许后续重试",
                symbol, type(exc).__name__, exc,
            )
        else:
            logger.error(
                "日线 %s：ERROR - 数据格式异常，类型=%s，消息=%s，允许后续重试",
                symbol, type(exc).__name__, exc,
            )
        return TaskResult("daily", symbol, "failed", type(exc).__name__, str(exc))
    except Exception as exc:
        logger.error(
            "日线 %s：ERROR - 接口异常，类型=%s，消息=%s，允许后续重试",
            symbol, type(exc).__name__, exc,
        )
        return TaskResult("daily", symbol, "failed", type(exc).__name__, str(exc))


def run_collection(active_contracts=None) -> int:
    """Run all collection tasks in parallel and summarize failures.

    Returns 0 if every task succeeded (or was skipped), 1 otherwise.
    ``None`` selects the default ``ACTIVE_CONTRACTS``; ``[]`` submits no tasks.
    """
    contracts = ACTIVE_CONTRACTS if active_contracts is None else active_contracts

    # Two data streams are independent, execute in parallel
    tasks = []
    for sym in contracts:
        # 商品期货支持分钟线，跳过指数合约 H11061
        if sym != "H11061":
            tasks.append(("minute", sym))
        tasks.append(("daily", sym))

    if not tasks:
        logger.info("采集任务为空，未提交任何任务，退出码 0")
        return 0

    results = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        future_map = {}
        for task_type, sym in tasks:
            fn = _run_minute_bars if task_type == "minute" else _run_daily_bars
            future_map[executor.submit(fn, sym)] = (task_type, sym)

        for future in as_completed(future_map):
            task_type, sym = future_map[future]
            try:
                result = future.result()
            except Exception as exc:  # 未捕获异常兜底
                logger.error(
                    "调度器捕获未处理异常：task=%s symbol=%s 类型=%s，消息=%s",
                    task_type, sym, type(exc).__name__, exc,
                )
                result = TaskResult(
                    task_type, sym, "failed", type(exc).__name__, str(exc)
                )
            if result is None:
                logger.error(
                    "调度器检测包装函数返回 None：task=%s symbol=%s",
                    task_type, sym,
                )
                result = TaskResult(
                    task_type, sym, "failed", "NoneResult",
                    "包装函数意外返回 None",
                )
            results.append(result)

    # Summary: log every failure, non-zero exit if any
    failed = [r for r in results if r.outcome == "failed"]
    for r in failed:
        logger.error(
            "采集失败汇总：task=%s symbol=%s 类型=%s，原因=%s",
            r.task_type, r.symbol, r.error_type, r.error_message,
        )
    success_count = sum(r.outcome == "success" for r in results)
    no_new_count = sum(r.outcome == "no_new_data" for r in results)
    skipped_count = sum(r.outcome == "skipped" for r in results)
    failed_count = sum(r.outcome == "failed" for r in results)
    logger.info(
        "采集汇总：总任务 %d，成功 %d，无新数据 %d，跳过 %d，失败 %d",
        len(results), success_count, no_new_count, skipped_count, failed_count,
    )
    if failed_count:
        logger.error("采集任务存在失败，退出码 1")
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    OUT.mkdir(parents=True, exist_ok=True)
    raise SystemExit(run_collection())
