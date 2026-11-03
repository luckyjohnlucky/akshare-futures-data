# PVC 具体交割月份合约数据采集 — Phase 1 实施计划

**版本**: 1.0  
**基于**: `.kilo/plans/pvc-contract-data-review.md`（已修订审查报告）  
**状态**: 计划制定中（未执行代码修改）  
**测试时点**: 2026-11-02 08:18–08:25 CST  
**AKShare 版本**: 1.20.0  

---

## 一、Phase 1 目标与范围

### 目标
在不影响现有 V0 主力连续行情采集的前提下，增加 PVC 具体交割月份合约的独立采集与存储能力。首批测试对象为已验证可用的 V2701、V2705、V2709。

### 范围内（Phase 1 实施）
- 扩展合约配置，增加 V2705、V2709 到采集列表
- 修改主采集循环，支持动态合约列表遍历
- 新增合约状态分类逻辑（ACTIVE/UNLISTED/UNKNOWN/ERROR），`Length mismatch` 不得单独作为未挂牌判据
- 复用现有所有采集器、验证器、去重机制、原子写入
- 日线、分钟线、实时快照三条流对新合约均独立工作

### 范围外（Phase 1 明确不实施）
- 自动合约发现系统（无需轮询未知合约代码）
- 完整生命周期状态机（UNLISTED→ACTIVE→NEAR_EXPIRY→EXPIRS）
- 网页爬虫备用数据源
- Tushare、天勤等新数据源接入
- 自动交易、预测或交易信号功能
- 架构重构（不重构 V0，不引入数据库）

---

## 二、设计原则（必须遵守）

| 序号 | 原则 | 说明 |
|------|------|------|
| P1 | V0 零影响 | V0 原有采集逻辑、数据定义、存储方式完全保持不变 |
| P2 | 独立采集存储 | 具体合约独立采集、独立存储、独立去重 |
| P3 | 不跨年度拼接 | 不进行跨年度合约拼接，不前复权、不后复权 |
| P4 | 多年度并存 | 允许不同年度的同月份合约同时采集（如 V2701 与 V2801 同时存在） |
| P5 | 未挂牌非故障 | 尚未挂牌的合约不作为采集故障，不报错、不写入空文件 |
| P6 | Length mismatch 不唯一判据 | `Length mismatch` 错误不得作为唯一的未挂牌判据，需结合接口响应综合判断 |
| P7 | 异常分级 | 接口异常、网络异常、数据格式变化不得直接判定为未挂牌，需保留 ERROR 路径 |
| P8 | UNKNOWN/ERROR 路径 | 无法确认挂牌状态时，保留 UNKNOWN/ERROR 处理路径，不丢弃诊断信息 |
| P9 | 历史永久保留 | 历史数据永久保留，不因合约退市而删除 |
| P10 | 复用优先 | 优先复用现有采集器、数据格式、质量检查和原子写入机制，避免过度设计 |

---

## 三、文件改动清单

### 3.1 需要修改的文件

#### `fetch_pvc.py`（核心修改）

**为什么修改**：当前主循环硬编码了 `("V0", "V2701")`，`SYMBOL_NAME_MAP` 仅包含两个合约，无 `Length mismatch` 错误分类处理。需要扩展以支持多合约动态遍历和未挂牌合约的优雅处理。

**具体修改项**：

1. **扩展 `SYMBOL_NAME_MAP`**（第 69-72 行）
   - 增加 V2705、V2709（已验证可用）
   - 增加 V2801、V2805、V2809、V2901（预期合约，标注为预期）
   - 明确标注哪些为过渡性手工维护

2. **新增 `ACTIVE_CONTRACTS` 常量**
   - 定义需要主动采集的合约列表：`["V0", "V2701", "V2705", "V2709"]`
   - V0 为主力连续，V2701/05/09 为具体交割月份合约

3. **新增 `EXPECTED_CONTRACTS` 常量**（可选，用于未来自动发现扩展）
   - 定义预期但尚未挂牌的合约：`["V2801", "V2805", "V2809", "V2901"]`
   - Phase 1 不主动采集，仅在配置中声明

4. **修改 `__main__` 主循环**（第 860-870 行）
   - 将硬编码的 `("V0", "V2701")` 替换为遍历 `ACTIVE_CONTRACTS`
   - 每个合约仍提交三条独立任务（实时、分钟、日线）
   - 保持 `ThreadPoolExecutor` 并行模式不变

