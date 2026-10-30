# akshare-futures-data

采集 PVC 连续合约（`V0`/`V2701`）的历史日线与分钟行情，执行质量校验、去重与合并，
并输出结构化 CSV 与实时快照 JSONL。

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

执行顺序（各流程相互独立，单流程失败不影响其他流程）：

1. **实时快照**：抓取 `V2701`/`V0` 新浪 HTTP API 实时行情 → 严格校验源日期/源时间 →
   写入 `output/V0_realtime_snapshots.jsonl` / `output/V2701_realtime_snapshots.jsonl`。
2. **分钟线**：抓取 `V2701`/`V0` AKShare 1 分钟行情 → `validate_minute_bars` 校验 →
   `separate_future_timestamps` 过滤采集后未到时间的 bar（以 `Asia/Shanghai`
   时区 `collected_at` 为基准，容差 1 分钟）
   → `update_minute_bars` 合并历史并原子写入 `output/V0_minute_bars.csv` /
   `output/V2701_minute_bars.csv`。
3. **日线**：白盘收盘后（15:00+，周一至周五）抓取 `V0`/`V2701` AKShare 日线 →
   `validate_daily_bars` 校验 → `update_daily_bars` 合并历史并原子写入
   `output/V0_daily_bars.csv` / `output/V2701_daily_bars.csv`。

### 各流程执行机制

#### 实时快照（独立流程）

- 数据源：新浪 HTTP API (`https://hq.sinajs.cn/list=nf_{symbol}`)，不使用 akshare
  `futures_zh_spot`（后者存在列数不匹配缺陷）。
- 字段：`source_date` / `source_time` 来自数据源本身，`collected_at` 记录实际采集时间，
  两者不混淆。
- 校验：`source_date` 必须为有效日历日期；`source_time` 必须为合法 HHMMSS；
  否则拒绝写入，不留空记录。
- 交易日推定：21:00 及之后的夜盘归入下一自然日（`infer_trading_date`）。
- 写盘：JSONL 追加写入，以 `(symbol, source_date, source_time)` 为去重键，
  同一条快照不重复追加。
- 失败处理：API 异常返回 `None`，不写入文件，不影响其他流程。

#### 分钟线（独立流程）

- 数据源：`ak.futures_zh_minute_sina(symbol=symbol, period="1")`。
- 校验：`validate_minute_bars` 检查必填字段（`datetime, open, high, low, close,
  volume, hold`）、无效时间戳、重复时间戳、非正 OHLC、OHLC 逻辑关系、
  非负成交量/持仓量。
- 未来时间戳过滤：`separate_future_timestamps` 以 `collected_at + 1 分钟` 为阈值，
  剔除晚于阈值的 bar，记录至 `output/minute_data_quality.jsonl`；
  `update_minute_bars` 合并历史后再通过 `filter_future_anomalies` 二次清理旧文件残留异常。
- 写盘：以 `(symbol, datetime)` 为去重键，旧记录保留原始 `collected_at`，
  仅更新行情字段；新记录写入当前 `collected_at`。
- 失败处理：API 异常或校验失败抛出异常，**不改动**已有分钟线文件。

#### 日线（独立流程）

- 数据源：`ak.futures_zh_daily_sina(symbol=symbol)`。
- 采集时机：北京时间 15:00 后，周一至周五（`is_after_market_close()`）。
  白盘收盘后，前一夜盘与今日日盘数据即齐备，可采集当日交易日完整日线。
  夜盘（21:00-23:00）归入下一交易日，不影响今日日线完整性。
  周末不采集。
- 校验：`validate_daily_bars` 检查必填字段（`date, open, high, low, close,
  volume, hold, settle`）、日期有效性与去重、OHLC 正数与逻辑关系、
  结算价非负（允许 0 表示缺失，写入时转为 `None`）、成交量/持仓量非负。
  已知异常日期（`2011-01-03`, `2020-08-06`）的 OHLC 异常仅标记
  `quality_status="invalid_ohlc"`，不拒绝写入；未登记的 OHLC 异常会拒绝写入。
- 写盘：以 `(symbol, trading_date)` 为去重键，旧记录被新数据覆盖，
  其余历史原样保留；全量排序后通过临时文件 + 原子替换写回 CSV。
- 失败处理：API 异常或校验失败抛出异常，**不改动**已有日线文件。

## 数据目录 (`output/`)

