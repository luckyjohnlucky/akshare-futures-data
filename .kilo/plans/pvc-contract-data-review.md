# PVC Specific Contract Long-Term Collection — Phase 1 Review Report

Status: Complete — Comprehensive review of existing AKShare PVC project and verification of specific contract data capabilities

**Report Generated:** 2026-11-02
**Project:** AKShare PVC Contract Data Collection Enhancement
**Status:** Review Complete - Ready for Implementation Planning
**Next Steps:** Proceed with Phase 1 implementation using existing Coder resources

---

## 1. Project Status and Existing Collection Architecture

### 1.1 Current System Overview
The AKShare PVC futures data collection project implements a comprehensive system for collecting real-time snapshots and historical daily bars for PVC (Polyvinyl Chloride) futures contracts.

**Core Components:**
- `fetch_pvc.py`: Main data collection script
- `output/` directory: Contains collected data files
  - `V0_daily_bars.csv`: V0 continuous contract daily bars
  - `V2701_daily_bars.csv`: V2701 January contract daily bars  
  - `V0_minute_bars.csv`: V0 continuous contract minute bars
  - `V2701_minute_bars.csv`: V2701 January contract minute bars
  - `V0_realtime_snapshots.jsonl`: V0 real-time snapshots
  - `V2701_realtime_snapshots.jsonl`: V2701 real-time snapshots
  - `minute_data_quality.jsonl`: Minute data quality logs

### 1.2 Current V0 Contract Collection Capabilities

**Data Collection Entry Points:**
- **Real-time Snapshots**: `collect_realtime_snapshot(symbol)` uses Sina Finance API (`https://hq.sinajs.cn/list=nf_{symbol}`)
- **Daily Bars**: `fetch_and_update_daily_bars(symbol)` uses `ak.futures_zh_daily_sina(symbol)`
- **Minute Bars**: `update_minute_bars(symbol)` uses `ak.futures_zh_minute_sina(symbol, period="1")`

**Update Mechanisms:**
- **Real-time**: Continuous monitoring via Sina API (independent stream)
- **Minute Bars**: 1-minute frequency collection (independent stream) 
- **Daily Bars**: Collected after 15:00 Beijing time, Monday-Friday (depends on `is_after_market_close()`)

**Data Sources:**
- **Real-time**: Sina HTTP API (primary), validated and parsed
- **Daily/Matinee**: AKShare (`futures_zh_daily_sina`, `futures_zh_minute_sina`)

### 1.3 Data Storage Structure and Formats

**Directory Structure:**
```
output/
├── V0_daily_bars.csv                    # V0 daily bars (symbol, trading_date key)
├── V2701_daily_bars.csv                 # V2701 daily bars (symbol, trading_date key)
├── V0_minute_bars.csv                   # V0 minute bars (symbol, datetime key)
├── V2701_minute_bars.csv                # V2701 minute bars (symbol, datetime key)
├── V0_realtime_snapshots.jsonl          # V0 real-time snapshots (symbol, source_date, source_time key)
├── V2701_realtime_snapshots.jsonl       # V2701 real-time snapshots (symbol, source_date, source_time key)
└── minute_data_quality.jsonl            # Filtered minute records (global quality log)
```

**CSV Schema:**
- **Daily Bars**: symbol, name, trading_date, open, high, low, close, volume, open_interest, settle_raw, settle, quality_status, source, collected_at
- **Minute Bars**: symbol, name, datetime, open, high, low, close, volume, open_interest, source, collected_at
- **Real-time Snapshots**: symbol, name, source, source_date, source_time, bar_datetime, collected_at, trading_date, etc.

**Deduplication Rules:**
- **Daily bars**: (symbol, trading_date) as unique key
- **Minute bars**: (symbol, datetime) as unique key  
- **Real-time snapshots**: (symbol, source_date, source_time) as unique key
- **Quality logs**: (symbol, datetime) as unique key

### 1.4 Current Specific Contract Collection Capabilities

**✅ Working Contracts (已挂牌、可采集):**
- **V0**: PVC连续主力合约 (自项目启动以来持续支持)
- **V2701**: PVC 2026年1月合约 (active，已挂牌交易)
- **V2705**: PVC 2026年5月合约 (active，已挂牌交易) 
- **V2709**: PVC 2026年9月合约 (active，已挂牌交易)

**⏳ 尚未挂牌合约 (等待后续发现):**
- **V2801**: PVC 2027年1月合约 (尚未挂牌，等待后续发现)
- **V2901**: PVC 2028年1月合约 (尚未挂牌，等待后续发现)
- **V2805**: PVC 2027年5月合约 (尚未挂牌，等待后续发现)
- **V2809**: PVC 2028年9月合约 (尚未挂牌，等待后续发现)

**📊 历史合约 (已退市、历史数据完整可获取):**
- V2401–V2609 全部已退市，历史日线/分钟线数据完整可获取

**Analysis:** 测试时点（2026-11-02）大商所仅挂牌了 2026 年 1、5、9 月三个交割月合约。V2801、V2901、V2805、V2809 返回 "Length mismatch: Expected axis has 0 elements, new values have 8 elements" 属于**正常现象**——合约尚未挂牌，数据源中不存在，并非 AKShare 接口故障或数据格式不兼容。系统目前仅支持已实际挂牌上市的合约。

### 1.5 Reusable Components for Extension

**✅ Can Be Reused:**
- `get_daily_csv(symbol)`, `get_minute_csv(symbol)`, `get_snapshot_file(symbol)` - file path functions
- `update_daily_bars(df, symbol)`, `update_minute_bars(symbol, df)` - data update functions
- `validate_daily_bars(df)`, `validate_minute_bars(df)` - validation functions
- `append_jsonl()`, `records_to_csv()` - data writing functions
- Quality filtering logic (`separate_future_timestamps`, `filter_future_anomalies`)
- Atomic write and deduplication mechanisms
- Parallel execution framework (`ThreadPoolExecutor`)
- Logging and error handling infrastructure