5. **新增合约可用性检查与状态分类逻辑**（在 `_run_daily_bars` 和 `_run_minute_bars` 中）
   - 捕获接口异常，按异常类型分类：
     - **ACTIVE**：接口返回有效数据 → 正常走校验、去重、写入流程
     - **ERROR**：网络超时、HTTP 异常、数据格式变化等真实接口异常 → 记录异常类型、异常消息、合约代码，日志级别 ERROR，不写文件，不抛出异常中断其他合约
     - **UNKNOWN**：无法确认挂牌状态的异常（包括仅凭 `Length mismatch` 无法判断是“未挂牌”还是“格式变化”的情况） → 记录异常类型、异常消息、合约代码，日志级别 ERROR，不写文件，不中断其他合约，后续运行允许重新检测和重试
     - **UNLISTED**：仅在存在可靠证据确认合约尚未挂牌时才判定（例如多个独立接口均返回明确的“不存在”信号，而非仅 `Length mismatch`） → 日志级别 INFO，跳过采集，不写文件
   - `Length mismatch` **不得单独作为未挂牌判据**，必须结合其他证据（如 Sina 实时 API 返回 insufficient fields、多次重试后仍无数据等）才能标记为 UNLISTED
   - 网络异常（`requests.RequestException`）由 `_retryable_call` 指数退避重试（3 次），失败后由外层 try-except 记录 ERROR，不影响其他合约
   - UNKNOWN 和 ERROR 合约**不被永久排除**，后续运行应允许重新检测和重试
   - 单个合约异常不能中断其他合约及 V0 采集（每个合约每条流在独立 try-except 中执行）

6. **实时快照流的状态分类处理**（在 `_run_realtime_snapshot` 中）
   - `collect_realtime_snapshot` 已在 Sina 返回 insufficient fields 时返回 `None`
   - 无需额外修改，现有 `if snapshot is None: logger.error(...)` 逻辑即可
   - 返回 None 的合约标记为 ERROR（网络/接口异常）或 UNKNOWN（无法区分是未挂牌还是异常），不写入 JSONL，不影响其他合约
   - 保留原始异常类型、异常消息和合约代码，便于排查

### 3.2 不需要修改的文件（复用现有）

| 文件/函数 | 复用理由 |
|-----------|----------|
| `get_daily_csv(symbol)` | 已支持任意 symbol，生成 `{symbol}_daily_bars.csv` |
| `get_minute_csv(symbol)` | 已支持任意 symbol，生成 `{symbol}_minute_bars.csv` |
| `get_snapshot_file(symbol)` | 已支持任意 symbol，生成 `{symbol}_realtime_snapshots.jsonl` |
| `validate_daily_bars(df)` | 符号无关，仅校验字段和 OHLC 逻辑 |
| `validate_minute_bars(df)` | 符号无关，仅校验字段和时间戳 |
| `update_daily_bars(df, symbol)` | 使用 (symbol, trading_date) 去重键，符号隔离 |
| `update_minute_bars(symbol, df)` | 使用 (symbol, datetime) 去重键，符号隔离 |
| `append_jsonl()` | 通用 JSONL 原子写入，符号无关 |
| `records_to_csv()` | 通用 CSV 原子写入，符号无关 |
| `clean()`, `number()` | 通用数据清洗，符号无关 |
| `is_after_market_close()` | 交易时间判断，合约无关 |
| `ThreadPoolExecutor` 并行框架 | 已支持多任务并行，无需修改 |

### 3.3 新增文件

**Phase 1 不新增任何 Python 文件**。所有逻辑集中在 `fetch_pvc.py` 中，避免过度设计。

**可选（不在 Phase 1 必须范围内）**：
- `contracts.yaml` 或 `contracts.json`：若未来需要将合约列表从代码中解耦，可在 Phase 2 引入

---

## 四、合约配置组织方案

### 4.1 配置结构（在 `fetch_pvc.py` 中定义）

```python
# 合约显示名称映射（过渡性手工维护，Phase 2 可迁移至配置文件）
SYMBOL_NAME_MAP = {
    "V0": "PVC连续",
    "V2701": "PVC 2701",
    "V2705": "PVC 2705",
    "V2709": "PVC 2709",
    # 以下为预期合约（未挂牌），Phase 1 手工维护，Phase 2 自动发现后移除硬编码
    "V2801": "PVC 2801",
    "V2805": "PVC 2805",
    "V2809": "PVC 2809",
    "V2901": "PVC 2901",
}

# 需主动采集的合约列表（Phase 1 首批）
ACTIVE_CONTRACTS = ["V0", "V2701", "V2705", "V2709"]

# 预期但尚未挂牌的合约（Phase 1 不主动采集，仅声明）
EXPECTED_CONTRACTS = ["V2801", "V2805", "V2809", "V2901"]
```

### 4.2 合约配置职责（Phase 1 硬编码方案，保留）

