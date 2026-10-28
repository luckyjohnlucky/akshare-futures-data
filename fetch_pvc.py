#!/usr/bin/env python3
"""采集 PVC 连续合约实时快照与历史日线。"""

import csv
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import akshare as ak
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
SNAPSHOTS = OUT / "realtime_snapshots.jsonl"
DAILY_BARS = OUT / "daily_bars.json"
DAILY_BARS_CSV = OUT / "daily_bars.csv"
TZ = ZoneInfo("Asia/Shanghai")


def clean(value):
    """将 Pandas/Numpy 值转换成可序列化的普通 Python 值。"""
    if value is None or pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, (int, float, str, bool)):
        return value
    return str(value)


def number(value):
    value = clean(value)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_sina_source_date():
    """
    尝试读取新浪原始行情中的日期字段。
    失败时返回 None，不把本机日期伪装成行情源日期。
    """
    url = "https://hq.sinajs.cn/list=nf_V0"
    headers = {
        "Referer": "https://finance.sina.com.cn/",
        "User-Agent": "Mozilla/5.0",
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        match = re.search(r'"([^"]*)"', response.text)
        if not match:
            return None

        fields = match.group(1).split(",")
        if len(fields) > 17:
            candidate = fields[17].strip()
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
                return candidate
    except Exception as exc:
        print(f"提示：未能读取新浪原始日期字段：{exc}")

    return None


def infer_trading_date(source_date, source_time, collected_at):
    """
    初版交易日推定：
    21:00 及之后的夜盘归入下一自然日。
    注意：尚未接入大商所节假日交易日历，结果需要验证。
    """
    base_date = source_date or collected_at.date().isoformat()

    try:
        day = datetime.strptime(base_date, "%Y-%m-%d").date()
    except ValueError:
        day = collected_at.date()

    try:
        hhmmss = int(str(source_time).strip())
    except (TypeError, ValueError):
        hhmmss = -1

    if 210000 <= hhmmss <= 235959:
        day += timedelta(days=1)

    return day.isoformat()



def validate_daily_bars(df):
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
        if values.isna().any() or not values.map(
            lambda x: pd.notna(x) and abs(float(x)) != float("inf")
        ).all():
            raise ValueError(f"价格字段 {column} 存在缺失或非有限数值")
        if (values <= 0).any():
            raise ValueError(f"价格字段 {column} 存在小于或等于 0 的值")
        data[column] = values

    settle = pd.to_numeric(data["settle"], errors="coerce")
    if settle.isna().any() or not settle.map(
        lambda x: pd.notna(x) and abs(float(x)) != float("inf")
    ).all():
        raise ValueError("结算价存在缺失、非数值或非有限值")
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
        if not values.map(
            lambda x: pd.notna(x) and abs(float(x)) != float("inf")
        ).all():
            raise ValueError(f"字段 {column} 存在非有限数值")
        if (values < 0).any():
            raise ValueError(f"字段 {column} 存在负值")
        data[column] = values

    # 持仓量和成交量不允许缺失；通过后返回标准化副本
    data["date"] = normalized_dates
    return data

def append_snapshot(record):
    with SNAPSHOTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")


def fetch_sina_spot(symbol="V0"):
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
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as exc:
        print(f"提示：获取新浪实时行情失败：{exc}")
        return None

    match = re.search(r'"([^"]*)"', response.text)
    if not match:
        return None

    fields = match.group(1).split(",")
    if len(fields) < 18:
        print(f"提示：新浪行情字段数不足（{len(fields)} < 18），跳过")
        return None

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


def collect_realtime_snapshot():
    """
    获取 PVC 连续合约实时快照，独立于历史 CSV。

    约定：
    - source_date / source_time 来自数据源本身（新浪 API），不把采集时间
      冒充行情时间。
    - collected_at 记录实际采集时间。
    - 数据源的成交量与持仓量原样保存。
    - 保存到 output/realtime_snapshots.jsonl。
    - 返回保存的记录；采集失败返回 None。
    """
    spot = fetch_sina_spot(symbol="V0")
    if spot is None:
        print("提示：实时快照采集失败，未获取到行情数据")
        return None

    collected_at = datetime.now(TZ)
    source_date = spot.get("date")
    source_time = spot.get("time")

    source_time_str = str(source_time).strip() if source_time else ""
    source_time_valid = bool(re.fullmatch(r"\d{6}", source_time_str))
    if not source_time_valid:
        print(f"提示：行情时间格式异常（source_time={source_time!r}），仍记录到快照")

    trading_date = infer_trading_date(source_date, source_time, collected_at)

    is_night = source_time_valid and 210000 <= int(source_time_str) <= 235959
    trading_date_method = (
        "inferred_next_calendar_day_for_night_session"
        if is_night else "calendar_day"
    )

    last_close_raw = number(spot.get("last_close"))
    last_settle_raw = number(spot.get("last_settle_price"))
    vol = number(spot.get("volume"))

    record = {
        "symbol": "V0",
        "name": spot.get("name") or "PVC连续",
        "source": "Sina via AKShare",
        "source_date": source_date,
        "source_time": source_time,
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
        "volume": int(vol) if vol is not None and vol == int(vol) else vol,
        "is_daily_bar_final": False,
    }
    append_snapshot(record)
    return record


def json_to_csv(json_path, csv_path):
    """
    将 JSON 数组文件转换为 UTF-8 BOM 编码的 CSV 文件。
    列名为所有记录字段的并集，保留原字段名称及首次出现的顺序。
    写入临时文件，成功后原子替换，避免留下半成品。
    """
    try:
        raw = json.loads(json_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(
            f"JSON 文件不存在，无法生成 CSV：{json_path}"
        )
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"JSON 文件内容无法解析，无法生成 CSV：{json_path}：{exc}"
        ) from exc

    if not isinstance(raw, list):
        raise ValueError(f"JSON 文件不是数组，无法生成 CSV：{json_path}")

    fieldnames = []
    seen = set()
    rows = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(
                f"JSON 数组中的第 {index} 条记录不是对象，无法生成 CSV：{json_path}"
            )
        rows.append(item)
        for key in item.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)

    if not rows:
        raise ValueError(f"JSON 数组为空，无法生成 CSV：{json_path}")

    temp_path = csv_path.with_name(csv_path.name + ".tmp")
    try:
        with temp_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=fieldnames, extrasaction="ignore"
            )
            writer.writeheader()
            for item in rows:
                writer.writerow(item)
        temp_path.replace(csv_path)
    except Exception:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass
        raise
    return len(rows)