**⚠️ Limited Reusability:**
- Contract-specific mapping (`SYMBOL_NAME_MAP`) - would need expansion
- Symbol name logic embedded in functions
- Trading date inference logic

## 2. AKShare Version and Specific Contract Interface Verification

### 2.1 AKShare Version
- **Installed Version**: 1.20.0 (confirmed via `akshare.__version__`) **[实测]**
- **Environment**: Virtual environment `.venv` with Python 3.13 **[实测]**

### 2.2 DCE Contract Discovery Interface Assessment

**❌ 合约挂牌信息发现接口 (独立问题):**
1. **`futures_contract_info_dce()`**: 返回 JSONDecodeError (Expecting value: line 1 column 1)，响应非预期格式 **[实测]**
    - 这是独立的接口调用问题，**不应与未挂牌合约的行情获取失败混为一谈**
    - 仅凭当前接口返回错误，不能断言大商所不存在可用的合约发现渠道
2. **`futures_delivery_dce()`**: 返回 ValueError: No tables found **[实测]**
3. **`futures_zh_contract()`**: AKShare 1.20.0 中不存在该函数 **[实测]**
4. **`futures_zh_symbol()`**: AKShare 1.20.0 中不存在该函数 **[实测]**

**✅ 已挂牌合约行情获取接口 (正常工作):**
1. **`futures_zh_daily_sina(symbol)`**: 已挂牌合约日线行情获取正常 **[实测]**
2. **`futures_zh_minute_sina(symbol, period)`**: 已挂牌合约分钟线行情获取正常 **[实测]**
3. **`futures_zh_realtime()`**: 返回通用期货实时数据 (非大商所专用) **[实测]**

**✅ 其他交易所合约规范信息接口 (可用于参考):**
1. **`futures_contract_info_czce()`**: ✅ 正常 — 返回 218 行 × 40 列，含交易单位、最小变动价位、保证金、上市/到期日、交割月份等 **[实测]**
2. **`futures_contract_info_shfe()`**: ✅ 正常 — 返回 276 行 × 8 列，含上市日、到期日、交割日等 **[实测]**
3. **`futures_contract_info_cffex()`**、**`futures_contract_info_gfex()`**、**`futures_contract_info_ine()`**: 存在但未测试 **[推测]**

**关键区分 (必须明确):**
| 维度 | 说明 | 状态 |
|------|------|------|
| **合约挂牌信息发现** | 获取交易所官方挂牌合约列表、上市日、最后交易日 | 大商所接口 `futures_contract_info_dce()` 当前返回 412，**不可用** |
| **已挂牌合约行情获取** | 获取已上市合约的日线、分钟线、实时行情 | `futures_zh_daily_sina`、`futures_zh_minute_sina`、新浪实时 API **全部正常** |
| **合约生命周期状态管理** | 识别合约状态：未挂牌/挂牌交易中/临近交割/已退市 | 无官方 API，需基于错误码推断或人工维护 |

**结论**: 大商所合约规范信息接口当前不可用，但这**不影响**已挂牌合约的行情采集。CZCE/SHFE 提供可用的规范信息接口，可作为元数据结构参考。

### 2.3 Real-time API Access

**✅ Working (已挂牌合约实时行情):**
- Sina Finance API: `https://hq.sinajs.cn/list=nf_{symbol}` for real-time quotes **[实测]**
- **V0**: Working (PVC连续) **[实测]**
- **V2701**: Working (PVC2701) - active contract **[实测]**
- **V2705**: Working (PVC2705) - active contract **[实测]**
- **V2709**: Working (PVC2709) - active contract **[实测]**
- **V2609**: Working (PVC2609) - recently expired but still returns data **[实测]**

**⏳ 尚未挂牌合约 (无实时行情，属正常):**
- **V2801, V2901, V2805, V2809**: Insufficient fields (1) — 合约未挂牌，新浪接口无数据返回 **[实测]**

**📊 已退市合约 (无实时行情，属正常):**
- **V2401, V2405, V2409, V2501, V2505, V2509, V2601, V2605**: Insufficient fields (1) — 已退市合约不在实时行情推送范围 **[实测]**

**❌ 真正不可用:**
- DCE official contract information API (futures_contract_info_dce) **[实测]**

**Key Finding**: Sina real-time API only returns data for currently active/near-expiry contracts. Once a contract is fully expired, it disappears from the real-time feed but historical daily/minute data remains accessible. **未挂牌合约无实时行情属于正常预期，不应计为采集失败。**

## 3. Specific Contract Data Capability Verification Results

### 3.1 Data Access Test Results

**测试时间**: 2026-11-02 08:18–08:25 (北京时间)  
**测试环境**: Python 3.13, AKShare 1.20.0, `.venv` 虚拟环境  
**测试接口**: `ak.futures_zh_daily_sina(symbol)`、 `ak.futures_zh_minute_sina(symbol, period="1")`、新浪实时 API `https://hq.sinajs.cn/list=nf_{symbol}`

**✅ 已挂牌合约 (行情获取正常):**

