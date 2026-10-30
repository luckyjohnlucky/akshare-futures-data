#!/usr/bin/env python3
"""采集 PVC 连续合约实时快照与历史日线。"""
from __future__ import annotations

import csv
import json
import logging
import random
import re
import time
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
    """带指数退避的重试调用。

    参数:
        func: 要调用的函数
        max_retries: 最大重试次数
        base_delay: 基础延迟秒数
        max_delay: 最大延迟秒数
    """
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            return func(*args, **kwargs)
        except (requests.RequestException, ValueError, RuntimeError) as exc:
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
    """返回指定品种的日线 CSV 路径。"""
    return OUT / f"{symbol}_daily_bars.csv"


def get_minute_csv(symbol: str) -> Path:
    """返回指定品种的分钟线 CSV 路径。"""
    return OUT / f"{symbol}_minute_bars.csv"


def get_snapshot_file(symbol: str) -> Path:
    """返回指定品种的实时快照 JSONL 路径。"""
    return OUT / f"{symbol}_realtime_snapshots.jsonl"


QUALITY_LOG = OUT / "minute_data_quality.jsonl"
FUTURE_TIMESTAMP_TOLERANCE = timedelta(minutes=1)


def clean(value: Any) -> Any:
    """将 Pandas/Numpy 值转换成可序列化的普通 Python 值。"""
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
    初版交易日推定：
    21:00 及之后的夜盘归入下一自然日。
    注意：尚未接入大商所节假日交易日历，结果需要验证。
    source_date/source_time 必须已由调用方严格校验；此处不以本机日期兜底。
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
    """校验历史日线的日期、数值和 OHLC 逻辑；失败时拒绝写入。"""
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

    # 日期必须有效且不能重复
    dates = pd.to_datetime(data["date"], errors="coerce")
    if dates.isna().any():
        bad_rows = data.index[dates.isna()].tolist()[:10]
        raise ValueError(f"存在无效交易日期，行索引示例：{bad_rows}")

    normalized_dates = dates.dt.strftime("%Y-%m-%d")
    duplicated = normalized_dates[normalized_dates.duplicated(keep=False)]
    if not duplicated.empty:
        examples = sorted(set(duplicated.tolist()))[:10]
        raise ValueError(f"历史日线存在重复日期：{examples}")

    # OHLC 必须为有限正数；结算价允许源数据用 0 表示缺失
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
    if settle.isna().any():
        raise ValueError("结算价存在缺失或非数值")
    if not np.isfinite(settle).all():
        raise ValueError("结算价存在非有限值")
    if (settle < 0).any():
        raise ValueError("结算价存在负值")
    data["settle"] = settle

    # OHLC 关系必须成立
    invalid = (
        (data["high"] < data[["open", "close", "low"]].max(axis=1))
        | (data["low"] > data[["open", "close", "high"]].min(axis=1))
    )

    # 仅对已经核实的两条历史源数据异常进行显式标记，不修改原始价格。
    known_bad_dates = {"2011-01-03", "2020-08-06"}
    known_bad = normalized_dates.isin(known_bad_dates) & invalid
    unexpected_bad = invalid & ~known_bad

    if unexpected_bad.any():
        examples = normalized_dates[unexpected_bad].tolist()[:10]
        raise ValueError(f"发现未登记的 OHLC 异常，拒绝写入：{examples}")

    data["quality_status"] = "valid"
    data.loc[known_bad, "quality_status"] = "invalid_ohlc"

    # 成交量和持仓量必须是非负有限数值
    for column in ["volume", "hold"]:
        values = pd.to_numeric(data[column], errors="coerce")
        if values.isna().any():
            raise ValueError(f"字段 {column} 存在缺失或非数值")
        if not np.isfinite(values).all():
            raise ValueError(f"字段 {column} 存在非有限数值")
        if (values < 0).any():
            raise ValueError(f"字段 {column} 存在负值")
        data[column] = values

    # 持仓量和成交量不允许缺失；通过后返回标准化副本
    data["date"] = normalized_dates
    return data

