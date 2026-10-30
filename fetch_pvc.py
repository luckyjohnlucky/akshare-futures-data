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
    "V2701": "PVC 2701",
}


def get_daily_csv(symbol: str) -> Path:
    """Return the daily CSV path for the given symbol."""
    return OUT / f"{symbol}_daily_bars.csv"


def get_minute_csv(symbol: str) -> Path:
    """Return the minute CSV path for the given symbol."""
    return OUT / f"{symbol}_minute_bars.csv"


def get_snapshot_file(symbol: str) -> Path:
    """Return the real-time snapshot JSONL path for the given symbol."""
    return OUT / f"{symbol}_realtime_snapshots.jsonl"


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


def infer_trading_date(source_date: str, source_time: str) -> str:
    """
    Initial trading date inference:
    Night sessions at 21:00 and later are assigned to the next calendar day.

    Note: Not yet connected to DCE trading calendar; results need verification.
    source_date/source_time must be strictly validated by the caller;
    this function does not fall back to the local date.
    """
    day = datetime.strptime(source_date, "%Y-%m-%d").date()

    source_time_str = str(source_time).strip()
    try:
        hhmmss = int(source_time_str)
    except (TypeError, ValueError):
        hhmmss = -1

    if 210000 <= hhmmss <= 235959:
        day += timedelta(days=1)

    return day.isoformat()



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


def fetch_sina_spot(symbol: str = "V0") -> Optional[dict]:
    """
    Fetch raw field data for PVC continuous contract (V0) real-time quote from Sina Finance API.

    Call Sina HTTP interface directly instead of akshare.futures_zh_spot
    (the latter has a ValueError defect due to column count mismatch).

    Returns a dictionary of fields; returns None on failure.
    """
    url = f"https://hq.sinajs.cn/list=nf_{symbol}"
    headers = {
        "Referer": "https://finance.sina.com.cn/",
        "User-Agent": "Mozilla/5.0",
    }

    def _fetch():
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        match = re.search(r'"([^"]*)"', response.text)
        if not match:
            raise ValueError("新浪响应中未找到行情数据")

        fields = match.group(1).split(",")
        if len(fields) < 18:
            raise ValueError(f"新浪行情字段数不足（{len(fields)} < 18）")

        return {
            "name": fields[0].strip(),
            "time": fields[1].strip(),
            "open": fields[2].strip(),
            "high": fields[3].strip(),
            "low": fields[4].strip(),
            "last_close": fields[5].strip(),
            "bid_price": fields[6].strip(),
            "ask_price": fields[7].strip(),
            "current_price": fields[8].strip(),
            "avg_price": fields[9].strip(),
            "last_settle_price": fields[10].strip(),
            "buy_vol": fields[11].strip(),
            "sell_vol": fields[12].strip(),
            "open_interest": fields[13].strip(),
            "volume": fields[14].strip(),
            "contract_code": fields[15].strip(),
            "exchange": fields[16].strip(),
            "date": fields[17].strip(),
        }

    try:
        return _retryable_call(_fetch)
    except Exception as exc:
        logger.error("获取新浪实时行情失败：%s", exc)
        return None


def _validate_source_date(value: Any) -> Optional[str]:
    """Strictly validate source date: must be YYYY-MM-DD and a valid calendar date; otherwise return None."""
    if value is None:
        return None
    s = str(value).strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return None
    try:
        datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None
    return s


def _validate_source_time(value: Any) -> Optional[str]:
    """Strictly validate source time: must be HHMMSS and valid hours/minutes/seconds; otherwise return None."""
    if value is None:
        return None
    s = str(value).strip()
    if not re.fullmatch(r"\d{6}", s):
        return None
    hh = int(s[0:2])
    mm = int(s[2:4])
    ss = int(s[4:6])
    if hh > 23 or mm > 59 or ss > 59:
        return None
    return s