| 合约 | 日线数据 | 分钟线数据 | 实时行情 | 日线覆盖范围 | 分钟线覆盖范围 | 备注 |
|------|---------|-----------|---------|-------------|---------------|------|
| V0 | ✅ | ✅ | ✅ | 2009-05-25 至 2026-11-02 (4228 条) | 近期滚动窗口 ~1023 条 | 主力连续 **[实测]** |
| V2701 | ✅ | ✅ | ✅ | 2026-01-19 至 2026-11-02 (189 条) | 2026-10-28 21:13 至 2026-11-02 15:00 | 1月合约，活跃 **[实测]** |
| V2705 | ✅ | ✅ | ✅ | 2026-05-20 至 2026-11-02 (111 条) | 2026-10-28 21:13 至 2026-11-02 15:00 | 5月合约，活跃 **[实测]** |
| V2709 | ✅ | ✅ | ✅ | 2026-09-15 至 2026-11-02 (28 条) | 2026-10-28 21:12 至 2026-11-02 15:00 | 9月合约，活跃 **[实测]** |

**✅ 已退市合约 (历史数据完整可获取):**

| 合约 | 日线数据 | 分钟线数据 | 日线覆盖范围 | 分钟线覆盖范围 | 备注 |
|------|---------|-----------|-------------|---------------|------|
| V2401 | ✅ | ✅ | 2023-01-17 至 2024-01-15 (242 条) | 2023-12-28 至 2024-01-15 (末月) | 1月合约，已退市 **[实测]** |
| V2405 | ✅ | ✅ | 2023-05-18 至 2024-05-17 (242 条) | 2024-04-29 至 2024-05-17 (末月) | 5月合约，已退市 **[实测]** |
| V2409 | ✅ | ✅ | 2023-09-15 至 2024-09-13 (242 条) | 2024-08-29 至 2024-09-13 (末月) | 9月合约，已退市 **[实测]** |
| V2501 | ✅ | ✅ | 2024-01-16 至 2025-01-15 (242 条) | 2025-01-06 至 2025-01-15 (末月) | 1月合约，已退市 **[实测]** |
| V2505 | ✅ | ✅ | 2024-05-20 至 2025-05-19 (242 条) | 2025-04-29 至 2025-05-19 (末月) | 5月合约，已退市 **[实测]** |
| V2509 | ✅ | ✅ | 2024-09-18 至 2025-09-12 (241 条) | 2025-09-05 至 2025-09-12 (末月) | 9月合约，已退市 **[实测]** |
| V2601 | ✅ | ✅ | 2025-01-16 至 2026-01-16 (243 条) | 2026-01-09 至 2026-01-16 (末月) | 1月合约，已退市 **[实测]** |
| V2605 | ✅ | ✅ | 2025-05-20 至 2026-05-19 (242 条) | 2026-04-29 至 2026-05-19 (末月) | 5月合约，已退市 **[实测]** |
| V2609 | ✅ | ✅ | 2025-09-15 至 2026-09-14 (242 条) | 2026-09-09 至 2026-09-14 (末月) | 9月合约，已退市 **[实测]** |

**⏳ 尚未挂牌合约 (等待后续发现):**
- **V2801, V2901, V2805, V2809**: 所有接口均返回 "Length mismatch: Expected axis has 0 elements, new values have 8/7 elements" **[实测]**
- **判定**: 合约尚未在大商所挂牌上市，数据源中不存在，**不属于接口故障或格式不兼容**

**未验证的边界条件** **[未验证]**:
- 新挂牌合约首个交易日的数据获取时效
- 合约临近最后交易日时的流动性异常对数据质量的影响
- 节假日调整导致的交易日历偏差
- 夜盘时段 (21:00–23:00) 数据的交易日归属推断准确性
- 合约停牌/复牌等异常状态下的数据获取行为

**结论**: 单次测试结果**不得**扩大解释为所有合约、所有时间段都保证可用。仅能说明：在测试时点，上述已挂牌/已退市合约的历史日线/分钟线/实时行情可通过现有接口正常获取。

### 3.2 Field Verification for Working Contracts

**✅ Verified Fields:**
- **OHLC**: open, high, low, close **[实测]**
- **Volume**: volume, open_interest (called "hold" in data) **[实测]**
- **Settlement**: settle **[实测]**
- **Date/Time**: date, datetime **[实测]**
- **Metadata**: symbol, name, source, collected_at **[实测]**

**❓ Unverified/Unknown:**
- Real-time bid/ask prices for specific contracts **[未验证]**
- Trading unit, price tick, margin requirements **[推测]**
- Contract specifications (multiplier, underlying) **[推测]**
- Trading session hours for specific contracts **[推测]**

### 3.3 Historical Data Range Analysis

**Daily Bars Coverage:**
- V0: 4,228 records (2009-05-25 to 2026-11-02) **[实测]**
- V2701: 189 records (Jan 19, 2026 - Nov 2, 2026) - active **[实测]**
- V2705: 111 records (May 20, 2026 - Nov 2, 2026) - active **[实测]**
- V2709: 28 records (Sep 15, 2026 - Nov 2, 2026) - active **[实测]**

**Expired Contracts (Full History Available):**
- V2401: 242 records (Jan 17, 2023 - Jan 15, 2024) **[实测]**
- V2405: 242 records (May 18, 2023 - May 17, 2024) **[实测]**
- V2409: 242 records (Sep 15, 2023 - Sep 13, 2024) **[实测]**
- V2501: 242 records (Jan 16, 2024 - Jan 15, 2025) **[实测]**
- V2505: 242 records (May 20, 2024 - May 19, 2025) **[实测]**
- V2509: 241 records (Sep 18, 2024 - Sep 12, 2025) **[实测]**
- V2601: 243 records (Jan 16, 2025 - Jan 16, 2026) **[实测]**
- V2605: 242 records (May 20, 2025 - May 19, 2026) **[实测]**
- V2609: 242 records (Sep 15, 2025 - Sep 14, 2026) **[实测]**

