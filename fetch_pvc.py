#!/usr/bin/env python3
"""Collect PVC futures contract real-time snapshots and historical daily bars."""
from __future__ import annotations

import csv
import json
import logging
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

import akshare as ak
import numpy as np
import pandas as pd
import requests

logger = logging.getLogger(__name__)


def _retryable_call(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    *args,
    **kwargs,
):
    """Retry call with exponential backoff.

    Only retry on requests.RequestException (network timeout, HTTP errors, etc.);
    ValueError, RuntimeError and other data format exceptions are raised directly
    without retry.

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
        except requests.RequestException as exc:
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
}

# 需主动采集的合约列表（九个商品期货主力连续）
# 只有列在此列表中的合约才会被主循环提交采集任务
ACTIVE_CONTRACTS = ["V0", "TA0", "MA0", "PP0", "L0", "SA0", "FG0", "RB0", "HC0"]


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


def validate_daily_bars(df: pd.DataFrame) -> pd.DataFrame:
    """Validate historical daily bars: dates, values, and OHLC logic; refuse writing on failure."""
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

    # Explicitly mark only the two verified historical source data anomalies, do not modify original prices.
    known_bad_dates = {"2011-01-03", "2020-08-06"}
    known_bad = normalized_dates.isin(known_bad_dates) & invalid
    unexpected_bad = invalid & ~known_bad

    if unexpected_bad.any():
        examples = normalized_dates[unexpected_bad].tolist()[:10]
        raise ValueError(f"发现未登记的 OHLC 异常，拒绝写入：{examples}")

    data["quality_status"] = "valid"
    data.loc[known_bad, "quality_status"] = "invalid_ohlc"

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
    data["date"] = normalized_dates
    return data

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


def is_after_day_session_close() -> bool:
    """After day session close, complete daily bars can be collected.

    DCE day session trading time: 09:00-15:00.
    After day session close (15:00), the previous night session and today's day session
    data are ready, so complete daily bars for the current trading day can be collected
    (night session is assigned to the next trading day, does not affect today).
    Returns False on weekend closure.
    """
    now = datetime.now(TZ)
    weekday = now.weekday()  # 0=Mon … 5=Sat, 6=Sun
    hhmm = int(now.strftime("%H%M"))

    if weekday >= 5:  # Weekend closure
        return False
    # Weekdays: complete daily bars can be collected after day session at 15:00
    return hhmm >= 1500


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
    Fetch and update daily bar data for the specified symbol.

    Parameters:
        symbol: Contract code, e.g., "V0", "TA0"
        session_label: Log label, e.g., "day session", "complete"

    Returns:
        Number of updated records, returns None on failure.
    """
    daily_df = _retryable_call(ak.futures_zh_daily_sina, symbol=symbol)
    if daily_df is None or daily_df.empty:
        raise RuntimeError(f"{symbol} 日线数据为空，停止更新。")

    required = {"date", "open", "high", "low", "close", "volume", "hold", "settle"}
    missing = required - set(daily_df.columns)
    if missing:
        raise ValueError(f"{symbol} 日线数据缺少字段：{sorted(missing)}")

    validated = validate_daily_bars(daily_df)
    count = update_daily_bars(validated, symbol=symbol)
    logger.info(
        "日线 %s（%s）：本次校验 %d 条；更新结果 %d；CSV %s",
        symbol, session_label, len(validated), count, get_daily_csv(symbol),
    )
    return count


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    OUT.mkdir(parents=True, exist_ok=True)

    def _run_minute_bars(symbol: str):
        try:
            minute_df = _retryable_call(ak.futures_zh_minute_sina, symbol=symbol, period="1")
            if minute_df is None or minute_df.empty:
                raise RuntimeError(f"{symbol} 分钟数据为空，停止更新。")
            updated, total = update_minute_bars(symbol, minute_df)
            logger.info(
                "分钟线 %s：ACTIVE，本次校验 %d 条；文件累计 %d 条；CSV %s",
                symbol, updated, total, get_minute_csv(symbol),
            )
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
        except Exception as exc:
            logger.error(
                "分钟线 %s：ERROR - 接口异常，类型=%s，消息=%s，允许后续重试",
                symbol, type(exc).__name__, exc,
            )

    def _run_daily_bars(symbol: str):
        try:
            if is_after_market_close():
                fetch_and_update_daily_bars(symbol, "完整")
                logger.info(
                    "日线 %s：ACTIVE，采集成功；CSV %s",
                    symbol, get_daily_csv(symbol),
                )
            else:
                logger.info("日线 %s：未到采集时间，跳过", symbol)
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
        except Exception as exc:
            logger.error(
                "日线 %s：ERROR - 接口异常，类型=%s，消息=%s，允许后续重试",
                symbol, type(exc).__name__, exc,
            )

    # Two data streams are independent, execute in parallel; each symbol's each stream is an independent task
    tasks = []
    for sym in ACTIVE_CONTRACTS:
        tasks.append(("minute", sym, _run_minute_bars))
        tasks.append(("daily", sym, _run_daily_bars))

    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = [executor.submit(fn, sym) for _, sym, fn in tasks]
        for future in as_completed(futures):
            future.result()  # Raise exceptions possibly thrown within tasks (already caught in each function, just confirm completion here)
