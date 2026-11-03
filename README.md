# akshare-futures-data

Collect historical daily and minute bars for nine Chinese commodity futures main continuous contracts (PVC/V0, PTA/TA0, Methanol/MA0, PP/PP0, L Plastic/L0, Soda Ash/SA0, Glass/FG0, Rebar/RB0, Hot Rolled Coil/HC0), perform quality validation, deduplication and merging, and output structured CSV.

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

1. **Minute bars**: Fetch AKShare 1-minute quote → `validate_minute_bars` validation → `separate_future_timestamps` filter bars after collection time (based on `Asia/Shanghai` timezone `collected_at`, 1-minute tolerance) → `update_minute_bars` merge history and atomically write to `output/{symbol}_minute_bars.csv`.
2. **Daily bars**: After day session close (15:00+, Monday to Friday) fetch AKShare daily bars → `validate_daily_bars` validation → `update_daily_bars` merge history and atomically write to `output/{symbol}_daily_bars.csv`.

### Stream Execution Mechanisms

#### Parallel Execution

Two data streams (minute bars, daily bars) are independent, executed using `ThreadPoolExecutor`. Each symbol's each stream is submitted as an independent task; total duration depends on the slowest individual task, not the sum of all tasks.

Expected speedup:
- After 15:00 (18 tasks): total duration reduced by about 80%-90%, speedup 6-7x
- Before 15:00 (9 tasks, daily bars skipped): total duration reduced by about 70%-80%, speedup 3-4x

Parallel execution safety: different symbols operate on different files, no race condition; good failure isolation, single stream failure does not affect others.

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
| `output/V0_daily_bars.csv` | PVC daily bars, merged and deduplicated by `(symbol, trading_date)`, sorted by date ascending. |
| `output/V0_minute_bars.csv` | PVC minute bars, merged and deduplicated by `(symbol, datetime)`, sorted by time ascending. |
| `output/TA0_daily_bars.csv` | PTA daily bars, merged and deduplicated by `(symbol, trading_date)`, sorted by date ascending. |
| `output/TA0_minute_bars.csv` | PTA minute bars, merged and deduplicated by `(symbol, datetime)`, sorted by time ascending. |
| `output/MA0_daily_bars.csv` | Methanol daily bars, merged and deduplicated by `(symbol, trading_date)`, sorted by date ascending. |
| `output/MA0_minute_bars.csv` | Methanol minute bars, merged and deduplicated by `(symbol, datetime)`, sorted by time ascending. |
| `output/PP0_daily_bars.csv` | PP daily bars, merged and deduplicated by `(symbol, trading_date)`, sorted by date ascending. |
| `output/PP0_minute_bars.csv` | PP minute bars, merged and deduplicated by `(symbol, datetime)`, sorted by time ascending. |
| `output/L0_daily_bars.csv` | Plastic daily bars, merged and deduplicated by `(symbol, trading_date)`, sorted by date ascending. |
| `output/L0_minute_bars.csv` | Plastic minute bars, merged and deduplicated by `(symbol, datetime)`, sorted by time ascending. |
| `output/SA0_daily_bars.csv` | Soda Ash daily bars, merged and deduplicated by `(symbol, trading_date)`, sorted by date ascending. |
| `output/SA0_minute_bars.csv` | Soda Ash minute bars, merged and deduplicated by `(symbol, datetime)`, sorted by time ascending. |
| `output/FG0_daily_bars.csv` | Glass daily bars, merged and deduplicated by `(symbol, trading_date)`, sorted by date ascending. |
| `output/FG0_minute_bars.csv` | Glass minute bars, merged and deduplicated by `(symbol, datetime)`, sorted by time ascending. |
| `output/RB0_daily_bars.csv` | Rebar daily bars, merged and deduplicated by `(symbol, trading_date)`, sorted by date ascending. |
| `output/RB0_minute_bars.csv` | Rebar minute bars, merged and deduplicated by `(symbol, datetime)`, sorted by time ascending. |
| `output/HC0_daily_bars.csv` | Hot Rolled Coil daily bars, merged and deduplicated by `(symbol, trading_date)`, sorted by date ascending. |
| `output/HC0_minute_bars.csv` | Hot Rolled Coil minute bars, merged and deduplicated by `(symbol, datetime)`, sorted by time ascending. |
| `output/minute_data_quality.jsonl` | Minute records excluded due to anomalies (e.g., `future_timestamp`) (global). |

## Quality Filtering Rules

- **Future timestamp (`future_timestamp`)**: `datetime > collected_at + 1 minute` (unified `Asia/Shanghai` timezone).
  - Newly collected data is filtered before merging.
  - After merging history, re-validated via `filter_future_anomalies` to avoid retaining anomalies left in old files.
  - Exception records are written as-is to `minute_data_quality.jsonl`, deduplicated by `(symbol, datetime)`; **original timestamps of exception records are not modified**.
- **Daily bar OHLC check**: `high >= max(open, close, low)` and `low <= min(open, close, high)`; unregistered anomalies refuse writing, known anomalies (`2011-01-03`, `2020-08-06`) are only marked `invalid_ohlc`.
- **Minute bar OHLC check**: Same logic as daily bars; anomalies directly refuse writing.
- **Volume / open interest**: Must be non-negative; missing values result in `None` for daily bar fields, minute bars are directly rejected.

## Supported Exchanges and Contracts

All nine varieties are China Dalian Commodity Exchange (DCE) main continuous contracts. The program directly uses AKShare's main continuous contract codes (e.g., `V0`, `TA0`, `MA0`, etc.), which automatically roll over, without manually constructing continuous series.

| Variety | AKShare Code | Exchange |
|---------|-------------|----------|
| PVC | V0 | DCE |
| PTA | TA0 | DCE |
| Methanol | MA0 | DCE |
| PP | PP0 | DCE |
| Plastic | L0 | DCE |
| Soda Ash | SA0 | DCE |
| Glass | FG0 | DCE |
| Rebar | RB0 | DCE |
| Hot Rolled Coil | HC0 | DCE |

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
| Minute data rolling window | AKShare minute interface returns rolling window (~1023 records), not full history | Long-term operation loses early minute data | Accept AKShare limitation, add separate archival if needed |