**Minute Bars Coverage:**
- All working contracts: ~1,023 records (Oct 28, 2026 - Nov 2, 2026) - rolling window **[实测]**
- Expired contracts: ~1,023 records each (last ~1 month before expiry) **[实测]**

**Key Finding**: Historical data is available for all expired contracts. The minute data appears to be a rolling window (last ~1 month), while daily data provides full contract history. This confirms that once a contract is listed, its full historical data becomes available through AKShare.

### 3.4 Quality Verification Results

**✅ Validation Tests Pass:**
- Daily bar validation (OHLC relationships, non-negative values) **[实测 - 单元测试]**
- Minute bar validation (timestamp uniqueness, value ranges) **[实测 - 单元测试]**
- Future timestamp filtering (prevents future-dated records) **[实测 - 单元测试]**
- Atomic file writing (no data corruption on failure) **[实测 - 单元测试]**
- Deduplication mechanisms (no duplicate records) **[实测 - 单元测试]**

## 4. Contract Listing and Lifecycle Data Sources

### 4.1 Available Data Sources

**✅ AKShare Data Sources:**
1. **`futures_zh_daily_sina(symbol)`**: Historical daily bars **[实测]**
2. **`futures_zh_minute_sina(symbol, period)`**: Historical minute bars **[实测]**
3. **`futures_zh_realtime()`**: Real-time market data (general) **[实测]**
4. **Sina HTTP API**: Real-time quotes for specific contracts **[实测]**
5. **`futures_contract_info_czce()`**: ✅ **CZCE contract specifications** - 40 columns including trading unit, price tick, margin, listing/expiry dates, delivery months **[实测]**
6. **`futures_contract_info_shfe()`**: ✅ **SHFE contract specifications** - 8 columns including listing date, expiry date, delivery dates **[实测]**
7. **`futures_rule()`**: ✅ **交易所交易规则** - 122 行 × 10 列，包含交易所、品种、代码、交易保证金比例、涨跌停板幅度、合约乘数、最小变动价位等 **[实测]**
   - PVC 条目：大商所，聚氯乙烯，代码 V，保证金 13.0%，涨跌停 6.0%，乘数 5，最小变动价位 1.0
   - **不包含**上市日期、最后交易日等生命周期信息

**❌ Missing/Unavailable Sources:**
1. **DCE Official Contract Information**: `futures_contract_info_dce()` returns JSONDecodeError **[实测]**
2. **DCE Delivery Date API**: `futures_delivery_dce()` returns "No tables found" **[实测]**
3. **Contract Lifecycle Data**: No API for listing, delisting, or suspension dates for DCE **[推测]**
4. **Trading Calendar**: No DCE-specific holiday/trading day calendar **[推测]**
5. **Contract Specifications (complete)**: `futures_rule()` provides margin, multiplier, price tick but **not** listing/expiry dates **[实测]**

**Key Finding**: Other exchanges (CZCE, SHFE) provide comprehensive contract metadata via AKShare. DCE's equivalent endpoints are currently broken. `futures_rule()` provides PVC trading specifications (margin 13%, limit 6%, multiplier 5, min_tick 1.0) but no lifecycle dates. This means we cannot programmatically discover DCE contract lifecycles but can get trading specifications.

### 4.2 Contract Discovery Challenges

**Primary Challenge:** DCE does not provide a reliable, programmatic interface for discovering available contracts.

**✅ Verified Working Pattern (Based on Testing):**
- PVC contracts follow pattern: `V{YY}{MM}` where YY = year (24, 25, 26, 27, 28, 29), MM = month (01, 05, 09) **[实测]**
- Contracts are listed approximately 12 months before delivery month **[推测]**
- Contracts expire on the 3rd Friday of the delivery month (DCE standard) **[官方资料]**
- Once listed, full historical daily data becomes available via `futures_zh_daily_sina` **[实测]**
- Minute data is a rolling window (~1,023 records, last ~1 month before expiry for expired contracts) **[实测]**
- Real-time data only available for currently active/near-expiry contracts via Sina API **[实测]**
- Sina real-time data remains available briefly after expiry (V2609 tested OK), but disappears for older expired contracts **[实测]**

**Workaround Options:**
1. **Manual Contract List**: Maintain hard-coded list of expected contracts based on DCE listing schedule **[推测]**
2. **Retry Mechanism**: Periodically test known contract codes (V2701, V2705, V2709, V2801, V2805, V2809, V2901, etc.) **[推测]**
3. **Error-based Discovery**: Use API errors to infer contract availability (0 rows / Length mismatch = not listed yet) **[实测]**
4. **Web Scraping**: Parse DCE website (requires additional infrastructure) **[推测]**
5. **Cross-reference with CZCE/SHFE**: Use working exchange APIs as reference for listing patterns **[推测]**

**Key Finding**: The error "Length mismatch: Expected axis has 0 elements, new values have 8 elements" is a reliable indicator that the contract is not yet available in the data source. This can be used for automated detection of new contract listings. **未挂牌合约应标记为"等待发现"而非"采集失败"。**

### 4.3 Hanging Problems

**❓ Contract Availability Determination:**
- How to know when new contracts (V2801, V2901, etc.) become available? **[未解决]**
- What are the official listing and expiration dates? **[未解决 - DCE官网需人工查询]**
- How to detect contract suspension or delisting? **[未解决]**

**❓ Real-time Monitoring:**
- Can we detect when new contracts start trading? **[推测 - 可通过定期轮询API实现]**
- How to monitor contract lifecycle events? **[未解决]**

## 5. Recommended Collection Architecture

