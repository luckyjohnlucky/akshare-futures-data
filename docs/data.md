# Data

Status: current
Version: 1.0
Last updated: 2026-11-05

## Data sources

All data comes from AKShare, backed by Sina Finance HTTP endpoints.

| Stream | AKShare call | Output |
|--------|--------------|--------|
| Minute bars | `ak.futures_zh_minute_sina(symbol=symbol, period="1")` | `output/{symbol}_minute_bars.csv` |
| Daily bars | `ak.futures_zh_daily_sina(symbol=symbol)` | `output/{symbol}_daily_bars.csv` |
| H11061 index daily | `ak.futures_index_ccidx(symbol='中证商品期货指数')` | `output/H11061_index_daily.csv` |

AKShare version requirement: `>=1.20,<2.0` (from `requirements.txt`).

## Contracts

10 entries in `ACTIVE_CONTRACTS`:

| Symbol | Variety | Exchange | Has minute | Has daily |
|--------|---------|----------|-----------|-----------|
| V0 | PVC | DCE | yes | yes |
| TA0 | PTA | CZC | yes | yes |
| MA0 | Methanol | CZC | yes | yes |
| PP0 | PP | DCE | yes | yes |
| L0 | Plastic | DCE | yes | yes |
| SA0 | Soda Ash | CZC | yes | yes |
| FG0 | Glass | CZC | yes | yes |
| RB0 | Rebar | SHFE | yes | yes |
| HC0 | Hot Rolled Coil | SHFE | yes | yes |
| H11061 | 中证商品期货指数 | — | no | yes |

Codes are main continuous contracts; AKShare rolls them automatically.

## Daily bars fields

`date, open, high, low, close, volume, hold, settle, quality_status, source, collected_at`

- `settle` may be `0` for missing; written as `None`.
- `quality_status`: `valid` / `invalid_ohlc`.
- Known anomaly dates `2011-01-03` and `2020-08-06` are hardcoded in
  `known_bad_dates`; OHLC anomalies on those dates are marked `invalid_ohlc`
  rather than refused. Unregistered OHLC anomalies refuse writing.

## Minute bars fields

`datetime, open, high, low, close, volume, hold, quality_status, source, collected_at`

- Same OHLC logic as daily bars; anomalies directly refuse writing.
- Volume/hold must be non-negative; missing values reject the minute record.

## H11061 index daily fields

`symbol, name, index_code(100001.CCI), trading_date, close, settle, change,
pct_change, quality_status, source, collected_at`

- No OHLC / volume / hold fields (an index has no volume or open interest).
- `quality_status`: `valid` / `invalid` (index-specific, not `invalid_ohlc`).
- Incremental update by `trading_date`; new records overwrite old ones; empty
  results or interface errors do not write and do not overwrite history.

## Merge / dedup keys

- Daily: `(symbol, trading_date)` — old records overwritten by new data, rest kept.
- Minute: `(symbol, datetime)` — old records keep original `collected_at`, only
  quote fields updated.
- Writes use temp file + atomic `rename`.

## Quality log

`output/minute_data_quality.jsonl` records minute bars excluded by anomaly
(e.g. `future_timestamp`), deduplicated by `(symbol, datetime)`. Original
timestamps of exception records are not modified.

**Confirmed absence**: this file does not currently exist. Absence does not prove
the filter never ran — it may simply mean no future-timestamp anomalies were
produced in the runs since the log was last present. Recorded as unverified
item U-4 in audit V2.3.2.

## Trading-day rules

- Daily collection runs only when `is_after_market_close()` is true (after 15:00
  Beijing time, Monday–Friday). No collection on weekends.
- Night sessions (21:00–23:00) are assigned to the next trading day and do not
  affect today's daily-bar completeness.
- Known limitation: the first working day before a statutory holiday has no
  night session; the code does not yet consult the DCE trading calendar, so
  complete daily bars may be collected too early before holidays.

## Data counts (confirmed)

| File | Data rows |
|------|-----------|
| `output/V0_daily_bars.csv` | 4230 |
| `output/V0_minute_bars.csv` | 2396 |
| `output/H11061_index_daily.csv` | 969 |
| `output/H11061_minute_bars.csv` | 0 (0-byte placeholder) |

Historical figures 4229 (daily) and 2044 / 2058 (minute) appear in
`merge_v0_data.py` assertions and `pvc-final-review.md` and conflict with the
current counts. The discrepancy is unexplained; current counts are confirmed but
do not constitute a completeness acceptance. See audit V2.3.2 §4.2–§4.3.

## Known data-quality issue

Two V0 daily records carry `quality_status = invalid_ohlc` despite OHLC logic
violations:

| Date | Anomaly |
|------|---------|
| 2011-01-03 | high < open |
| 2020-08-06 | low > close |

Both records still exist in the historical CSV `output/V0_daily_bars.csv` and
still carry `quality_status = invalid_ohlc`. The `known_bad_dates` recognition in
source code does not imply the historical CSV has been reprocessed. Historical
data repair and re-verification remain open (audit issue P1-4, V2.3.2 §4.5).
No data file is modified by this governance pass.

Recorded as audit issue P1-4 (V2.3.2). Not fixed here — out of scope.

## Downstream consumption contract

This contract is a required future behavior. The current `csv_to_records()`
implementation in `fetch_pvc.py` returns every CSV row unchanged and does not
filter by `quality_status`.

When reading `output/V0_daily_bars.csv` for analysis or reporting, downstream
consumers MUST treat only rows with `quality_status == "valid"` as usable. Rows
with `quality_status = invalid_ohlc`, or any other non-`valid` status, MUST be
excluded before calculation. The `quality_status != "valid"` test is a
defensive rule: it excludes the currently known `invalid_ohlc` status and any
future non-`valid` status.

Rolling windows and time-series aggregations MUST NOT concatenate data across an
`invalid_ohlc` record. A window must end before the invalid record, and a new
window may begin only after it. The invalid record itself MUST NOT be included
in either window.

Future modules (API, metrics, reporting) added to this repository must implement
this filtering at their data intake points and provide corresponding tests.