def append_jsonl(records: list[dict], log_path: Path | None = None, key_fields: tuple[str, ...] = ("symbol", "datetime")) -> int:
    """将记录去重追加写入 JSONL 文件。

    参数:
        records: 要写入的记录列表
        log_path: 目标 JSONL 文件路径，默认使用 QUALITY_LOG
        key_fields: 去重依据的字段名元组，默认 ("symbol", "datetime")

    返回:
        本次实际写入的条数。
    """
    if not records:
        return 0

    log_path = Path(log_path) if log_path else QUALITY_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)

    existing = set()
    if log_path.exists():
        with log_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    existing.add(tuple(item.get(k) for k in key_fields))
                except json.JSONDecodeError:
                    continue

    written = 0
    with log_path.open("a", encoding="utf-8") as f:
        for item in records:
            key = tuple(item.get(k) for k in key_fields)
            if key in existing:
                continue
            existing.add(key)
            f.write(json.dumps(item, ensure_ascii=False, allow_nan=False) + "\n")
            written += 1
    return written


def fetch_sina_spot(symbol: str = "V0") -> Optional[dict]:
    """
    从新浪财经 API 拉取 PVC 连续合约（V0）实时行情原始字段。

    直接调用 Sina HTTP 接口而非 akshare.futures_zh_spot（后者存在列数
    不匹配导致的 ValueError 缺陷）。

    返回字段字典；失败时返回 None。
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
    """严格校验源日期：必须为 YYYY-MM-DD 且为真实日历日期；否则返回 None。"""
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
    """严格校验源时间：必须为 HHMMSS 且时分秒合法；否则返回 None。"""
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
    获取 PVC 连续合约实时快照，独立于历史 CSV。

    约定：
    - source_date / source_time 来自数据源本身（新浪 API），不把采集时间
      冒充行情时间。
    - collected_at 记录实际采集时间。
    - 数据源的成交量与持仓量原样保存。
    - 保存到 output/{symbol}_realtime_snapshots.jsonl。
    - 返回保存的记录；采集失败返回 None。
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
    将记录列表直接写入 UTF-8 BOM 编码的 CSV 文件。
    列名为所有记录字段的并集，保留原字段名称及首次出现的顺序。
    写入临时文件，成功后原子替换，避免留下半成品。
    """
    if not records:
        # 无记录时写入仅含 header 的 CSV，清空旧数据（防止异常记录残留）
        if not csv_path.exists():
            return 0
        fieldnames = []
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                fieldnames = list(reader.fieldnames)
        temp_path = csv_path.with_name(csv_path.name + ".tmp")
        try:
            with temp_path.open("w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(
                    f, fieldnames=fieldnames, extrasaction="ignore"
                )
                writer.writeheader()
            temp_path.replace(csv_path)
        except Exception:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass
            raise
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
    """从 CSV 文件读取记录列表。文件不存在时返回空列表。"""
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [row for row in reader]

