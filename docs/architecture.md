# Architecture

Status: current
Version: 1.0
Last updated: 2026-11-05

## Overview

`akshare-futures-data` collects historical daily and minute bars for Chinese commodity
futures main continuous contracts from AKShare (Sina Finance source), validates them,
deduplicates, merges with history, and writes structured CSVs to `output/`.

## Components

| Component | File | Responsibility |
|-----------|------|----------------|
| Collector | `fetch_pvc.py` (1132 lines) | Fetch, validate, merge, write. Entry point: `python fetch_pvc.py`. |
| V0 merge tool | `merge_v0_data.py` | One-off merge of local V0 data with `origin/main` data (remote-priority). Not part of the main collection flow. |
| Tests | `tests/` (5 `.py` + 1 `.sh` + `conftest.py`) | 50 `def test_` cases (Python) + 8 Shell scenarios. |
| Workflow | `.github/workflows/collect.yml` | GitHub Actions runner: install deps, run collector, commit CSVs, push. |

## Data flow

```
AKShare
  ├─ ak.futures_zh_minute_sina(symbol, period="1")   → minute bars
  ├─ ak.futures_zh_daily_sina(symbol)                → daily bars
  └─ ak.futures_index_ccidx(symbol='中证商品期货指数') → H11061 index daily bars
        │
        ▼
  validate_*_bars()  (field presence, timestamp/date validity, duplicates,
                      non-positive OHLC, OHLC logic, non-negative volume/settle)
        │
        ▼
  separate_future_timestamps()  (filter bars newer than collected_at + 1 min,
                                 record to minute_data_quality.jsonl)
        │
        ▼
  update_*_bars()  (merge by (symbol, datetime) / (symbol, trading_date),
                    atomic write via temp file + rename)
        │
        ▼
  output/{symbol}_{daily,minute}_bars.csv
```

## Concurrency model

- `fetch_pvc.py` `__main__` submits one task per contract per stream to a
  `ThreadPoolExecutor(max_workers=len(tasks))`.
- 19 tasks total: 9 commodity contracts × 2 streams + H11061 daily stream
  (H11061 has no minute stream).
- Streams are independent; a single stream failure does not affect others, and
  different symbols write to different files (no file-level race).

> Confirmed: 19 tasks, `ThreadPoolExecutor`, `max_workers=len(tasks)`.
> Unverified: the 6–7x / 3–4x speedup figures quoted in README — no reproducible benchmark exists.

## Failure semantics (known limitation)

- Each task's `except Exception` only logs via `logger.error`; it does not re-raise
  or return a failure state. `future.result()` therefore cannot detect a failed
  task, and the process can exit 0 with partial data missing.
- This is recorded as audit issue P0-2 (V2.3.2). Not fixed here — out of scope for
  documentation governance.

## Retry semantics

- `_retryable_call` retries only `requests.RequestException` (exponential backoff,
  max 3 attempts). AKShare's own exceptions (`NetworkError`, `APIError`,
  `DataParsingError`, `RateLimitError`) are not `requests.RequestException` and are
  not retried by this layer. AKShare has its own internal retry layer; the two are
  distinct.
- Recorded as audit issue P0-3 (V2.3.2). Not fixed here.

## Output layout

`output/` holds 20 CSV files: 9 commodity daily + 9 commodity minute + H11061
index daily + a 0-byte H11061 minute placeholder. See `docs/data.md` for field
descriptions.

## Blind spot in V0 merge script

The `merge_v0_data.py` script merges local V0 data with remote data from
`origin/main`. It performs the merge operation using remote‑priority semantics,
but it does NOT check the `quality_status` field when applying the merge.
Consequently, when the same `(symbol, trading_date)` key exists on both sides,
the remote record is selected unconditionally; if that remote record carries
`invalid_ohlc`, it can silently override a local record whose `quality_status` is
`valid`. The `quality_status` field is not validated or filtered during merge.