def json_matches_csv(json_path, csv_path):
    """
    Check whether the CSV file is a faithful derivation of the JSON file.

    Compares:
    - record count
    - field collection (union of JSON keys) MUST equal CSV header field set
    - no duplicate field names in CSV header
    - per-record values (in order), with JSON None mapped to CSV empty string
    - every CSV record must have exactly the same field set (no extra/missing)

    This is NOT a cross-file atomic transaction; it is a consistency checkpoint.
    """
    try:
        raw = json.loads(json_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False

    if not isinstance(raw, list):
        return False

    # Check every JSON item is a dict before proceeding
    json_fields = set()
    for item in raw:
        if not isinstance(item, dict):
            return False
        json_fields.update(item.keys())

    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            csv_fieldnames = reader.fieldnames
            csv_records = list(reader)
    except (FileNotFoundError, OSError):
        return False

    # If JSON is empty but CSV has data, they don't match
    if not raw and csv_records:
        return False

    # Empty JSON and empty CSV (no header, no data) -> consistent
    if not raw and not csv_records and csv_fieldnames is None:
        return True

    # Empty JSON with proper CSV header (no data rows) -> consistent
    if not raw and not csv_records and csv_fieldnames is not None:
        return True

    # CSV header must exist
    if csv_fieldnames is None:
        return False

    # Check for duplicate field names in CSV header
    if len(csv_fieldnames) != len(set(csv_fieldnames)):
        return False

    # CSV header field set must exactly match JSON field set
    csv_field_set = set(csv_fieldnames)
    if json_fields != csv_field_set:
        return False

    # Record count must match
    if len(raw) != len(csv_records):
        return False

    # Compare every record value (in order), with strict field set per row
    for json_item, csv_row in zip(raw, csv_records):
        # csv.DictReader puts extra columns under None key (restkey) or
        # missing columns get None. Check row field count matches header.
        # None key in csv_row means extra columns were found
        if None in csv_row:
            return False

        # Check for None values (missing fields in CSV row)
        for key in json_fields:
            if csv_row.get(key) is None:
                return False

        for key in json_fields:
            json_val = json_item.get(key)
            csv_val = csv_row.get(key, "")
            # Map JSON None to CSV empty string for comparison
            if json_val is None:
                json_str = ""
            else:
                json_str = str(json_val)
            csv_str = str(csv_val) if csv_val is not None else ""
            if json_str != csv_str:
                return False

    return True


def update_daily_bars(df):
    """
    历史日线以 (symbol, trading_date) 为唯一键。
    每次读取历史接口后进行合并、去重并整体写回。
    """
    records_by_key = {}

    if DAILY_BARS.exists():
        try:
            old_records = json.loads(DAILY_BARS.read_text(encoding="utf-8"))
            for item in old_records:
                key = (item["symbol"], item["trading_date"])
                records_by_key[key] = item
        except (json.JSONDecodeError, OSError, KeyError, TypeError) as exc:
            raise RuntimeError(
                f"现有历史 JSON 无法安全读取，已停止写入以防覆盖：{exc}"
            ) from exc

    for _, row in df.iterrows():
        trading_date = pd.to_datetime(row["date"]).date().isoformat()
        record = {
            "symbol": "V0",
            "name": "PVC连续",
            "trading_date": trading_date,
            "open": number(row.get("open")),
            "high": number(row.get("high")),
            "low": number(row.get("low")),
            "close": number(row.get("close")),
            "volume": clean(row.get("volume")),
            "open_interest": clean(row.get("hold")),
            "settle_raw": number(row.get("settle")),
            "settle": (
                None if number(row.get("settle")) == 0
                else number(row.get("settle"))
            ),
            "quality_status": clean(row.get("quality_status")) or "valid",
            "source": "AKShare futures_zh_daily_sina",
            "collected_at": datetime.now(TZ).isoformat(),
        }
        records_by_key[("V0", trading_date)] = record

    result = sorted(
        records_by_key.values(),
        key=lambda item: (item["symbol"], item["trading_date"]),
    )

    temp_path = DAILY_BARS.with_suffix(".json.tmp")
    try:
        temp_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(DAILY_BARS)
    except Exception:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass
        raise
    return len(result)


MINUTE_BARS = OUT / "minute_bars.json"
MINUTE_BARS_CSV = OUT / "minute_bars.csv"
QUALITY_LOG = OUT / "minute_data_quality.jsonl"
FUTURE_TIMESTAMP_TOLERANCE = timedelta(minutes=1)


def validate_minute_bars(df):
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
        if data[col].isna().any() or not data[col].map(
            lambda x: pd.notna(x) and abs(float(x)) != float("inf")
        ).all():
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


def parse_market_datetime(value, tz=TZ):
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


def append_quality_records(records, log_path=None):
    """
    将分钟数据异常记录去重追加写入 JSONL 质量日志。
    去重依据 (symbol, datetime)：与已有日志条目重复的记录不再重复写入。
    返回本次实际写入的条数。
    """
    if not records:
        return 0

    log_path = Path(log_path) if log_path else Path(QUALITY_LOG)
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
                except json.JSONDecodeError:
                    continue
                existing.add((item.get("symbol"), item.get("datetime")))

    written = 0
    with log_path.open("a", encoding="utf-8") as f:
        for item in records:
            key = (item["symbol"], item["datetime"])
            if key in existing:
                continue
            existing.add(key)
            f.write(json.dumps(item, ensure_ascii=False, allow_nan=False) + "\n")
            written += 1
    return written


def separate_future_timestamps(data, symbol, collected_at, log_path=None):
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
        append_quality_records(future_records, log_path)

    valid = data[keep_mask].copy()
    return valid.sort_values("datetime").reset_index(drop=True)


def filter_future_anomalies(records, log_path=None):
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
        if bar_dt is None or coll_dt is None:
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
        append_quality_records(anomalies, log_path)
    return kept


def update_minute_bars(symbol, df):
    data = validate_minute_bars(df)
    collected_at = datetime.now(TZ)
    data = separate_future_timestamps(data, symbol, collected_at)
    old_records = []

    if MINUTE_BARS.exists():
        with MINUTE_BARS.open("r", encoding="utf-8") as f:
            old_records = json.load(f)
        if not isinstance(old_records, list):
            raise ValueError("分钟历史文件格式错误：预期为 JSON 数组")

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
        item = {
            "symbol": symbol,
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
        records[(symbol, timestamp)] = item

    merged = sorted(records.values(), key=lambda x: (x["symbol"], x["datetime"]))
    merged = filter_future_anomalies(merged)
    temp_path = MINUTE_BARS.with_suffix(".json.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write("\n")
        temp_path.replace(MINUTE_BARS)
    except Exception:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass
        raise
    return len(data), len(merged)


def is_after_market_close():
    """
    判断当前北京时间是否已过 PVC 交易当日收盘。

    PVC 交易时间（大商所）：
    - 白盘：09:00-15:00
    - 夜盘：21:00-23:00（周日至周四）

    周五无夜盘，收盘后（15:00）即可获取当周最后一个日线。
    其他交易日夜盘收盘后（23:00）即可获取完整日线。
    周末休市时返回 False，避免无意义的 API 调用。
    """
    now = datetime.now(TZ)
    weekday = now.weekday()  # 0=Mon … 5=Sat, 6=Sun
    hhmm = int(now.strftime("%H%M"))

    if weekday == 4:
        return hhmm >= 1500
    if 0 <= weekday <= 3:
        return hhmm >= 2300
    return False

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)

    # Pre-flight: rebuild CSV if existing JSON/CSV are inconsistent.
    # JSON is the authoritative data source; CSV is a regenerable derivation.
    for json_file, csv_file, label in [
        (MINUTE_BARS, MINUTE_BARS_CSV, "分钟线"),
        (DAILY_BARS, DAILY_BARS_CSV, "日线"),
    ]:
        if json_file.exists() and (
            not csv_file.exists() or not json_matches_csv(json_file, csv_file)
        ):
            print(f"[修复] {label} CSV 缺失或与 JSON 不一致，重新生成中...")
            try:
                json_to_csv(json_file, csv_file)
            except Exception as exc:
                print(f"错误：{label} CSV 重建失败: {exc}，路径 {csv_file}；"
                      f"JSON 保持有效，CSV 可在下次运行时重试。")
                raise SystemExit(1)

    # 1. 实时快照（独立运行，不影响其他数据流）
    try:
        snapshot = collect_realtime_snapshot()
        if snapshot:
            print(f"实时快照：已保存，行情时间 {snapshot.get('source_date')} "
                  f"{snapshot.get('source_time')}，采集时间 {snapshot.get('collected_at')}")
        else:
            print("实时快照：采集失败，未获取到行情数据")
    except Exception as exc:
        print(f"实时快照采集失败（不影响其他流程）：{exc}")

    # 2. 分钟线（独立运行，不依赖日线最新日期是否等于当天）
    try:
        minute_df = ak.futures_zh_minute_sina(symbol="V2701", period="1")
        if minute_df is None or minute_df.empty:
            raise RuntimeError("分钟数据为空，停止更新。")
        updated, total = update_minute_bars("V2701", minute_df)
        try:
            json_to_csv(MINUTE_BARS, MINUTE_BARS_CSV)
        except Exception as exc:
            print(f"错误：分钟线 CSV 生成失败: {exc}；JSON 已更新，CSV 可重建。")
        print(f"分钟线：本次校验 {updated} 条；文件累计 {total} 条；"
              f"路径 {MINUTE_BARS}；CSV {MINUTE_BARS_CSV}")
    except Exception as exc:
        print(f"分钟线更新失败（不影响其他流程）：{exc}")

    # 3. 日线（独立运行，仅在收盘后采集以避免重复获取）
    try:
        if not is_after_market_close():
            print("日线：未到收盘时间，跳过采集")
        else:
            daily_df = ak.futures_zh_daily_sina(symbol="V0")
            if daily_df is None or daily_df.empty:
                raise RuntimeError("日线数据为空，停止更新。")

            required = {"date", "open", "high", "low", "close", "volume", "hold", "settle"}
            missing = required - set(daily_df.columns)
            if missing:
                raise ValueError(f"日线数据缺少字段：{sorted(missing)}")

            validated = validate_daily_bars(daily_df)
            count = update_daily_bars(validated)
            try:
                json_to_csv(DAILY_BARS, DAILY_BARS_CSV)
            except Exception as exc:
                print(f"错误：日线 CSV 生成失败: {exc}；JSON 已更新，CSV 可重建。")
            print(f"日线：本次校验 {len(validated)} 条；更新结果 {count}；"
                  f"路径 {DAILY_BARS}；CSV {DAILY_BARS_CSV}")
    except Exception as exc:
        print(f"日线更新失败（不影响其他流程）：{exc}")