def update_daily_bars(df: pd.DataFrame, symbol: str = "V0") -> int:
    """
    历史日线以 (symbol, trading_date) 为唯一键。
    每次读取历史接口后进行合并、去重并整体写回 CSV。
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
    将行情分钟时间戳统一为带时区的 pandas Timestamp。
    输入无时区则本地化为 tz；已带时区则转换到 tz，避免跨时区混比。
    无法解析返回 pd.NaT。
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
    以带时区的采集时间 (collected_at) 为基准，识别行情时间晚于
    采集时间加容差 (FUTURE_TIMESTAMP_TOLERANCE) 的记录。

    行为：
    - 未来时间记录标记 issue="future_timestamp"，不写入有效分钟线数据集；
      其时间、品种、OHLC、成交量、持仓量及采集时间记录到质量日志
      (output/minute_data_quality.jsonl)，同一条 (symbol, datetime) 记录
      不重复写入。
    - 时间戳本身不被修改（不把 09:01 改成 21:01 等）。
    - 时间比较统一为 Asia/Shanghai 时区。
    - 返回仅含正常记录的 DataFrame（按 datetime 排序、重置索引）。
    """
    if data.empty:
        return data.copy()

    threshold = pd.Timestamp(collected_at) + FUTURE_TIMESTAMP_TOLERANCE
    future_records = []
    keep_mask = []

    for _, row in data.iterrows():
        bar_dt = parse_market_datetime(row["datetime"])
        if pd.isna(bar_dt):
            # 无法解析的时间戳不在本函数判断，保留以维持原有行为。
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
    对已合并的数据集按记录自身的 collected_at 校验。

    判定规则（统一 Asia/Shanghai 时区）：
        record.datetime > record.collected_at + FUTURE_TIMESTAMP_TOLERANCE
    的记录视为未来时间戳异常，从最终数据集中移除，并记录到质控日志。

    该步骤在合并历史数据之后执行，用于清理旧文件中因历史未受过滤而残留的
    异常记录，避免旧文件异常被重新保留。
    - 不修改异常记录的原始时间。
    - 同一条 (symbol, datetime) 异常记录不重复写入日志。
    - 缺少可用的时间对（datetime/collected_at）的记录原样保留。
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
            # 旧记录保留原始 collected_at，只更新行情字段
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
    """白盘收盘后，可采集白盘日线数据。

    PVC 白盘交易时间（大商所）：09:00-15:00。
    15:30 后白盘日线数据即可获取，无需等到夜盘收盘。
    周末休市时返回 False。
    """
    now = datetime.now(TZ)
    weekday = now.weekday()  # 0=Mon … 5=Sat, 6=Sun
    hhmm = int(now.strftime("%H%M"))

    if weekday >= 5:  # 周末休市
        return False
    # 周一到周五：白盘 15:30 后可采集当日白盘日线
    return hhmm >= 1530


def is_after_market_close() -> bool:
    """
    判断当前北京时间是否已过 PVC 交易当日收盘。

    PVC 交易时间（大商所）：
    - 白盘：09:00-15:00
    - 夜盘：21:00-23:00（周一至周五，含周五）

    注意：法定节假日前第一个工作日无夜盘，尚未接入交易所日历，
    该情况需手动跳过或后续补全日历校验。

    周末休市时返回 False，避免无意义的 API 调用。
    """
    now = datetime.now(TZ)
    weekday = now.weekday()  # 0=Mon … 5=Sat, 6=Sun
    hhmm = int(now.strftime("%H%M"))

    if weekday >= 5:  # 周末休市
        return False
    # 周一至周五：夜盘 23:00 后即可获取完整日线（含周五夜盘）
    return hhmm >= 2300

def fetch_and_update_daily_bars(symbol: str, session_label: str) -> Optional[int]:
    """
    获取并更新指定品种的日线数据。

    参数:
        symbol: 合约代码，如 "V0"、"V2701"
        session_label: 日志标签，如 "白盘"、"完整"

    返回:
        更新条数，失败返回 None
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

    # 1. 实时快照（独立运行，不影响其他数据流）
    for sym in ("V0", "V2701"):
        try:
            snapshot = collect_realtime_snapshot(symbol=sym)
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

    # 2. 分钟线（独立运行，不依赖日线最新日期是否等于当天）
    for sym in ("V2701", "V0"):
        try:
            minute_df = _retryable_call(ak.futures_zh_minute_sina, symbol=sym, period="1")
            if minute_df is None or minute_df.empty:
                raise RuntimeError(f"{sym} 分钟数据为空，停止更新。")
            updated, total = update_minute_bars(sym, minute_df)
            logger.info(
                "分钟线 %s：本次校验 %d 条；文件累计 %d 条；CSV %s",
                sym, updated, total, get_minute_csv(sym),
            )
        except Exception as exc:
            logger.error("分钟线 %s 更新失败：%s", sym, exc)

    # 3. 日线（独立运行，白盘收盘后采集白盘日线，完全收盘后采集完整日线）
    #    互斥：当完全收盘条件满足时，只采集完整日线；否则采集白盘日线。
    for sym in ("V0", "V2701"):
        try:
            if is_after_market_close():
                fetch_and_update_daily_bars(sym, "完整")
            elif is_after_day_session_close():
                fetch_and_update_daily_bars(sym, "白盘")
            else:
                logger.info("日线 %s：未到采集时间，跳过", sym)

        except Exception as exc:
            logger.error("日线 %s 更新失败（不影响其他流程）：%s", sym, exc)