| 文件 | 说明 |
|------|------|
| `output/V0_minute_bars.csv` | V0 分钟 Bar，按 `(symbol, datetime)` 去重合并，按时间升序。 |
| `output/V2701_minute_bars.csv` | V2701 分钟 Bar，按 `(symbol, datetime)` 去重合并，按时间升序。 |
| `output/V0_daily_bars.csv` | V0 日线，按 `(symbol, trading_date)` 去重合并，按日期升序。 |
| `output/V2701_daily_bars.csv` | V2701 日线，按 `(symbol, trading_date)` 去重合并，按日期升序。 |
| `output/V0_realtime_snapshots.jsonl` | V0 实时快照流（JSONL，追加写入）。 |
| `output/V2701_realtime_snapshots.jsonl` | V2701 实时快照流（JSONL，追加写入）。 |
| `output/minute_data_quality.jsonl` | 因异常（如 `future_timestamp`）被排除的分钟记录明细（全局）。 |

## 质量过滤规则

- **未来时间戳 (`future_timestamp`)**：`datetime > collected_at + 1 分钟`
  (统一 `Asia/Shanghai` 时区)。
  - 新抓取的数据在合并前过滤；
  - 合并历史后亦会重新校验（`filter_future_anomalies`），避免旧文件残留异常被保留。
  - 异常记录原件写入 `minute_data_quality.jsonl`，以 `(symbol, datetime)` 去重；
    **不修改**异常记录的原始时间戳。
- **日线 OHLC 校验**：`high >= max(open, close, low)` 且 `low <= min(open, close, high)`；
  未登记异常会拒绝写入，已知异常（`2011-01-03`, `2020-08-06`）仅标记 `invalid_ohlc`。
- **分钟线 OHLC 校验**：同日线逻辑，异常直接拒绝写入。
- **成交量/持仓量**：必须非负，缺失时日线字段转为 `None`，分钟线直接拒绝。

## 大商所交易时间安排（PVC / 聚氯乙烯 `v`）

| 时段 | 时间 | 适用日 |
|------|------|--------|
| 日盘集合竞价申报 | 08:55 - 08:59 | 周一至周五 |
| 日盘集合竞价撮合 | 08:59 - 09:00 | 周一至周五 |
| 日盘第一节 | 09:00 - 10:15 | 周一至周五 |
| 小节休息 | 10:15 - 10:30 | 周一至周五 |
| 日盘第二节 | 10:30 - 11:30 | 周一至周五 |
| 日盘第三节 | 13:30 - 15:00 | 周一至周五 |
| 夜盘集合竞价申报 | 20:55 - 20:59 | 周一至周五 |
| 夜盘集合竞价撮合 | 20:59 - 21:00 | 周一至周五 |
| 夜盘连续竞价 | 21:00 - 23:00 | 周一至周五 |

### 采集时机规则

- **完整日线**：北京时间 15:00 后，周一至周五可采集（`is_after_market_close` / `is_after_day_session_close`）
  - 白盘收盘后，前一夜盘与今日日盘数据即齐备，可采集当日交易日完整日线
  - 夜盘归入下一交易日，不影响今日日线完整性
- **周末**：不采集

### 交易日推定

- 21:00 及之后的夜盘行情，归入**下一自然日**作为交易日（`infer_trading_date`）
- 白盘行情，交易日即为当前自然日

> 注：法定节假日前第一个工作日无夜盘，代码尚未接入大商所交易所日历，此类情况需手动跳过或后续补全日历校验。

## 测试

```bash
python -m unittest discover -s tests -v
```

所有测试使用临时目录和 Mock，不访问真实网络，不读写正式数据文件。

## GitHub 工作流（手动触发）

- 工作流：`.github/workflows/collect.yml`，触发方式为 `workflow_dispatch`（手动）。
- 触发者：NAS 手动发出 GitHub Actions 命令执行，无定时自动触发。
- 并发控制：`concurrency.group: pvc-collect`，`cancel-in-progress: false`，
  避免并发运行导致推送冲突。
- 推送策略：`git fetch + rebase origin/main`，推送失败时最多重试 3 次，
  每次重试间隔 5 秒。

## 安全约定

- 写盘采用“临时文件 + 原子替换” (`rename`)，避免半成品；
- 接口返回空/`None` 或校验失败时，抛出异常并**不改动**已有行情文件；
- 工作流 `git push` 前执行 `git fetch + rebase`，失败时最多重试 3 次，
  避免并发提交导致推送被拒绝；
- 各流程相互独立，单流程失败不影响其他流程。