- **`ACTIVE_CONTRACTS`**：当前已确认可采集的合约列表。只有列在此列表中的合约才会被主循环提交采集任务。Phase 1 首批为 `["V0", "V2701", "V2705", "V2709"]`。
- **`EXPECTED_CONTRACTS`**：未来需要关注的目标合约，**不代表已经挂牌**。Phase 1 不主动采集，仅在配置中声明，作为“待确认挂牌”的清单。当前为 `["V2801", "V2805", "V2809", "V2901"]`。
- **未挂牌合约不得作为正常采集任务执行**：EXPECTED_CONTRACTS 中的合约不会被加入采集循环，只有在人工确认其已挂牌并手工移入 `ACTIVE_CONTRACTS` 后，才会开始采集。
- **新合约加入方式（集中、可维护）**：当某个 EXPECTED_CONTRACTS 中的合约在大商所实际挂牌后，开发者在 `fetch_pvc.py` 中完成两步操作：（1）将合约代码从 `EXPECTED_CONTRACTS` 移至 `ACTIVE_CONTRACTS`；（2）在 `SYMBOL_NAME_MAP` 中补充对应的显示名称。无需修改其他代码，主循环会自动遍历新列表。
- **不要为了本阶段引入 YAML 配置或自动发现系统**：配置保持为代码中的 Python 常量，避免过度设计。

---

## 五、采集入口与执行流程

### 5.1 采集入口

单一入口：`fetch_pvc.py` 的 `__main__` 块。无需新增 CLI 参数或入口函数。

### 5.2 执行流程

```
启动 fetch_pvc.py
    │
    ├─ OUT 目录创建（如不存在）
    │
    ├─ 遍历 ACTIVE_CONTRACTS（["V0", "V2701", "V2705", "V2709"]）
    │   │
    │   ├─ 任务 1: 实时快照 (collect_realtime_snapshot)
    │   │   ├─ 调用 Sina HTTP API: https://hq.sinajs.cn/list=nf_{symbol}
    │   │   ├─ 若返回 None（未挂牌/网络异常）：记录 ERROR，跳过
    │   │   ├─ 若返回数据：校验 source_date/source_time，写入 JSONL
    │   │   └─ 去重键: (symbol, source_date, source_time)
    │   │
   │   ├─ 任务 2: 分钟线 (update_minute_bars)
   │   │   ├─ 调用 ak.futures_zh_minute_sina(symbol, period="1")
   │   │   ├─ 接口返回有效数据 → ACTIVE，走校验、去重、写入流程
   │   │   ├─ 捕获异常 → 分类判定：
   │   │   │   ├─ 有可靠证据确认未挂牌 → UNLISTED，INFO 日志，跳过，不写文件
   │   │   │   ├─ 网络/HTTP/格式等真实异常 → ERROR，ERROR 日志，记录异常类型和消息，允许后续重试
   │   │   │   └─ 无法确认状态（仅 Length mismatch 等） → UNKNOWN，ERROR 日志，记录异常类型和消息，允许后续重新检测
   │   │   └─ 去重键: (symbol, datetime)
   │   │
   │   └─ 任务 3: 日线 (fetch_and_update_daily_bars)
   │       ├─ 仅在 is_after_market_close() 为 True 时执行
   │       ├─ 调用 ak.futures_zh_daily_sina(symbol)
   │       ├─ 接口返回有效数据 → ACTIVE，走校验、去重、写入流程
   │       ├─ 捕获异常 → 分类判定：
   │       │   ├─ 有可靠证据确认未挂牌 → UNLISTED，INFO 日志，跳过，不写文件
   │       │   ├─ 网络/HTTP/格式等真实异常 → ERROR，ERROR 日志，记录异常类型和消息，允许后续重试
   │       │   └─ 无法确认状态（仅 Length mismatch 等） → UNKNOWN，ERROR 日志，记录异常类型和消息，允许后续重新检测
   │       └─ 去重键: (symbol, trading_date)
   │
   └─ ThreadPoolExecutor 并行执行所有任务，每个 symbol × 每条流为独立任务
```

### 5.3 并行执行特性

- 并行机制：使用原有代码中的 `ThreadPoolExecutor(max_workers=len(tasks))`（第 11 行导入，第 920-921 行使用），**并非 Phase 1 新增**
- Phase 1 改动：仅将主循环的 `for sym in ("V0", "V2701")` 改为 `for sym in ACTIVE_CONTRACTS`（第 915 行），使多合约并行采集成为可能
- 每个合约的三条流（实时、分钟、日线）独立提交，互不阻塞
- 不同合约之间也独立，单个合约失败不影响其他合约
- 总耗时取决于最慢的单个任务，而非所有任务之和

---

## 六、日线、分钟线、实时数据分别如何处理

### 6.1 日线数据

| 项 | 处理方式 |
|----|----------|
| 数据源 | `ak.futures_zh_daily_sina(symbol)` |
| 采集时机 | `is_after_market_close()` 为 True（北京时间 15:00+，周一至周五） |
| 状态分类 | ACTIVE：返回有效数据 → 正常采集；ERROR：网络/HTTP/格式异常 → 记录异常，不写文件；UNKNOWN：无法确认状态 → 记录异常，允许后续重试；UNLISTED：有可靠证据确认未挂牌 → 跳过，不写文件 |
| 接口异常 | `_retryable_call` 指数退避重试（3 次），失败后由外层 try-except 记录 ERROR，不写文件，不中断其他合约 |
| 字段校验 | `validate_daily_bars`: date, open, high, low, close, volume, hold, settle |
| 去重键 | (symbol, trading_date) |
| 存储文件 | `output/{symbol}_daily_bars.csv` |
| 字段 | symbol, name, trading_date, open, high, low, close, volume, open_interest, settle_raw, settle, quality_status, source, collected_at |

