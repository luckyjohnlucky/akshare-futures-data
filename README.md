# akshare-futures-data

Collect historical daily and minute bars for PVC continuous contracts (`V0`/`V2701`), perform quality validation, deduplication and merging, and output structured CSV and real-time snapshot JSONL.

## Environment

- Python 3.9+ (virtual environment uses Python 3.13)
- Dependencies in `requirements.txt`; recommended to use a virtual environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Running

```bash
python fetch_pvc.py
```

Execution order (each stream is independent, single stream failure does not affect others):

1. **Real-time snapshot**: Fetch `V2701`/`V0` Sina HTTP API real-time quote → strictly validate source date/source time → write to `output/V0_realtime_snapshots.jsonl` / `output/V2701_realtime_snapshots.jsonl`.
2. **Minute bars**: Fetch `V2701`/`V0` AKShare 1-minute quote → `validate_minute_bars` validation → `separate_future_timestamps` filter bars after collection time (based on `Asia/Shanghai` timezone `collected_at`, 1-minute tolerance) → `update_minute_bars` merge history and atomically write to `output/V0_minute_bars.csv` / `output/V2701_minute_bars.csv`.
3. **Daily bars**: After day session close (15:00+, Monday to Friday) fetch `V0`/`V2701` AKShare daily bars → `validate_daily_bars` validation → `update_daily_bars` merge history and atomically write to `output/V0_daily_bars.csv` / `output/V2701_daily_bars.csv`.

### Stream Execution Mechanisms

#### Parallel Execution

Three data streams (real-time snapshot, minute bars, daily bars) are independent, executed using `ThreadPoolExecutor`. Each symbol's each stream is submitted as an independent task; total duration depends on the slowest individual task, not the sum of all tasks.

Expected speedup:
- After 15:00 (6 tasks): total duration reduced by about 60%-70%, speedup 3-4x
- Before 15:00 (4 tasks, daily bars skipped): total duration reduced by about 50%-60%, speedup 2-3x

Parallel execution safety: different symbols (V0/V2701) operate on different files, no race condition; good failure isolation, single stream failure does not affect others.

#### Real-time Snapshot (Independent Stream)

- Data source: Sina HTTP API (`https://hq.sinajs.cn/list=nf_{symbol}`), does not use akshare `futures_zh_spot` (the latter has a column count mismatch defect).
- Fields: `source_date` / `source_time` come from the data source itself, `collected_at` records actual collection time; the two are not confused.
- Validation: `source_date` must be a valid calendar date; `source_time` must be a valid HHMMSS; otherwise refuse writing, no empty records left.
- Trading date inference: night sessions at 21:00 and later are assigned to the next calendar day (`infer_trading_date`).
- Write: JSONL append write, with `(symbol, source_date, source_time)` as deduplication key; the same snapshot is not appended repeatedly.
- Failure handling: API exception returns `None`, no file written, does not affect other streams.

#### Minute Bars (Independent Stream)

- Data source: `ak.futures_zh_minute_sina(symbol=symbol, period="1")`.
- Validation: `validate_minute_bars` checks required fields (`datetime, open, high, low, close, volume, hold`), invalid timestamps, duplicate timestamps, non-positive OHLC, OHLC logical relationships, non-negative volume/open interest.
- Future timestamp filtering: `separate_future_timestamps` uses `collected_at + 1 minute` as threshold, filters out bars later than the threshold, records to `output/minute_data_quality.jsonl`; `update_minute_bars` after merging history re-cleans old file residual anomalies via `filter_future_anomalies`.
- Write: with `(symbol, datetime)` as deduplication key, old records keep original `collected_at`, only quote fields are updated; new records write current `collected_at`.
- Failure handling: API exception or validation failure raises exception, **does not modify** existing minute bar files.

#### Daily Bars (Independent Stream)

- Data source: `ak.futures_zh_daily_sina(symbol=symbol)`.
- Collection timing: after 15:00 Beijing time, Monday to Friday (`is_after_market_close()`). After day session close, the previous night session and today's day session data are ready, so complete daily bars for the current trading day can be collected. Night sessions (21:00-23:00) are assigned to the next trading day, do not affect today's daily bar completeness. No collection on weekends.
- Validation: `validate_daily_bars` checks required fields (`date, open, high, low, close, volume, hold, settle`), date validity and deduplication, positive OHLC and OHLC logical relationships, non-negative settle price (allows 0 for missing, written as `None`), non-negative volume/open interest. Known anomaly dates (`2011-01-03`, `2020-08-06`) OHLC anomalies are only marked `quality_status="invalid_ohlc"`, not refused; unregistered OHLC anomalies will refuse writing.
- Write: with `(symbol, trading_date)` as deduplication key, old records are overwritten by new data, other history is kept as-is; full sort then written back to CSV via temp file + atomic replace.
- Failure handling: API exception or validation failure raises exception, **does not modify** existing daily bar files.

## Data Directory (`output/`)