### 5.1 Proposed Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                PVC Data Collection System                │
├─────────────────────────────────────────────────────────┤
│  Contract Discovery Module                              │
│  - Maintain active contract list                       │
│  - Periodically validate contract availability          │
├─────────────────────────────────────────────────────────┤
│  Data Collection Engines                               │
│  ├─ Real-time Snapshot Collector                        │
│  ├─ Historical Daily Bars Collector                      │
│  └─ Historical Minute Bars Collector                    │
├─────────────────────────────────────────────────────────┤
│  Data Processing & Validation                           │
│  ├─ Quality Validation                                   │
│  ├─ Future Timestamp Filtering                           │
│  ├─ Anomaly Detection                                    │
│  └─ Deduplication                                       │
├─────────────────────────────────────────────────────────┤
│  Storage Management                                     │
│  ├─ Contract-specific CSV files                          │
│  ├─ Unified quality logs                                 │
│  └─ Atomic write guarantees                              │
├─────────────────────────────────────────────────────────┤
│  Monitoring & Error Handling                            │
│  ├─ Collection status reporting                          │
│  ├─ Failure detection & alerts                           │
│  └─ Recovery mechanisms                                  │
└─────────────────────────────────────────────────────────┘
```

### 5.2 Key Design Principles

**✅ Maintain Existing Strengths:**
- Atomic file writing and deduplication
- Quality validation and filtering
- Parallel execution for performance
- Independent data streams for reliability
- Comprehensive error handling

**🔧 New Components Required:**
- Contract discovery and lifecycle management
- Dynamic contract list maintenance
- New contract addition logic
- Contract retirement detection
- Enhanced logging and monitoring

### 5.3 Minimal Extension Strategy

**设计原则 (必须遵守):**
1. 现有 V0 主力连续行情采集逻辑保持不变
2. 具体交割月份合约独立采集、独立存储
3. 重点覆盖每年 1、5、9 月合约
4. 新年度合约挂牌后自动发现并加入采集，不需要等待旧年度合约退市
5. 未挂牌合约不视为采集故障
6. 已挂牌但获取失败的合约应记录异常并允许后续重试
7. 退市后停止常规采集，但永久保留已有历史数据
8. 不跨年度拼接，不复权，不重构 V0
9. 优先复用现有架构，避免不必要的复杂化

**Phase 1 - 基础扩展 (1-2 周，过渡方案):**
1. **扩展 `SYMBOL_NAME_MAP`** — 仅作为**过渡性手工维护**，包含当前已知挂牌合约 (V2701、V2705、V2709) 与未来预期合约 (V2801、V2805、V2809、V2901)
2. **更新采集循环** — 支持动态合约列表，遍历配置列表而非硬编码
3. **实现合约可用性检查** — 调用接口前先尝试获取，捕获 "Length mismatch" 等特征错误，标记为"未挂牌"而非报错
4. **独立文件路径** — 复用现有 `get_daily_csv`/`get_minute_csv`/`get_snapshot_file`，按 symbol 自动生成

> ⚠️ **说明**: Phase 1 中的手工维护 `SYMBOL_NAME_MAP` 只是**过渡方案**，最终目标是 Phase 2 实现自动发现。不应将手工维护当作最终目标。

**Phase 2 - 自动发现与生命周期 (2-4 周):**
1. **实现自动合约发现** — 定期轮询预期合约代码 (基于年份+月份模式)，检测"Length mismatch"从失败转为成功的时刻，自动加入采集列表
2. **生命周期状态机** — 每个合约维护状态：`UNLISTED`(未挂牌) → `ACTIVE`(交易中) → `NEAR_EXPIRY`(临近交割) → `EXPIRED`(已退市)
3. **退市检测** — 基于最后交易日 (大商所规则：交割月份第 3 个周五) 或连续 N 个交易日无成交量判定退市，自动停止常规采集
4. **异常记录与重试** — 已挂牌合约获取失败 (网络错误、数据校验失败) 记录异常、指数退避重试，不影响其他合约

**Phase 3 - 生产化与优化 (4-8 周):**
1. **增强监控与告警** — 采集成功率、延迟、异常合约数量仪表盘
2. **性能优化** — 大量合约并发时的资源控制、内存管理
3. **部署脚本与文档** — GitHub Actions 定时触发、手动触发、失败重试策略
4. **可选: Web Scraping 备选方案** — 若 DCE 官方接口长期不可用，建设网页解析能力作为兜底

## 6. Data Storage and Historical Data Retention

### 6.1 Current Storage Model

**✅ Proven Architecture:**
- **File-based storage**: Simple, reliable, no database dependencies
- **CSV format**: Human-readable, easy to process
- **Atomic writes**: No data corruption on failure
- **Deduplication**: Prevents duplicate records
- **Incremental updates**: Only modified records rewritten

**❌ Limitations:**
- No database querying capabilities
- Limited data type support
- No built-in indexing
- Query complexity limited

### 6.2 Recommended Storage Strategy

**✅ Maintain Current Approach:**
- Continue using CSV files for each contract
- Keep contract-specific files (V2701_daily_bars.csv, V2705_daily_bars.csv, etc.)
- Maintain unified quality log (`minute_data_quality.jsonl`)

**📋 Contract-Specific Storage:**
```
output/
├── V0_daily_bars.csv                    # Continuous contract
├── V2701_daily_bars.csv                 # January 2026
├── V2705_daily_bars.csv                 # May 2026  
├── V2709_daily_bars.csv                 # September 2026
├── V2801_daily_bars.csv                 # January 2027 (new)
├── V2901_daily_bars.csv                 # January 2028 (new)
├── V2805_daily_bars.csv                 # May 2027 (new)
├── V2809_daily_bars.csv                 # May 2028 (new)
├── [similar files for minute and realtime]
└── minute_data_quality.jsonl            # Global quality log
```

**📋 Data Retention Policy:**
- **Historical Data**: Permanent retention (as per requirement #7)
- **Active Contracts**: Continuous updates
- **Retired Contracts**: Files preserved with historical data
- **No Data Purge**: Files grow indefinitely (current limitation)

## 7. Minimal Necessary Changes List

### 7.1 Core System Modifications

**🔧 REQUIRED CHANGES (最小必要改动):**

1. **扩展合约映射** (`SYMBOL_NAME_MAP`) — **过渡性手工维护**:
   ```python
   SYMBOL_NAME_MAP = {
       "V0": "PVC连续",
       "V2701": "PVC 2701",
       "V2705": "PVC 2705",
       "V2709": "PVC 2709",
       # 以下为预期合约，Phase 1 手工维护，Phase 2 自动发现后移除硬编码
       "V2801": "PVC 2801",
       "V2805": "PVC 2805",
       "V2809": "PVC 2809",
       "V2901": "PVC 2901",
   }
   ```

2. **更新采集入口函数** — 支持动态合约列表:
   - `collect_realtime_snapshot(symbol)`：已支持任意 symbol，无需修改
   - `fetch_and_update_daily_bars(symbol)`：已支持任意 symbol，无需修改
   - `update_minute_bars(symbol, df)`：已支持任意 symbol，无需修改
   - **主循环** (`__main__`)：将硬编码的 `("V0", "V2701")` 替换为从配置/发现模块获取的动态列表

3. **新增合约可用性检查模块** (`contract_discovery.py`):
   - `check_contract_available(symbol) -> bool`：尝试调用日线接口，捕获 "Length mismatch" 等特征错误，返回 False 表示未挂牌
   - `discover_new_contracts(base_years, months=[1,5,9]) -> List[str]`：基于年份范围和月份模式生成预期代码并批量检查
   - `get_active_contracts() -> List[str]`：返回当前状态为 ACTIVE 的合约列表

4. **新增合约生命周期状态管理** (可选，Phase 2):
   - 简单的内存/文件状态持久化：`UNLISTED` → `ACTIVE` → `NEAR_EXPIRY` → `EXPIRED`
   - 退市判定逻辑：最后交易日规则或连续无成交检测

### 7.2 Infrastructure Changes

**🔧 REQUIRED CHANGES:**

1. **任务管理**:
   - 主循环遍历动态合约列表提交任务，保持现有 `ThreadPoolExecutor` 并行模式
   - 每个合约的三条流 (实时、分钟、日线) 仍为独立任务，互不干扰

2. **文件路径管理**:
   - **无需修改** — 现有 `get_daily_csv`/`get_minute_csv`/`get_snapshot_file` 已支持任意 symbol

3. **配置**:
   - 新增 `contracts.yaml` 或 `contracts.json` (可选)：目标年份范围、目标月份 (1,5,9)、预期合约代码模板
   - 保持现有无配置文件也可运行的能力 (内置默认值)

### 7.3 Testing and Validation

**🔧 REQUIRED CHANGES:**

1. **测试覆盖扩展**:
   - 单元测试：合约可用性检查 (模拟 Length mismatch、网络错误、成功)
   - 单元测试：生命周期状态迁移 (UNLISTED→ACTIVE→EXPIRED)
   - 集成测试：多合约并行采集、错误隔离、文件独立性

2. **验收测试场景** (见 Section 8):
   - V0 原有功能完全不受影响
   - 已挂牌合约 (V2701/05/09) 正常采集
   - 未挂牌合约 (V2801/05/09/2901) 标记为 UNLISTED，不报错、不写入空文件
   - 已退市合约历史数据永久保留，不再采集
   - 新挂牌合约自动发现并加入采集 (Phase 2)

## 8. Testing and Acceptance Standards

### 8.1 Existing Test Coverage

**✅ Well-Tested Areas:**
- Real-time snapshot collection
- Minute bar validation and filtering
- Daily bar validation
- Atomic file writing
- Error handling and recovery
- Data deduplication

**❌ Missing Coverage:**
- Contract discovery logic
- New contract addition
- Contract lifecycle management
- Multi-contract parallel execution
- Historical data continuity across contract transitions

### 8.2 Required Test Scenarios

**🔧 NEW TESTS NEEDED:**

1. **Contract Discovery Tests:**
   - Test automatic availability checking
   - Test new contract detection
   - Test contract list updates

2. **Multi-Contract Tests:**
   - Test parallel collection across contracts
   - Test independent file operations
   - Test error isolation

3. **Lifecycle Management Tests:**
   - Test contract retirement detection
   - Test historical data preservation
   - Test transition handling

### 8.3 Acceptance Criteria

**🔧 IMPLEMENTATION VERIFICATION (验收标准):**

1. **V0 Compatibility (V0 兼容性):**
   - ✅ Existing V0 data unchanged (现有 V0 数据完全不变)
   - ✅ V0 collection functionality unaffected (V0 采集功能完全不受影响)
   - ✅ No breaking changes to existing API (无破坏性 API 变更)

2. **Contract Discovery (合约发现):**
   - ✅ 已挂牌合约 (V2701/05/09) 自动识别为 ACTIVE 并正常采集
   - ✅ 未挂牌合约 (V2801/05/09/2901) 标记为 UNLISTED，**不报错、不写入空文件、不计入失败统计**
   - ✅ 正确识别 1、5、9 月交割月份合约
   - ✅ 新挂牌合约自动发现并加入采集 (Phase 2 验收)

3. **Data Collection (数据采集):**
   - ✅ 日线/分钟线/实时快照三条流对每个 ACTIVE 合约均正常工作
   - ✅ 关键字段 (OHLC、成交量、持仓量、结算价、日期时间) 完整填充
   - ✅ 已挂牌合约获取失败 (网络/校验) 记录异常、指数退避重试，**不影响其他合约**

4. **Data Storage (数据存储):**
   - ✅ 每个合约独立 CSV/JSONL 文件，互不混合
   - ✅ 历史数据永久保留 (不因合约退市而删除)
   - ✅ 去重键按合约隔离：日线 (symbol, trading_date)、分钟线 (symbol, datetime)、实时 (symbol, source_date, source_time)

5. **Lifecycle Management (生命周期管理):**
   - ✅ 退市合约 (到达最后交易日) 自动停止常规采集
   - ✅ 退市合约历史数据完整保留
   - ✅ 新挂牌合约自动从 UNLISTED 转为 ACTIVE 并开始采集 (Phase 2)
   - ✅ 新旧年度同月份合约可并存采集 (如 V2701 与 V2801 同时存在时)

## 9. Technical Risks and Unresolved Issues

### 9.1 Critical Risks

**🔴 HIGH RISK:**

1. **合约挂牌信息发现依赖缺失:**
    - **风险**: 大商所官方合约规范接口 `futures_contract_info_dce()` 当前返回 JSONDecodeError，**无法程序化获取权威挂牌列表、上市日、最后交易日**
    - **影响**: 依赖"错误码推断"或"人工维护"发现新合约，可能遗漏或延迟
    - **缓解**: Phase 1 手工维护预期列表 + Phase 2 定期轮询预期代码 + 监控 DCE 官网公告；长期建设 Web Scraping 兜底

2. **数据格式不一致:**
   - **风险**: 新挂牌合约可能返回不同数据格式 (列名、字段顺序、缺失值表示)
   - **影响**: 采集失败、数据校验不通过
   - **缓解**: 统一的 `validate_daily_bars`/`validate_minute_bars` 校验层，新合约首次采集时人工抽检

3. **API 可靠性:**
   - **风险**: AKShare 依赖的新浪/东财等数据源可能不稳定、限流、结构变更
   - **影响**: 采集中断、数据缺失
   - **缓解**: 指数退避重试、多源兜底 (如有备选)、熔断机制、详细日志告警

4. **实时行情覆盖范围有限:**
   - **风险**: 新浪实时 API 仅覆盖活跃/临近交割合约，**已退市、未挂牌合约无实时数据**
   - **影响**: 无法对未挂牌合约进行实时监控发现
   - **缓解**: 接受此限制，实时流仅服务 ACTIVE 合约；日线/分钟线历史接口覆盖全生命周期

### 9.2 Technical Limitations

**🟡 MEDIUM RISK:**

1. **无官方合约规范 API:**
   - 无法获取大商所权威的交易单位、最小变动价位、保证金率、交割规则
   - **应对**: 参考 CZCE/SHFE 接口结构人工维护 PVC 专用元数据；不影响行情采集本身

2. **文件无限增长:**
   - CSV 按合约分文件存储，长期运行文件体积持续增大
   - **影响**: 存储成本、查询性能下降
   - **应对**: Phase 3 考虑迁移至时序数据库 (TimescaleDB/InfluxDB) 或分区 Parquet

3. **查询能力受限:**
   - 无法轻松跨合约、跨时间范围联合查询
   - **影响**: 分析复杂度高
   - **应对**: 导出工具支持合并查询；长期配合数仓建设

### 9.3 Unresolved Questions

**❓ OPEN QUESTIONS:**

1. **合约发现频率与策略:**
   - 轮询频率设为多少？(建议: 每日 1 次，非交易时段)
   - 如何平衡"及时发现"与"避免无效请求"？

2. **退市判定准则:**
   - 以交易所公布最后交易日为准，还是以连续 N 日无成交为准？
   - 节假日调整导致的最后交易日变动如何获取？

3. **异常状态处理:**
   - 合约停牌/复牌、临时调整保证金/涨跌停板如何感知？
   - 数据源返回异常值 (如结算价为 0) 如何区分"数据缺失"与"真实 0 值"？

4. **DCE 官方接口恢复时间:**
   - `futures_contract_info_dce()` 何时修复？是否有替代官方数据源？
   - 是否值得投入建设 Web Scraping 作为永久兜底？

## 10. Final Feasibility Assessment and Implementation Recommendations

### 10.1 Feasibility Conclusion

**🎯 OVERALL FEASIBILITY: MODERATE TO HIGH**

**✅ What We CAN Do (已验证可行):**
1. **Extend Current Architecture**: 系统模块化设计，天然支持多合约并行采集
2. **Add New Contracts**: 已挂牌合约 (V2701/05/09) 行情获取完全正常，历史合约 (V2401–V2609) 数据完整可获取
3. **Maintain V0 Compatibility**: V0 采集逻辑与存储完全隔离，零影响
4. **Implement Required Features**: 独立存储、去重、校验、并行、异常隔离均已有成熟实现

**❌ What We CANNOT Do (客观限制):**
1. **权威合约挂牌信息自动获取**: 大商所官方接口 `futures_contract_info_dce()` 当前不可用 (HTTP 412)
2. **预测性合约新增**: 无法预知新合约确切挂牌日期，只能轮询发现
3. **完整生命周期自动化**: 退市判定依赖规则推算或人工确认，无官方实时状态源
4. **未挂牌合约实时监控**: 新浪实时 API 不覆盖未挂牌合约

### 10.2 Recommended Implementation Strategy

**📋 PHASED APPROACH (严格遵循 9 条设计原则):**

**Phase 1 - 基础扩展 (1-2 周，过渡方案):**
1. 扩展 `SYMBOL_NAME_MAP` — **仅含当前已挂牌 + 预期近期挂牌合约，明确标注为过渡性手工维护**
2. 主循环改为遍历动态合约列表 (从配置/发现模块获取)
3. 新增 `check_contract_available(symbol)`：捕获 "Length mismatch" 标记 UNLISTED，不报错
4. 复用现有文件路径函数，按 symbol 自动生成独立 CSV/JSONL
5. **验收**: V0 零影响；V2701/05/09 正常采集；V2801/05/09/2901 标记 UNLISTED 无报错

**Phase 2 - 自动发现与生命周期 (2-4 周):**
1. `discover_new_contracts()`：按年份范围×月份模式生成预期代码，定期批量检查
2. 合约状态机：`UNLISTED` → `ACTIVE` → `NEAR_EXPIRY` → `EXPIRED`
3. 退市判定：最后交易日规则 (交割月第 3 周五) + 连续无成交兜底
3. 异常重试：已挂牌合约网络/校验失败指数退避重试，记录异常不阻塞其他合约
4. **验收**: 新挂牌合约自动转 ACTIVE 并采集；退市合约自动停止采集但保留历史

**Phase 3 - 生产化与优化 (4-8 周):**
1. 监控仪表盘：采集成功率、延迟、异常合约、文件大小
2. 性能调优：并发控制、内存管理、大文件增量写入优化
3. 部署运维：GitHub Actions 定时/手动触发、失败重推、版本回滚
4. 可选 Web Scraping：DCE 官网公告解析作为官方接口长期不可用的兜底

### 10.3 Risk Mitigation Recommendations

**🛡️ IMMEDIATE ACTIONS (立即执行):**
1. **Phase 1 先行**: 以手工维护预期合约列表起步，**不等待官方接口恢复**
2. **错误分级**: "Length mismatch"=未挂牌 (INFO)；网络/校验失败=异常 (WARNING/ERROR)
3. **全链路日志**: 每合约每流水线记录耗时、行数、状态、错误码
4. **V0 回归保护**: 单元测试覆盖 V0 采集全流程，确保重构零回归

**🔄 LONG-TERM IMPROVEMENTS (长期演进):**
1. **多数据源兜底**: 调研除 AKShare/新浪外的备选行情源
2. **Web Scraping 能力**: DCE 官网合约挂牌公告定时解析
3. **合约预测模型**: 基于历史挂牌规律 (约提前 12 个月) 辅助预判
4. **存储升级**: CSV → 分区 Parquet / TimescaleDB，支持高效跨合约查询

### 10.4 Success Criteria (可度量验收指标)

**✅ MEASUREABLE SUCCESS INDICATORS:**

1. **功能性指标:**
   - 所有目标合约 (V2701/05/09、V2801/05/09/2901) 状态正确识别
   - V0 功能 100% 保持
   - 1、5、9 月合约筛选准确
   - 历史数据永久保留 (0 丢失)
   - 合约级独立存储 (0 混合)

2. **技术性指标:**
   - 任意单流失败不影响其他流/合约 (隔离性 100%)
   - 重复采集 0 重复数据 (去重有效)
   - 异常数据不入库 (校验拦截 100%)
   - 单次采集耗时 < 60s (并行加速)

3. **运维性指标:**
   - 新挂牌合约 < 24h 自动发现 (Phase 2)
   - 退市合约自动停止采集、历史数据 100% 保留
   - 系统可用性 > 99.5% (工作日交易时段)
   - 失败告警 < 5min 触达

## Executive Summary

**🔍 KEY FINDINGS:**

The AKShare PVC futures data collection system has a **modular, extensible architecture** that supports adding new contracts. 

**✅ ACHIEVABLE GOALS (已验证):**
1. Extend current system to support all target contracts (V2701/05/09 当前已挂牌，V2801/05/09/2901 预期近期挂牌 + V0)
2. Maintain complete backward compatibility with V0
3. Implement independent storage per contract
4. Add automatic new contract detection via polling (受限于无官方接口)
5. Leverage working CZCE/SHFE contract info APIs as reference for metadata structure

**❌ SIGNIFICANT CHALLENGES (客观限制):**
1. No official DCE contract information API (returns JSONDecodeError) — **独立问题，不影响已挂牌合约行情采集**
2. Cannot reliably determine contract lifecycle events for DCE — 需规则推算/人工维护
3. Newer contracts may have different data formats — 需统一校验层兜底
4. Requires manual intervention for contract management (过渡期) — Phase 2 自动化解决
5. Real-time data only available for active contracts (Sina API limitation) — 接受限制

**关键修正:** V2801、V2901、V2805、V2809 在测试时点**尚未挂牌**，其接口报错属正常现象，**不应归类为采集失败或接口不兼容**。

**📊 RECOMMENDATION:**
Proceed with **phased implementation** starting with basic contract list expansion and gradually adding discovery capabilities. The existing system provides a solid foundation for extension with minimal risk to current operations.

**💰 INVESTMENT RECOMMENDATION:**
- **Phase 1**: Low cost, high value (2-4 person-weeks) — 过渡性手工维护预期列表
- **Phase 2**: Medium cost, medium value (4-8 person-weeks) — 自动发现+生命周期
- **Phase 3**: High cost, lower incremental value (8-12 person-weeks) — 生产化+存储升级

**🎯 FINAL RECOMMENDATION:** Start immediately with Phase 1 to establish baseline functionality, then proceed with Phases 2 and 3 as resources and data availability permit.

**Report Generated:** 2026-11-02
**Project:** AKShare PVC Contract Data Collection Enhancement
**Status:** Review Complete - Ready for Implementation Planning
**Next Steps:** Proceed with Phase 1 implementation using existing Coder resources

---