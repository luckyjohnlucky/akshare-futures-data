# Write Test B

This is experiment B, approximately 1000 characters in length.

The purpose of this test is to verify whether the write tool works correctly with medium-length content.

PVC futures contracts on the Dalian Commodity Exchange use the trading code "v" followed by a year-month suffix, such as v2501, v2505, and v2509. These represent the January, May, and September delivery months respectively. The continuous contract V0 is a composite indicator that rolls over between active contracts.

In the existing project, the fetch_pvc.py script collects three independent data streams for each symbol: real-time snapshots from the Sina HTTP API, 1-minute bars from akshare, and daily bars from akshare. Each stream writes to its own output file under the output/ directory. The daily bars use (symbol, trading_date) as the deduplication key, while the minute bars use (symbol, datetime).

The data storage design requires that each actual contract be saved independently, with no cross-year overwriting or merging. Historical data for delisted contracts must be permanently retained. The existing CSV format and field names must remain compatible.

For contract lifecycle management, the system needs to automatically discover newly listed contracts, include them in collection once listed, allow simultaneous collection of old and new contracts during the transition period, and stop collecting old contracts based on the exchange's actual last trading date.

The AKShare interface verification showed that ak.futures_zh_daily_sina works with specific contract codes like v2509, returning the full trading history for that contract. The minute bar interface ak.futures_zh_minute_sina also works, capped at 1023 rows per call. The Sina HTTP API only serves currently active contracts, returning empty strings for expired ones.

This test file is created under the .kilo/plans directory as a diagnostic test only. No source code or configuration files have been modified.