### 6.2 分钟线数据

| 项 | 处理方式 |
|----|----------|
| 数据源 | `ak.futures_zh_minute_sina(symbol, period="1")` |
| 采集时机 | 每次运行均尝试（受交易时间自然限制，非交易时段返回空或近期数据） |
| 状态分类 | ACTIVE：返回有效数据 → 正常采集；ERROR：网络/HTTP/格式异常 → 记录异常，不写文件；UNKNOWN：无法确认状态 → 记录异常，允许后续重试；UNLISTED：有可靠证据确认未挂牌 → 跳过，不写文件 |
| 接口异常 | `_retryable_call` 指数退避重试（3 次），失败后由外层 try-except 记录 ERROR，不写文件，不中断其他合约 |
| 字段校验 | `validate_minute_bars`: datetime, open, high, low, close, volume, hold |
| 时间戳过滤 | `separate_future_timestamps`: 过滤 collected_at + 1min 之后的未来时间戳 |
| 去重键 | (symbol, datetime) |
| 存储文件 | `output/{symbol}_minute_bars.csv` |
| 字段 | symbol, name, datetime, open, high, low, close, volume, open_interest, source, collected_at |

### 6.3 实时快照数据

| 项 | 处理方式 |
|----|----------|
| 数据源 | Sina HTTP API: `https://hq.sinajs.cn/list=nf_{symbol}` |
| 采集时机 | 每次运行均尝试 |
| 状态分类 | ACTIVE：返回有效数据 → 正常写入；ERROR：网络/接口异常 → 记录 ERROR，不写文件；UNKNOWN：Sina 返回 insufficient fields 但无法区分是未挂牌还是异常 → 记录 UNKNOWN，允许后续重试 |
| 接口异常 | `_retryable_call` 指数退避重试（3 次），失败后返回 None，ERROR 日志，不写文件 |
| 字段校验 | source_date 必须是有效 YYYY-MM-DD，source_time 必须是有效 HHMMSS |
| 去重键 | (symbol, source_date, source_time) |
| 存储文件 | `output/{symbol}_realtime_snapshots.jsonl` |
| 字段 | symbol, name, source, source_date, source_time, bar_datetime, collected_at, trading_date, open, high, low, current_price, bid_price, ask_price, last_close, last_settle_price, open_interest, volume, is_daily_bar_final, 等 |

---

## 七、文件命名、字段、去重键和存储路径

### 7.1 文件命名规则（现有，无需修改）

```
output/
├── {symbol}_daily_bars.csv              # 日线数据
├── {symbol}_minute_bars.csv             # 分钟线数据
└── {symbol}_realtime_snapshots.jsonl   # 实时快照
```

其中 `{symbol}` 为合约代码，如 `V0`, `V2701`, `V2705`, `V2709`。

### 7.2 存储路径

所有文件位于 `output/` 目录（`fetch_pvc.py` 第 66 行：`OUT = Path(__file__).resolve().parent / "output"`）。无需新增目录结构。

### 7.3 字段定义（复用现有，符号无关）

**日线 CSV**: symbol, name, trading_date, open, high, low, close, volume, open_interest, settle_raw, settle, quality_status, source, collected_at  
**分钟 CSV**: symbol, name, datetime, open, high, low, close, volume, open_interest, source, collected_at  
**实时 JSONL**: symbol, name, source, source_date, source_time, bar_datetime, collected_at, trading_date, open, high, low, current_price, bid_price, ask_price, last_close, last_settle_price, open_interest, volume, is_daily_bar_final, 等

### 7.4 去重键（复用现有，符号隔离）

| 数据类型 | 去重键 | 说明 |
|----------|--------|------|
| 日线 | (symbol, trading_date) | 不同合约同日期不冲突 |
| 分钟线 | (symbol, datetime) | 不同合约同时间戳不冲突 |
| 实时快照 | (symbol, source_date, source_time) | 不同合约同采集时刻不冲突 |

---

## 八、数据质量检查和异常日志如何复用

### 8.1 复用现有质量检查

| 检查函数 | 适用范围 | 说明 |
|----------|----------|------|
| `validate_daily_bars(df)` | 日线 | 字段完整性、日期有效性、OHLC 逻辑、价格非负、成交量持仓量非负 |
| `validate_minute_bars(df)` | 分钟线 | 字段完整性、时间戳有效性、OHLC 逻辑、价格正数、成交量持仓量非负 |
| `separate_future_timestamps()` | 分钟线 | 过滤未来时间戳（collected_at + 1min 容差） |
| `filter_future_anomalies()` | 分钟线合并后 | 清理历史文件中的残留异常记录 |

