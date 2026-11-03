# Write Test C

This is experiment C, approximately 3000 characters in length.

The purpose of this test is to verify whether the write tool works correctly with longer content.

## Project Overview

The akshare-futures-data project collects historical daily and minute bars for PVC futures contracts, performs quality validation, deduplication and merging, and outputs structured CSV and real-time snapshot JSONL files. The project currently supports two symbols: V0 (the PVC continuous main contract) and V2701 (the January 2027 specific contract).

## Data Collection Streams

The fetch_pvc.py script implements three independent data streams using ThreadPoolExecutor for parallel execution:

1. Real-time snapshots from the Sina HTTP API, written to JSONL files with (symbol, source_date, source_time) as the deduplication key.

2. Minute bars from ak.futures_zh_minute_sina with period="1", validated by validate_minute_bars, filtered by separate_future_timestamps, and merged by update_minute_bars with (symbol, datetime) as the deduplication key.

3. Daily bars from ak.futures_zh_daily_sina, collected only after 15:00 Beijing time on weekdays, validated by validate_daily_bars, and merged by update_daily_bars with (symbol, trading_date) as the deduplication key.

## Quality Validation

The validate_daily_bars function checks required fields, date validity and deduplication, positive OHLC values and logical relationships, non-negative settle prices (allowing 0 for missing), and non-negative volume and open interest. Known anomaly dates (2011-01-03 and 2020-08-06) are marked as invalid_ohlc rather than causing rejection. Unregistered OHLC anomalies cause the write to be refused.

The validate_minute_bars function checks required fields, invalid timestamps, duplicate timestamps, non-positive OHLC, OHLC logical relationships, and non-negative volume and open interest. Any anomaly causes the write to be refused.

## Future Timestamp Filtering

The separate_future_timestamps function uses collected_at plus a 1-minute tolerance as the threshold, filtering out bars later than the threshold and logging them to the quality log. The filter_future_anomalies function re-validates merged data to clean up residual anomalies from old files. Original timestamps of exception records are never modified.

## Storage Design

Each contract's data is stored in separate files:
- output/{symbol}_daily_bars.csv for daily bars
- output/{symbol}_minute_bars.csv for minute bars
- output/{symbol}_realtime_snapshots.jsonl for real-time snapshots

The output/ directory also contains minute_data_quality.jsonl for anomaly records.

## Contract Lifecycle Requirements

The target rules for the new feature are:
- Only track January, May, and September contracts long-term
- Automatically discover newly listed contracts
- Include new contracts in collection automatically after listing
- Allow simultaneous collection of old and new contracts during transition
- Stop old contract collection based on exchange actual last trading date
- Permanently retain historical data for delisted contracts
- Do not rely on annual manual code modifications

## AKShare Interface Findings

The akshare version is 1.20.0. The futures_zh_daily_sina function works with specific contract codes, returning the full trading history. The minute bar interface works with periods 1, 5, 15, 30, and 60 minutes, capped at 1023 rows. The Sina HTTP API only serves currently active contracts. There is no single akshare function that returns a complete listing of all PVC contracts with last trading day information.

## GitHub Actions Workflow

The collect.yml workflow uses workflow_dispatch for manual triggering. It installs dependencies, runs fetch_pvc.py, and commits data changes with retry logic for push failures.

This test file is created under the .kilo/plans directory as a diagnostic test only. No source code or configuration files have been modified. The content above is intentionally longer than previous tests to evaluate write tool behavior with larger payloads.