def collect_realtime_snapshot(symbol: str = "V0") -> Optional[dict]:
    """
    Get PVC continuous contract real-time snapshot, independent of historical CSV.

    Convention:
    - source_date / source_time come from the data source itself (Sina API), not confusing
      collection time with quote time.
    - collected_at records the actual collection time.
    - Volume and open interest from the data source are saved as-is.
    - Saved to output/{symbol}_realtime_snapshots.jsonl.
    - Returns the saved record; returns None on collection failure.
    """
    spot = fetch_sina_spot(symbol=symbol)
    if spot is None:
        logger.error("实时快照 %s 采集失败，未获取到行情数据", symbol)
        return None

    collected_at = datetime.now(TZ)
    source_date = _validate_source_date(spot.get("date"))
    source_time = _validate_source_time(spot.get("time"))

    if source_date is None:
        logger.error("无效的源日期（source_date=%r），%s 不写入快照", spot.get("date"), symbol)
        return None
    if source_time is None:
        logger.error("无效的源时间（source_time=%r），%s 不写入快照", spot.get("time"), symbol)
        return None

    trading_date = infer_trading_date(source_date, source_time)

    is_night = 210000 <= int(source_time) <= 235959
    trading_date_method = (
        "inferred_next_calendar_day_for_night_session"
        if is_night else "calendar_day"
    )

    bar_datetime = (
        f"{source_date} {source_time[0:2]}:{source_time[2:4]}:{source_time[4:6]}"
    )

    last_close_raw = number(spot.get("last_close"))
    last_settle_raw = number(spot.get("last_settle_price"))
    vol = number(spot.get("volume"))

    record = {
        "symbol": symbol,
        "name": spot.get("name") or SYMBOL_NAME_MAP.get(symbol, "PVC连续"),
        "source": "Sina HTTP API",
        "source_date": source_date,
        "source_time": source_time,
        "bar_datetime": bar_datetime,
        "collected_at": collected_at.isoformat(),
        "trading_date": trading_date,
        "trading_date_method": trading_date_method,
        "trading_date_verified": False,
        "data_type": "realtime_snapshot",
        "open": number(spot.get("open")),
        "high": number(spot.get("high")),
        "low": number(spot.get("low")),
        "current_price": number(spot.get("current_price")),
        "bid_price": number(spot.get("bid_price")),
        "ask_price": number(spot.get("ask_price")),
        "last_close_raw": last_close_raw,
        "last_close": None if last_close_raw == 0 else last_close_raw,
        "last_settle_price_raw": last_settle_raw,
        "last_settle_price": None if last_settle_raw == 0 else last_settle_raw,
        "open_interest": number(spot.get("open_interest")),
        "volume": vol,
        "is_daily_bar_final": False,
    }
    append_jsonl([record], get_snapshot_file(symbol), key_fields=("symbol", "source_date", "source_time"))
    return record


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
        symbol: Contract code, e.g., "V0", "V2701"
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

    def _run_realtime_snapshot(symbol: str):
        try:
            snapshot = collect_realtime_snapshot(symbol=symbol)
            if snapshot:
                logger.info(
                    "实时快照 %s：已保存，行情时间 %s %s，采集时间 %s",
                    sym,
                    snapshot.get("source_date"),
                    snapshot.get("source_time"),
                    snapshot.get("collected_at"),
                )
            else:
                logger.error("实时快照 %s：采集失败，未获取到行情数据", sym)
        except Exception as exc:
            logger.error("实时快照 %s 采集失败（不影响其他流程）：%s", sym, exc)

    def _run_minute_bars(symbol: str):
        try:
            minute_df = _retryable_call(ak.futures_zh_minute_sina, symbol=symbol, period="1")
            if minute_df is None or minute_df.empty:
                raise RuntimeError(f"{symbol} 分钟数据为空，停止更新。")
            updated, total = update_minute_bars(symbol, minute_df)
            logger.info(
                "分钟线 %s：本次校验 %d 条；文件累计 %d 条；CSV %s",
                symbol, updated, total, get_minute_csv(symbol),
            )
        except Exception as exc:
            logger.error("分钟线 %s 更新失败：%s", symbol, exc)

    def _run_daily_bars(symbol: str):
        try:
            if is_after_market_close():
                fetch_and_update_daily_bars(symbol, "完整")
            else:
                logger.info("日线 %s：未到采集时间，跳过", symbol)
        except Exception as exc:
            logger.error("日线 %s 更新失败（不影响其他流程）：%s", symbol, exc)

    # Three data streams are independent, execute in parallel; each symbol's each stream is an independent task
    tasks = []
    for sym in ("V0", "V2701"):
        tasks.append(("realtime", sym, _run_realtime_snapshot))
        tasks.append(("minute", sym, _run_minute_bars))
        tasks.append(("daily", sym, _run_daily_bars))

    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = [executor.submit(fn, sym) for _, sym, fn in tasks]
        for future in as_completed(futures):
            future.result()  # Raise exceptions possibly thrown within tasks (already caught in each function, just confirm completion here)