所有检查函数均为**符号无关**，对新合约直接适用，无需修改。

### 8.2 复用现有异常日志

| 日志文件 | 用途 | 去重键 |
|----------|------|--------|
| `output/minute_data_quality.jsonl` | 分钟线异常记录（如 future_timestamp） | (symbol, datetime) |
| 各合约 `{symbol}_realtime_snapshots.jsonl` | 实时快照（仅成功写入，失败不写入） | (symbol, source_date, source_time) |

### 8.3 新增异常分类日志（无需新文件，复用现有日志级别）

| 异常类型 | 识别方式 | 日志级别 | 处理动作 | 是否允许重试 |
|----------|----------|----------|----------|--------------|
| ACTIVE | 接口返回有效数据 | INFO | 正常采集，写入对应 CSV/JSONL | N/A |
| UNLISTED（未挂牌） | 有可靠证据确认合约尚未挂牌（非仅 `Length mismatch`） | INFO | 跳过采集，不写文件，不中断其他合约 | 否（需人工确认挂牌后移入 ACTIVE_CONTRACTS） |
| ERROR（接口异常） | 网络超时、HTTP 异常、数据格式变化等真实接口异常 | ERROR | 记录异常类型、异常消息、合约代码，不写文件，不中断其他合约 | 是（后续运行自动重试） |
| UNKNOWN（无法确认） | 无法区分是“未挂牌”还是“接口异常”的情况（包括仅凭 `Length mismatch` 无法判断） | ERROR | 记录异常类型、异常消息、合约代码，不写文件，不中断其他合约 | 是（后续运行自动重新检测） |
| RETRY_EXHAUSTED | `_retryable_call` 达到最大重试 | ERROR | 记录异常，继续其他合约 | 是（下次运行重新尝试） |

---

## 九、如何保证 V0 完全不受影响

### 9.1 代码层隔离

- `SYMBOL_NAME_MAP` 中 V0 条目保持不变：`"V0": "PVC连续"`
- `ACTIVE_CONTRACTS` 中 V0 仍为第一个元素，采集顺序不变
- 所有复用函数（`get_daily_csv`, `update_daily_bars`, `validate_daily_bars` 等）对 V0 的行为完全不变
- 主循环中的 `for sym in ACTIVE_CONTRACTS` 只是遍历列表，V0 的每条流逻辑与原代码一致

### 9.2 数据层隔离

- V0 数据文件：`output/V0_daily_bars.csv`、`output/V0_minute_bars.csv`、`output/V0_realtime_snapshots.jsonl` —— 路径不变，格式不变
- 去重键包含 symbol 字段，V0 数据与新合约数据在不同文件，无混合风险

### 9.3 测试层隔离

- 现有单元测试（`tests/` 目录）全部使用 Mock，不访问真实网络，不读写正式数据文件
- Phase 1 实施后，现有测试应继续通过，无需修改测试代码
- 新增的集成测试应使用临时目录，不读写正式 `output/` 目录

---

## 十、如何支持不同年度合约同时采集

### 10.1 机制

- 去重键包含 `symbol` 字段：`(symbol, trading_date)` 和 `(symbol, datetime)` —— 不同年度合约的同日期/同时间戳不会冲突
- 文件按 symbol 命名：`V2701_daily_bars.csv` 与 `V2801_daily_bars.csv` 是完全独立的文件
- 主循环遍历 `ACTIVE_CONTRACTS`，每个合约独立提交三条流任务

### 10.2 示例场景

假设未来 V2801（2027 年 1 月合约）挂牌并加入 `ACTIVE_CONTRACTS`：

```
ACTIVE_CONTRACTS = ["V0", "V2701", "V2705", "V2709", "V2801"]

并行执行：
  V0      → V0_daily_bars.csv, V0_minute_bars.csv, V0_realtime_snapshots.jsonl
  V2701   → V2701_daily_bars.csv, V2701_minute_bars.csv, V2701_realtime_snapshots.jsonl
  V2705   → V2705_daily_bars.csv, V2705_minute_bars.csv, V2705_realtime_snapshots.jsonl
  V2709   → V2709_daily_bars.csv, V2709_minute_bars.csv, V2709_realtime_snapshots.jsonl
  V2801   → V2801_daily_bars.csv, V2801_minute_bars.csv, V2801_realtime_snapshots.jsonl
```

V2701（2026 年 1 月）与 V2801（2027 年 1 月）可同时采集，无需等待 V2701 退市。

> 实际文件状态：V0 和 V2701 的日线文件已生成（修改时间 Oct 30）；V2705 和 V2709 的日线文件未生成，因测试运行于 00:22，未到 `is_after_market_close()` 采集时机（北京时间 15:00+，周一至周五），属预期行为。

---

## 十一、合约状态处理

### 11.1 五种状态及处理方式