| File | Description |
|------|-------------|
| `output/V0_minute_bars.csv` | V0 minute bars, merged and deduplicated by `(symbol, datetime)`, sorted by time ascending. |
| `output/V2701_minute_bars.csv` | V2701 minute bars, merged and deduplicated by `(symbol, datetime)`, sorted by time ascending. |
| `output/V0_daily_bars.csv` | V0 daily bars, merged and deduplicated by `(symbol, trading_date)`, sorted by date ascending. |
| `output/V2701_daily_bars.csv` | V2701 daily bars, merged and deduplicated by `(symbol, trading_date)`, sorted by date ascending. |
| `output/V0_realtime_snapshots.jsonl` | V0 real-time snapshot stream (JSONL, append write). |
| `output/V2701_realtime_snapshots.jsonl` | V2701 real-time snapshot stream (JSONL, append write). |
| `output/minute_data_quality.jsonl` | Minute records excluded due to anomalies (e.g., `future_timestamp`) (global). |

## Quality Filtering Rules

- **Future timestamp (`future_timestamp`)**: `datetime > collected_at + 1 minute` (unified `Asia/Shanghai` timezone).
  - Newly collected data is filtered before merging.
  - After merging history, re-validated via `filter_future_anomalies` to avoid retaining anomalies left in old files.
  - Exception records are written as-is to `minute_data_quality.jsonl`, deduplicated by `(symbol, datetime)`; **original timestamps of exception records are not modified**.
- **Daily bar OHLC check**: `high >= max(open, close, low)` and `low <= min(open, close, high)`; unregistered anomalies refuse writing, known anomalies (`2011-01-03`, `2020-08-06`) are only marked `invalid_ohlc`.
- **Minute bar OHLC check**: Same logic as daily bars; anomalies directly refuse writing.
- **Volume / open interest**: Must be non-negative; missing values result in `None` for daily bar fields, minute bars are directly rejected.

## DCE Trading Schedule (PVC / Polyvinyl Chloride `v`)

| Session | Time | Applicable Day |
|---------|------|----------------|
| Day session opening auction declaration | 08:55 - 08:59 | Monday to Friday |
| Day session opening auction matching | 08:59 - 09:00 | Monday to Friday |
| Day session first period | 09:00 - 10:15 | Monday to Friday |
| Short break | 10:15 - 10:30 | Monday to Friday |
| Day session second period | 10:30 - 11:30 | Monday to Friday |
| Day session third period | 13:30 - 15:00 | Monday to Friday |
| Night session opening auction declaration | 20:55 - 20:59 | Monday to Friday |
| Night session opening auction matching | 20:59 - 21:00 | Monday to Friday |
| Night session continuous auction | 21:00 - 23:00 | Monday to Friday |

### Collection Timing Rules

- **Complete daily bars**: Beijing time after 15:00, Monday to Friday can collect (`is_after_market_close` / `is_after_day_session_close`).
  - After day session close, the previous night session and today's day session data are ready, so complete daily bars for the current trading day can be collected.
  - Night sessions are assigned to the next trading day, do not affect today's daily bar completeness.
- **Weekend**: No collection.

### Trading Date Inference

- Night session quotes at 21:00 and later are assigned to the **next calendar day** as the trading day (`infer_trading_date`).
- Day session quotes: the trading day is the current natural day.

> Note: The first working day before a statutory holiday has no night session; the code has not yet connected to the DCE trading calendar. This situation requires manual skipping or future calendar check completion.

## Testing

```bash
python -m unittest discover -s tests -v
```

All tests use temporary directories and Mocks, do not access the real network, do not read or write formal data files.

## GitHub Workflow (Manual Trigger)

- Workflow: `.github/workflows/collect.yml`, trigger method is `workflow_dispatch` (manual).
- Trigger: NAS manually issues GitHub Actions command to execute, no scheduled automatic trigger.
- Concurrency control: `concurrency.group: pvc-collect`, `cancel-in-progress: false`, avoids push conflicts caused by concurrent runs.
- Push strategy: `git fetch + rebase origin/main`, push failure retries up to 3 times, 5 seconds interval between retries.

## Safety Conventions

- Writes use "temp file + atomic replace" (`rename`), avoiding half-finished output.
- Interface returns empty/`None` or validation failure raises exception and **does not modify** existing quote files.
- Workflow `git push` executes `git fetch + rebase` before push, failure retries up to 3 times, avoids push rejection caused by concurrent submissions.
- Each stream is independent, single stream failure does not affect other streams.

## Known Limitations

| Item | Description | Impact | Suggestion |
|------|-------------|--------|------------|
| Holiday calendar | The first working day before a statutory holiday has no night session; the code has not yet connected to the DCE trading calendar | Complete daily bars may be collected too early before holidays | Manual skip or complete calendar check later |
| `known_bad_dates` hardcoded | OHLC known anomaly dates (`2011-01-03`, `2020-08-06`) are hardcoded in code | Adding new anomaly dates requires code modification | Move to configuration file or environment variable |
| Data retention policy | Daily/minute CSV has no data retention period, grows indefinitely | Long-term operation causes repository bloat | Add policy to keep only recent N months of data |
| Comment language | Mixed Chinese and English comments | Does not affect functionality, but reading experience is inconsistent | Unify comment language |
| JSONL atomicity | JSONL append write has been changed to atomic replace, but a single corrupted line does not affect other lines | Partial snapshots may be lost in extreme cases | Acceptable, JSONL line independence feature |
