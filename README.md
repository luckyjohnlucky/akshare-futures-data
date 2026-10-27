# akshare-futures-data

采集 PVC 连续合约（`V0`/`V2701`）的历史日线与分钟行情，执行质量校验、去重与合并，
并输出结构化 JSON 与 CSV。

## 环境

- Python 3.9+（建议 3.13）
- 依赖见 `requirements.txt`；建议使用虚拟环境：

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## 运行

```bash
python fetch_pvc.py
```

依次执行：

1. 抓取 `V2701` 分钟行情 → `validate_minute_bars` 校验 →
   `separate_future_timestamps` 过滤采集后未到时间的 bar（以 `Asia/Shanghai`
   时区 `collected_at` 为基准，容差 1 分钟）
   → `update_minute_bars` 合并历史并原子写入 `output/minute_bars.json`
   → `json_to_csv` 输出 `output/minute_bars.csv`。
2. 抓取 `V0` 日线 → `validate_daily_bars` → `update_daily_bars`
   → `output/daily_bars.json` + `output/daily_bars.csv`。

## 数据目录 (`output/`)

| 文件 | 说明 |
|------|------|
| `minute_bars.json` / `minute_bars.csv` | 分钟 Bar，按 `(symbol, datetime)` 去重合并，按时间升序。 |
| `daily_bars.json` / `daily_bars.csv` | 日线，按 `(symbol, trading_date)` 去重合并，按日期升序。 |
| `minute_data_quality.jsonl` | 因异常（如 `future_timestamp`）被排除的分钟记录明细。 |
| `realtime_snapshots.jsonl` | 实时快照流（个人采集，未入库）。 |

## 质量过滤规则

- **未来时间戳 (`future_timestamp`)**：`datetime > collected_at + 1 分钟`
  (统一 `Asia/Shanghai` 时区)。
  - 新抓取的数据在合并前过滤；
  - 合并历史后亦会重新校验（`filter_future_anomalies`），避免旧文件残留异常被保留。
  - 异常记录原件写入 `minute_data_quality.jsonl`，以 `(symbol, datetime)` 去重；
    **不修改**异常记录的原始时间戳。
- 行情完整性校验：OHLC 关联、非负成交量/持仓、去重日期/时间戳等。

## 测试

```bash
python -m unittest discover -s tests -v
```

## 安全约定

- 写盘采用“临时文件 + 原子替换” (`rename`)，避免半成品；
- 接口返回空/`None` 或校验失败时，抛出异常并**不改动**已有行情文件。