| 状态 | 识别方式 | 日志级别 | 采集动作 | 文件写入 | 是否允许重试 |
|------|----------|----------|----------|----------|--------------|
| **ACTIVE**（已挂牌、可采集） | 接口返回有效数据，所有字段完整且通过校验 | INFO | 正常采集日线、分钟线、实时快照 | 写入对应 CSV/JSONL | N/A |
| **UNLISTED**（未挂牌） | 有可靠证据确认合约尚未挂牌（非仅 `Length mismatch`，需多个接口信号一致） | INFO | 跳过采集，不写文件，不中断其他合约 | 不写入 | 否（需人工确认挂牌后移入 ACTIVE_CONTRACTS） |
| **ERROR**（接口异常） | 网络超时、HTTP 错误、数据格式变化等真实接口异常 | ERROR | 记录异常类型、异常消息、合约代码，指数退避重试，失败后跳过 | 不写入 | 是（后续运行自动重试） |
| **UNKNOWN**（无法确认） | 无法区分是“未挂牌”还是“接口异常”，包括仅凭 `Length mismatch` 无法判断的情况 | ERROR | 记录异常类型、异常消息、合约代码，保留诊断信息 | 不写入 | 是（后续运行自动重新检测） |
| **RETRY_EXHAUSTED** | `_retryable_call` 达到最大重试次数 | ERROR | 记录异常，继续其他合约 | 不写入 | 是（下次运行重新尝试） |

### 11.2 状态判定规则（关键）

1. **`Length mismatch` 不能单独作为 UNLISTED 判据**：该错误可能由合约未挂牌、数据格式变更、接口临时异常等多种原因引起，必须结合其他证据（如 Sina 实时 API 返回 insufficient fields、多次重试后仍无数据等）才能标记为 UNLISTED。
2. **无法确认时标记为 UNKNOWN**：当仅有 `Length mismatch` 但无其他可靠证据时，标记为 UNKNOWN，保留原始异常类型、异常消息和合约代码，允许后续运行重新检测和重试。
3. **UNKNOWN 和 ERROR 不被永久排除**：这两类合约在后续运行中会重新尝试采集，无需人工干预即可恢复。
4. **单个合约异常不中断其他合约及 V0**：每个合约的每条流在独立的 try-except 中执行，异常被捕获并记录后，主循环继续处理下一个合约。

### 11.3 具体合约状态示例（基于 2026-11-02 测试）

| 合约 | 状态 | 依据 |
|------|------|------|
| V0 | ACTIVE | 日线 4228 条（2009-05-25 至 2026-11-02），分钟线正常，Sina 实时正常 **[实测]** |
| V2701 | ACTIVE | 日线 189 条（2026-01-19 至 2026-11-02），分钟线正常，Sina 实时正常 **[实测]** |
| V2705 | ACTIVE | 日线接口可用（111 条，2026-05-20 至 2026-11-02），但未到采集时机，日线文件未生成；分钟线正常，Sina 实时正常 **[实测]** |
| V2709 | ACTIVE | 日线接口可用（28 条，2026-09-15 至 2026-11-02），但未到采集时机，日线文件未生成；分钟线正常，Sina 实时正常 **[实测]** |
| V2801 | UNKNOWN | `Length mismatch` 错误，无其他可靠证据确认未挂牌 **[实测]** |
| V2805 | UNKNOWN | `Length mismatch` 错误，无其他可靠证据确认未挂牌 **[实测]** |
| V2809 | UNKNOWN | `Length mismatch` 错误，无其他可靠证据确认未挂牌 **[实测]** |
| V2901 | UNKNOWN | `Length mismatch` 错误，无其他可靠证据确认未挂牌 **[实测]** |

### 11.4 已退市合约的处理

| 场景 | 处理方式 |
|------|----------|
| 合约到达最后交易日 | Phase 1 不实施自动退市检测；若接口返回空数据，标记为 ERROR，允许后续重试；若有可靠证据确认未挂牌，标记为 UNLISTED |
| 历史数据 | 永久保留，不删除（符合 P9 原则） |
| 重复采集 | 去重键防止重复记录 |

---

## 十二、测试与验收标准

### 12.1 测试环境

| 测试层 | 环境要求 | 是否访问真实网络 |
|--------|----------|------------------|
| A. 自动化 Mock 测试 | 临时目录，使用 Mock 模拟 AKShare 接口和 Sina HTTP API | 否 |
| B. 真实接口冒烟测试 | 真实 Python 环境（`.venv`，AKShare 1.20.0），访问真实 AKShare 接口和 Sina HTTP API | 是 |

现有单元测试框架：`unittest`（`tests/` 目录）。

### 12.2 验收测试清单 —— Layer A：自动化 Mock 测试

| 序号 | 测试场景 | 验收标准 | 测试方法 |
|------|----------|----------|----------|
| T1 | V0 原有采集功能回归 | V0 日线、分钟线、实时快照采集结果与修改前一致；V0 数据文件内容不变 | 单元测试 + 对比修改前后输出 |
| T2 | V2701 具体合约采集 | 日线、分钟线、实时快照均能正常获取并写入对应文件 | 集成测试（Mock 接口） |
| T3 | V2705 具体合约采集 | 日线、分钟线、实时快照均能正常获取并写入对应文件 | 集成测试（Mock 接口） |
| T4 | V2709 具体合约采集 | 日线、分钟线、实时快照均能正常获取并写入对应文件 | 集成测试（Mock 接口） |
| T5 | 多年度同月份合约独立存储 | V2701 与 V2705 的日线文件独立，无数据混合；去重键按 symbol 隔离 | 集成测试（Mock 不同 symbol 返回不同数据） |
| T6 | 重复执行和去重 | 同一合约同一交易日/同一分钟只写入一条记录；重复运行不产生重复 | 单元测试（模拟重复数据） |
| T7 | OHLC、时间戳、成交量、持仓量字段检查 | 所有字段非空、类型正确、OHLC 逻辑满足（high >= max(open,close,low)，low <= min(open,close,high)） | 单元测试（校验函数直接调用） |
| T8 | 网络异常测试 | 接口抛出 ConnectionError 时，记录 ERROR，不影响其他合约，不写入损坏数据 | 单元测试（Mock 抛出异常） |
| T9 | 接口异常测试 | 接口返回空 DataFrame 或缺少字段时，记录 ERROR，不影响其他合约 | 单元测试（Mock 返回空/缺字段） |
| T10 | 未挂牌合约不误判为 ERROR | V2801 等合约仅返回 `Length mismatch` 时，标记为 UNKNOWN（非 ERROR），允许后续重试，不写入空文件 | 单元测试（Mock 抛出 `ValueError("Length mismatch")`） |
| T11 | UNKNOWN/ERROR 合约允许重试 | UNKNOWN/ERROR 合约在后续运行中重新尝试采集，不被永久排除 | 单元测试（模拟多次运行，验证 UNKNOWN 合约仍被检测） |
| T12 | 单个合约异常不中断 V0 | V2701 采集失败时，V0 采集仍正常进行 | 集成测试（Mock 某个合约失败，验证 V0 任务完成） |
| T13 | 历史数据不被覆盖或删除 | 现有 CSV 文件在重复采集后，旧记录保留，新记录追加，去重后写回 | 单元测试（预置历史数据，验证合并后旧数据完整） |

### 12.3 验收测试清单 —— Layer B：真实接口冒烟测试

**测试时间**：执行时记录（北京时间）  
**测试环境**：`.venv` 虚拟环境，AKShare 1.20.0，Python 3.13  
**测试对象**：V2701、V2705、V2709（已验证可挂牌的具体合约）

| 序号 | 测试场景 | 验收标准 | 测试方法 |
|------|----------|----------|----------|
| S1 | V2701 日线接口 | `ak.futures_zh_daily_sina(symbol="V2701")` 返回非空 DataFrame，包含 date/open/high/low/close/volume/hold/settle 字段，OHLC 逻辑正确 | 真实接口调用，记录返回记录数 |
| S2 | V2705 日线接口 | `ak.futures_zh_daily_sina(symbol="V2705")` 返回非空 DataFrame，字段完整，OHLC 逻辑正确 | 真实接口调用，记录返回记录数 |
| S3 | V2709 日线接口 | `ak.futures_zh_daily_sina(symbol="V2709")` 返回非空 DataFrame，字段完整，OHLC 逻辑正确 | 真实接口调用，记录返回记录数 |
| S4 | V2701 1分钟线接口 | `ak.futures_zh_minute_sina(symbol="V2701", period="1")` 返回非空 DataFrame，包含 datetime/open/high/low/close/volume/hold 字段 | 真实接口调用，记录返回记录数 |
| S5 | V2705 1分钟线接口 | `ak.futures_zh_minute_sina(symbol="V2705", period="1")` 返回非空 DataFrame，字段完整 | 真实接口调用，记录返回记录数 |
| S6 | V2709 1分钟线接口 | `ak.futures_zh_minute_sina(symbol="V2709", period="1")` 返回非空 DataFrame，字段完整 | 真实接口调用，记录返回记录数 |
| S7 | V2701 Sina 实时行情 | `https://hq.sinajs.cn/list=nf_V2701` 返回有效行情，包含价格、成交量、持仓量等字段 | 真实 HTTP 请求，解析返回字段 |
| S8 | V2705 Sina 实时行情 | `https://hq.sinajs.cn/list=nf_V2705` 返回有效行情，包含价格、成交量、持仓量等字段 | 真实 HTTP 请求，解析返回字段 |
| S9 | V2709 Sina 实时行情 | `https://hq.sinajs.cn/list=nf_V2709` 返回有效行情，包含价格、成交量、持仓量等字段 | 真实 HTTP 请求，解析返回字段 |
| S10 | 数据保存结果 | V2701/V2705/V2709 的分钟线、实时快照写入对应的 CSV/JSONL 文件；日线文件因 `is_after_market_close()` 为 False（非交易收盘时间）未生成，属预期行为 | 检查 `output/` 目录下对应文件是否存在 |
| S11 | 重复运行后的去重 | 对同一合约重复运行采集，同一交易日/同一分钟戳不产生重复记录 | 两次运行后检查 CSV 行数未重复增加 |

**真实接口测试记录格式**（每项测试需记录）：
- 测试时间（北京时间）
- 合约代码（V2701/V2705/V2709）
- 接口名称（`futures_zh_daily_sina` / `futures_zh_minute_sina` / Sina HTTP API）
- 返回记录数
- 返回字段列表
- 测试结果（通过/失败）
- 异常信息（如有）

**关键约束**：不得仅凭 Mock 测试通过就宣称采集能力已经验证。真实接口冒烟测试（Layer B）必须通过，才能确认具体合约的采集能力已验证。

### 12.4 可在当前环境实际完成的测试

- Layer A T1–T13：可，使用现有单元测试框架 + Mock
- Layer B S1–S11：可，使用 `.venv` 中的真实 AKShare 和 Sina HTTP API（已手工预验证 V2701/05/09 可用）

### 12.5 仅能在实施阶段验证的测试

- 生产环境下的并发性能和文件大小增长
- GitHub Actions 工作流的定时触发和失败重推
- 长期运行下的 UNKNOWN/ERROR 合约重试行为

---

## 十三、Phase 1 明确排除的工作

| 排除项 | 原因 | 建议阶段 |
|--------|------|----------|
| 自动合约发现系统 | 需轮询未知合约代码，超出 Phase 1 最小必要范围 | Phase 2 |
| 完整生命周期状态机 | 需状态持久化和退市判定逻辑 | Phase 2 |
| 网页爬虫备用数据源 | 需额外基础设施，非最小必要 | Phase 3（可选） |
| Tushare、天勤等新数据源 | 引入新依赖，违反 P10（复用优先） | 未来考虑 |
| 自动交易、预测、交易信号 | 违反项目原则第 9 条 | 永久排除 |
| 架构重构（V0 或整体） | 违反 P1、P3、P10 | 永久排除 |

---

## 十四、风险与待确认事项

### 14.1 已识别风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| `Length mismatch` 可能不仅由“未挂牌”引起 | 可能误将格式变更判定为 UNLISTED | `Length mismatch` 不得单独作为 UNLISTED 判据；无可靠证据时标记为 UNKNOWN，允许后续重试 |
| UNKNOWN/ERROR 合约反复重试 | 增加无效接口调用次数 | 指数退避重试，每次运行仅尝试一次，不频繁轮询 |
| 新合约数据格式与现有不同 | `validate_daily_bars`/`validate_minute_bars` 可能拒绝写入 | 新合约首次采集时人工抽检返回字段，TRUE ACTIVE 前先人工确认 |
| Sina 实时 API 对新合约返回数据格式不同 | `fetch_sina_spot` 字段解析可能失败 | `collect_realtime_snapshot` 已在返回 None 时优雅处理，记录 ERROR/UNKNOWN |
| 并行任务过多导致资源竞争 | 总耗时增加 | `ThreadPoolExecutor` 默认 `max_workers=len(tasks)`，任务数较少时无问题 |

### 14.2 待确认事项

1. **配置文件形式**：`SYMBOL_NAME_MAP` 和 `ACTIVE_CONTRACTS` 是否继续硬编码在 `fetch_pvc.py` 中，还是迁移至 `contracts.yaml`？（建议：Phase 1 保持硬编码，Phase 2 迁移）
2. **未挂牌合约的检查频率**：Phase 1 不主动检查 EXPECTED_CONTRACTS，仅在手工添加到 ACTIVE_CONTRACTS 时才尝试采集。是否需要定期检查？（建议：Phase 2 引入）
3. **已退市合约的自动停止**：Phase 1 不实施自动退市检测。退市合约若接口返回空数据，会被标记为 ERROR，需人工从 ACTIVE_CONTRACTS 移除。（建议：Phase 2 引入状态机）

---

## 十五、交付物清单

| 交付物 | 说明 | 状态 |
|--------|------|------|
| 本实施计划文档 | `.kilo/plans/pvc-phase1-implementation-plan.md` | 已制定 |
| 文件改动清单 | 见第 三 节 | 已制定 |
| 测试验收标准 | 见第 十二 节 | 已制定 |
| 风险与待确认事项 | 见第 十四 节 | 已制定 |

**代码修改**: 由 Coder 在用户批准本计划后执行，不在本计划范围内。

---

**报告生成**: 2026-11-02  
**基于审查报告**: `.kilo/plans/pvc-contract-data-review.md`  
**下一步**: 等待用户审查批准后，交由 Coder 执行 Phase 1 代码修改