# akshare-futures-data 最终审计总报告 V2

**项目路径**：`/Users/johnm/Projects/akshare-futures-data`
**报告性质**：仅汇编已完成审计模块的证据，修正原报告事实错误与定级问题，**不实施任何代码修复，不进入开发阶段**
**V2 基准报告**：`.kilo/plans/1793796003000-final-audit-report.md`（V1）
**独立复核**：本任务指令中的修正要求（独立复核报告正文未以附件形式随对话提供，其纠正要点已以本报告“独立复核意见及逐项裁决”章节形式固化）

---

## 1. 审计摘要和最终结论

V2 报告在 V1 基础上完成以下核心修正：

- **P0-1（本地/远程 SHA 不一致）**：从 P0 确定缺陷移除，降为 P2 版本基准问题。独立复核确认：本地 `main` 与远程 `origin/main` 源码**零差异**，差异仅体现在 10 个数据 CSV 文件上，远程多出的提交为自动采集数据提交。不得继续将其列为 P0 代码缺陷，也不得沿用 V1 中“47+ 提交差异”的旧说法。
- **P0-5（quality 日志不存在）**：从确定缺陷中删除，改为未验证事项。文件不存在已证实，但“过滤功能从未运行”缺乏证据，不得以此认定功能缺失。
- **P0-4（HTTP 缺少 timeout）**：保留 P0，但修正修复建议：AKShare 1.20.0 的相关函数内部直接调用 `requests.get`，函数签名无 timeout 参数，不能直接给外层 AKShare 函数增加 timeout 参数；具体实现方式标记为待技术设计。
- **P0-2（单任务失败不传递）**：保留 P0，补充精确失败传播机制，不将 `as_completed` 本身描述为有缺陷。
- **P0-3（重试异常类型不匹配）**：保留 P0，增加异常分类要求，不建议统一捕获 `ak.AkshareException` 后盲目重试。
- **output 文件总数**：修正为 20 个 CSV 文件（9 个商品日线 + 9 个商品分钟线 + 1 个 H11061 指数日线 + 1 个 0 字节 H11061 分钟线占位），0 字节文件不计入有效数据文件。
- **README 任务数与加速比**：补充说明代码实际提交 19 个采集 task，README 的 18/9 任务描述与当前代码不一致，6–7 倍/3–4 倍加速比无可靠基准证据，push 重试描述与当前工作流单次 push 不符。
- **新增遗漏项 N1–N5**：merge_v0_data.py 远程数据覆盖语义、Shell 测试缺少 Python fixture 隔离、工作流分支限制放宽、README push retry 描述错误、H11061 新旧日线文件并存。

**最终结论**：代码层采集/验证/原子写入逻辑基本可用，单元测试隔离性良好，H11061 已有 969 条真实数据。但存在 P0 级采集可靠性缺陷（无请求超时、重试异常类型不匹配、单任务失败不传递），以及 P1–P2 级数据处理、操作安全、工作流与文档问题。**建议先进入修复阶段处理 P0 缺陷，再进行正式发布。** 本报告不执行任何修复。

---

## 2. 审计范围、方法和版本基准

### 2.1 11 个审计模块

与 V1 一致，全部已完成，本报告汇编：

| 序号 | 审计模块 | 主要证据来源 |
|------|----------|--------------|
| 1 | Git 工作区状态 | `git status`、`git branch -vv`、`git rev-parse`、`git ls-files`、`investigation_report.md` |
| 2 | 项目结构与 README | 根目录列表、`README.md`（180 行） |
| 3 | `fetch_pvc.py` 代码逻辑 | `fetch_pvc.py`（1132 行，完整读取） |
| 4 | `merge_v0_data.py` | `merge_v0_data.py`（502 行，完整读取） |
| 5 | 测试文件审阅 | `tests/`（5 个 `.py` + 1 个 `.sh`，`conftest.py`） |
| 6 | GitHub Actions 工作流 | `.github/workflows/collect.yml`、`.bak`、README 工作流章节 |
| 7 | 数据文件抽查 | `output/` 目录列表及 `wc -l` 行数 |
| 8 | 单元测试运行 | `tests/` 中 `def test_` 计数、README 测试说明 |
| 9 | 数据完整性深度验证 | `output/` 行数、`merge_v0_data.py` 预期值、`pvc-final-review.md` |
| 10 | 安全性审查 | 工作流 `permissions`、`persist-credentials`、`subprocess` 使用、`fetch_pvc.py` 异常处理 |
| 11 | 性能与资源审查 | 并发模型（`ThreadPoolExecutor`）、README 加速比声明、无独立 cProfile 报告文件 |

### 2.2 版本基准（固定）

| 分支 | SHA（完整） | 提交信息 |
|------|-------------|----------|
| 本地 `main` | `fb97907fcb2678450abdd33d85ac32c3f19e2264` | `feat: add H11061 index daily line independent structure (B1-B3)` |
| 远程 `origin/main` | `bdecae1687bd7c48442fb24f8aaaf7cbd2695bc0` | `chore: auto-collect commodity futures data (2026-11-04T09:40:39Z)` |

**重要说明**：
- 两个 SHA 不一致**不等于源码存在差异**。独立复核确认本地与远程源码文件零差异，差异仅体现在 10 个数据 CSV 文件上，远程多出的提交为自动采集数据提交。
- 本地工作区状态、HEAD、`origin/main` 必须分别描述，不能混为一谈。
- V1 中记载的“本地落后远程 47 个提交”等旧信息已过时，不得作为当前事实。
- `.kilo/plans/1793711576733-h11061-index-daily-plan.md` 中的旧 SHA（本地 `9b94b5e`、远程 `2fa46b7`）已过时，不应作为当前基准。

### 2.3 审计限制

- 只汇编现有证据，不重新运行采集、不触发 GitHub Actions、不执行压力测试、不执行 `merge_v0_data.py`。
- 不修改任何 Python、Shell、YAML、CSV 或 README 源文件；不执行 Git 写操作（commit/push/pull/fetch/checkout/reset/clean/stash）；不删除备份文件；不创建修复分支。
- 已有审计报告之间存在矛盾时，逐项记录冲突、证据和最终裁决，不静默覆盖。
- 明确区分：确定缺陷、潜在风险、改进建议、未验证事项。

---

## 3. 项目结构与采集流程

### 3.1 项目基本信息

| 项目 | 内容 |
|------|------|
| 项目名称 | akshare-futures-data |
| 工作目录 | /Users/johnm/Projects/akshare-futures-data |
| 核心采集脚本 | `fetch_pvc.py`（1132 行） |
| V0 数据合并脚本 | `merge_v0_data.py`（502 行） |
| GitHub Actions 工作流 | `.github/workflows/collect.yml`（及备份 `.bak`） |
| 依赖文件 | `requirements.txt`：`akshare>=1.20,<2.0`、`numpy>=2.0,<3.0`、`pandas>=3.0,<4.0`、`requests>=2.31` |
| Python 运行环境 | `.venv`（Python 3.13，README 声明 3.9+） |
| 支持合约 | 9 个主力连续合约：V0( PVC)、TA0(PTA)、MA0(甲醇)、PP0(PP)、L0(塑料)、SA0(纯碱)、FG0(玻璃)、RB0(螺纹钢)、HC0(热卷)，以及指数 H11061（中证商品期货指数，仅日线，无分钟线） |
| 数据输出目录 | `output/`，共 20 个 CSV 文件（9 个商品日线 + 9 个商品分钟线 + 1 个 H11061 指数日线 + 1 个 0 字节 H11061 分钟线占位） |
| 备份目录 | `.kilo/phase4_backup/` |
| 本地备份分支 | `backup/local-before-merge`、`backup/remote-before-merge`（仅存在于本地，不存在于远程） |

### 3.2 采集流程（代码层）

`fetch_pvc.py` `__main__` 中：
1. 为 `ACTIVE_CONTRACTS`（10 个合约，含 H11061）的每个合约提交分钟线任务（H11061 跳过，无分钟线）和日线任务，共 19 个 task。
2. 使用 `ThreadPoolExecutor(max_workers=len(tasks))` 并行执行。
3. 每个 task 内部 `try/except` 捕获异常，仅 `logger.error` 记录，**不重新抛出、不返回失败状态**。
4. `__main__` 通过 `future.result()` 仅确认 task 完成，不会因单 task 失败而使整体流程报告失败。

AKShare 接口调用：
- `ak.futures_zh_minute_sina(symbol, period="1")` —— 分钟线
- `ak.futures_zh_daily_sina(symbol)` —— 商品日线
- `ak.futures_index_ccidx(symbol='中证商品期货指数')` —— H11061 指数日线

上述三个 AKShare 函数内部均直接调用 `requests.get`，**函数签名无 `timeout` 参数**，外层无法直接传入超时控制。

---

## 4. 数据完整性检查

### 4.1 现有数据文件行数（实测证据）

`wc -l` 统计（行数含 1 行表头，数据行 = 行数 - 1）：

| 文件 | 总行数 | 数据行 | 备注 |
|------|--------|--------|------|
| `output/V0_daily_bars.csv` | 4231 | 4230 | |
| `output/V0_minute_bars.csv` | 2397 | 2396 | |
| `output/H11061_index_daily.csv` | 970 | 969 | **969 条真实数据** |
| `output/H11061_minute_bars.csv` | 1（0 字节） | 0 | 空占位文件，不计入有效数据 |

### 4.2 已确认的行数矛盾（必须并列，待核实）

| 数据项 | merge_v0_data.py 预期 | pvc-final-review.md 报告 | 当前实测（`wc -l`） | 状态 |
|--------|----------------------|------------------------|---------------------|------|
| V0 日线数据行 | 4229 | 4230 | 4230 | 矛盾：4229 vs 4230 |
| V0 分钟线数据行 | 2044 | 2058 | 2396 | 矛盾：2044 vs 2058 vs 2396 |

**结论**：三方数据不一致，必须在修复阶段以当前代码重新跑一致性校验，记录实际行数并说明差异原因，不得仅凭任一数字认定数据完整。

### 4.3 H11061 验证状态纠正

- 早期报告曾将 H11061 指数日线标记为“未验证”。
- **实测证据**：`output/H11061_index_daily.csv` 共 970 行，扣除表头后 **969 条真实数据**，不应再标记为“未验证”。
- `output/H11061_minute_bars.csv` 为 0 字节，符合“指数无分钟线”设计（空占位）。

### 4.4 H11061 旧新日线文件并存（N5）

- 旧文件 `output/H11061_daily_bars.csv`：被 Git 跟踪，在本地 `main` HEAD 和 `origin/main` 中均存在，**但当前工作树中该文件已删除，删除未提交**。不得将工作区删除状态说成已经从 GitHub 删除。
- 新文件 `output/H11061_index_daily.csv`：独立指数日线文件，已存在并含 969 条数据。
- 两套文件数据结构和用途不同，当前不直接认定为缺陷，但需明确迁移、兼容和清理策略。

### 4.5 质量日志

- `output/minute_data_quality.jsonl`：**文件不存在**（已证实）。
- 但“不存在”不能推断为“过滤功能从未运行”，可能是本次采集未产生未来时间戳异常，或日志被清理/未生成。列为未验证事项 U-4。

### 4.6 merge_v0_data.py 远程数据覆盖语义（N1）

- 脚本读取 `origin/main` 的 `output/V0_daily_bars.csv` 和 `output/V0_minute_bars.csv`，合并时**优先使用远程数据**。
- 由于本地 `main` 落后于远程 `origin/main`，脚本可能把远程更新的数据带入本地。
- 这是一次性工具的设计风险，**不直接认定为 bug**。需要明确远程数据是否有意作为权威来源。

---

## 5. 代码可靠性问题

### 5.1 P0-4：AKShare HTTP 请求缺少有效 timeout（P0）

**问题描述**：`fetch_pvc.py` 调用 `ak.futures_zh_minute_sina`、`ak.futures_zh_daily_sina`、`ak.futures_index_ccidx` 时，底层均直接调用 `requests.get`，且 AKShare 函数签名无 `timeout` 参数。外层无法直接为 AKShare 调用设置超时，可能导致请求无限期阻塞。

**代码位置**：`fetch_pvc.py` 第 25-63 行 `_retryable_call`；第 1069/1090/1115 行 AKShare 接口调用。

**证据**：AKShare 1.20.0 相关函数内部直接调用 `requests.get`，无 `timeout` 参数暴露。

**影响范围**：所有采集任务（19 个 task）均可能受阻塞影响。

**置信度**：高（代码静态阅读可确认）。

**修复建议（待技术设计，不得直接实施）**：
- 不能把“给外层 AKShare 函数增加 timeout 参数”作为当前可直接实施的方案，因为 AKShare 函数签名不支持。
- 候选方案：
  1. 局部请求封装或替换：自行实现带超时的 HTTP 请求替换 AKShare 底层请求。
  2. monkeypatch `requests.get`：在调用前注入超时参数。需重点分析 monkeypatch 对多线程（`ThreadPoolExecutor`）及进程内其他 HTTP 请求的影响。
  3. 维护 AKShare 内部请求补丁或替代实现：维护成本高，升级困难。

**验收标准**：模拟超时场景，请求能在设定时间内退出并抛出超时异常；正常请求不受影响；多线程场景下不影响其他 task。

---

### 5.2 P0-2：单任务失败不传递到整体任务结果（P0）

**问题描述**：`fetch_pvc.py` `__main__` 中，`_run_minute_bars` 和 `_run_daily_bars` 的 `except Exception` 分支仅 `logger.error` 记录，不重新抛出、不返回失败状态。因此 `future.result()` 通常无法感知实际采集失败，整体任务可能在部分 task 失败时仍显示成功。

**代码位置**：`fetch_pvc.py` 第 1049-1132 行 `__main__`，`_run_minute_bars`（第 1056-1092 行）、`_run_daily_bars`（第 1094-1119 行）。

**证据**：代码中每个 `except` 分支只调用 `logger.error`，无 `raise`、无返回非零状态、无失败汇总。

**影响范围**：整体采集流程的失败感知机制；可能导致部分数据缺失却被误认为全部成功。

**置信度**：高（代码静态阅读可确认）。

**修复建议**：设计任务结果汇总及非零退出机制，单 task 失败时整体流程报告失败，且不修改已有文件。**不得将 `as_completed` 本身描述为有缺陷**；`as_completed` 仅是 futures 遍历工具，缺陷在于 task 内部异常处理和结果汇总缺失。

**验收标准**：单个采集任务失败时，整体流程能够报告失败（非零退出码或明确失败汇总），且不修改已有文件。

---

### 5.3 P0-3：重试机制与异常类型不匹配（P0）

**问题描述**：`_retryable_call` 仅对 `requests.RequestException` 进行指数退避重试，最多 3 次。AKShare 接口可能抛出的 `Length mismatch`、`ValueError`、`RuntimeError` 等异常不会被重试，也不会按类型分类处理；网络超时、限流、API 错误、数据解析异常混在一起处理不当。

**代码位置**：`fetch_pvc.py` 第 25-63 行 `_retryable_call`。

**证据**：`_retryable_call` 的 `except` 子句仅捕获 `requests.RequestException`，`ValueError`、`RuntimeError` 等直接向上抛出，无异常分类。

**影响范围**：所有 AKShare 接口调用的重试行为。

**置信度**：高。

**修复建议**：
- 增加异常分类：网络连接/请求异常（可考虑重试）、限流异常（需要更长退避）、API 错误（根据错误性质分类）、数据解析异常（不应默认无限或无条件重试）、`ValueError` 等参数或逻辑异常（原则上不重试）。
- 后续技术设计需给出：异常分类、最大重试次数、退避策略、日志要求。
- 不能简单建议捕获整个 `ak.AkshareException` 后统一重试。

**验收标准**：网络错误和限流错误按类型重试；`ValueError`/`RuntimeError`/数据格式异常不重试并直接抛出；重试次数和退避间隔可配置并可观测。

---

### 5.4 P1-1：分钟线、日线日期解析未向量化（P1）

**问题描述**：`separate_future_timestamps`、`update_minute_bars` 等函数使用 `iterrows` 逐行处理日期解析，大数据量下性能较差。

**代码位置**：`fetch_pvc.py` 第 777-830 行 `separate_future_timestamps`；第 880-933 行 `update_minute_bars`。

**验收标准**：向量化改造前后对同一输入输出结果一致（行数、字段值、排序和数据质量完全一致）。

---

### 5.5 P1-2：JSONL 多线程写入缺乏并发保护（P1）

**问题描述**：`append_jsonl` 读取全文、写临时文件再原子替换，并发场景下无文件锁，存在竞争/记录覆盖风险。

**代码位置**：`fetch_pvc.py` 第 560-622 行 `append_jsonl`。

**验收标准**：多线程并发写入同一 JSONL 文件，无记录丢失、无重复记录、文件不损坏。

---

### 5.6 P1-3：Shell 测试脚本存在误删正式 output 的风险（N2，P1）

**问题描述**：`tests/conftest.py` 的隔离只适用于 Python 测试（使用 `tempfile.TemporaryDirectory()`）。`tests/test_workflow_collect.sh` 有 8 处 `rm -rf output`，Shell 脚本在项目根目录执行时可能影响正式 output 数据。

**代码位置**：`tests/test_workflow_collect.sh` 第 17 行等。

**验收标准**：测试脚本仅操作临时目录，正式 `output/` 文件不被 `rm` 删除；执行前应有路径检查或使用临时工作目录。

---

### 5.7 P2-4：CSV 提交前质量门槛缺失（P2）

**问题描述**：缺少 CSV 全量质量检查与提交前质量门槛（重复主键、字段缺失、异常数值）。`merge_v0_data.py` 有简单校验但未集成到采集主流程提交前。

**验收标准**：校验能识别重复主键（`symbol`+`trading_date` / `symbol`+`datetime`）、字段缺失、异常数值（负价格、OHLC 逻辑错误）。

---

## 6. 性能问题

### 6.1 并发模型与任务数

`fetch_pvc.py` 使用 `ThreadPoolExecutor(max_workers=len(tasks))`，每个合约的每个流（分钟/日线）作为独立 task 提交，共 19 个 task（9 合约 × 2 流 + H11061 日线，H11061 无分钟线）。

**README 声明**（未经核实）：
- 15:00 后 18 个任务：总耗时缩减约 80%-90%，加速比 6-7x；
- 15:00 前 9 个任务：总耗时缩减约 70%-80%，加速比 3-4x。

**问题**：README 的 18/9 任务描述与当前代码（19 个 task）不一致；时间过滤发生在 task 内部，不是通过 task 生成数量实现；6–7 倍、3–4 倍加速比没有可靠基准证据。

### 6.2 性能验收原则

- 不直接把任意毫秒数的百分比作为硬性目标。
- 先建立可重复的基准：固定输入文件、Python 环境、执行命令和重复次数。
- 保存基准数据和 profiling 结果。
- 优化后必须保证行数、字段值、排序和数据质量完全一致。
- 性能改善依据重复测量判断，**不得将 cProfile 累计时间简单相加**（子函数累计耗时可能超过父函数耗时，因多次调用、递归或重叠计算导致）。

### 6.3 现状

- 工作区无独立的 cProfile 性能报告文件（无 `*.prof` 或性能报告 `.md`/`.txt`）。
- 未执行压力测试，无法给出资源占用结论。
- README 加速比声明属“未验证/需核实”项。

---

## 7. 安全性与操作风险

### 7.1 安全相关潜在风险（7 项，不得全部描述为“安全漏洞”）

| 序号 | 风险项 | 定性 | 说明与证据 | 建议处理 |
|------|--------|------|------------|----------|
| S-1 | `persist-credentials: true` | 潜在风险（非直接漏洞） | 工作流 checkout 使用 `token: ${{ secrets.GITHUB_TOKEN }}` 并 `persist-credentials: true`，后续 `git push` 可使用该凭据 | 结合当前“自动 push 数据到远程分支”的实际需求评估是否必需；如非必需建议设为 `false` |
| S-2 | `contents: write` 权限 | 潜在风险（非直接漏洞） | 工作流 `permissions: contents: write`，允许提交和推送数据文件 | 评估最小权限原则，仅在需要自动 push 时保留 |
| S-3 | `git push origin "HEAD:refs/heads/${GITHUB_REF_NAME}"` | 潜在风险（非直接漏洞） | 工作流自动推送数据变更，若触发频率高或分支检查放宽，可能意外覆盖分支 | 加强分支保护与推送目标确认 |
| S-4 | `subprocess.run(["git", "show", ...])` 无 `timeout` | 潜在风险（不直接等同于漏洞） | `merge_v0_data.py` 第 94/109 行，`subprocess.run` 无 `timeout` 参数 | 无 timeout subprocess 不应直接认定为漏洞，但建议补充 `timeout` 避免阻塞 |
| S-5 | AKShare 接口依赖（新浪财经） | 潜在风险（外部依赖） | 采集完全依赖 `ak.futures_zh_*` / `ak.futures_index_ccidx`，接口变更会影响采集 | 监控接口可用性，版本锁定 |
| S-6 | 测试脚本 `rm -rf output` | 误操作风险（非安全漏洞） | `tests/test_workflow_collect.sh` 第 17 行等 | 测试应限定临时目录，禁止操作正式 output |
| S-7 | 历史数据永久保留、文件无限增长 | 运营风险（非安全漏洞） | `merge_v0_data.py` / `fetch_pvc.py` 无数据保留策略 | 增加归档或保留策略 |

**安全性审查结论**：未发现可直接利用的代码层安全漏洞；7 项均为潜在风险/误操作风险/运营风险，应分级处理，其中 S-1/S-2 需结合自动 push 实际需求评估。**不得把“可推任意分支”直接描述成已证实的安全漏洞。**

### 7.2 工作流触发方式

- `.github/workflows/collect.yml` 仅 `workflow_dispatch` 手动触发，**无 `schedule`/`cron`、`repository_dispatch`**，确认无定时自动触发。
- 历史自动采集提交（`investigation_report.md`）均由手动触发工作流产生，非 cron。
- 不得把 `workflow_dispatch` 描述成定时采集。

### 7.3 工作流分支限制放宽（N3，P2）

- 当前 workflow 仅检查 `GITHUB_REF_TYPE == branch`，**不再限定特定分支名**（旧版曾强制 `release/pvc-nine-contracts`）。
- `release/pvc-nine-contracts` 分支仍然存在。
- 需要明确允许触发和推送的分支范围。
- 定为 P2，**不得把“可推任意分支”直接描述成已证实的安全漏洞**。

---

## 8. Git、workflow 和发布管理

### 8.1 版本基准差异（P2，不再是 P0）

- 本地 `main`（fb97907）与远程 `origin/main`（bdecae1）SHA 不一致。
- 独立复核确认源码零差异，差异仅体现在 10 个数据 CSV 文件上，远程多出的提交为自动采集数据提交。
- 属于审计基准和数据同步问题，**不得继续列为 P0 代码缺陷**。
- 降为 P2：本地与远程审计基准差异。

### 8.2 README push retry 描述错误（N4，低优先级文档问题）

- README 声称 "push failure retries up to 3 times"，但当前 workflow 只有一次 `git push`，**没有对应重试循环**。
- 属文档与代码不符，需修正 README 或补充工作流重试逻辑。

### 8.3 CI 工作流未集成单元测试

- 工作流只执行 `python fetch_pvc.py` 采集并提交数据，未调用 `python -m unittest discover -s tests`，这是 CI/CD 覆盖缺口。

### 8.4 H11061 旧文件状态（修正）

- `output/H11061_daily_bars.csv` 在本地 `main` HEAD 中存在，在 `origin/main` 中也存在。
- 当前 working tree 显示为已删除，但删除尚未提交。
- `output/H11061_index_daily.csv` 是新的独立指数日线文件。
- 不得把工作区删除状态说成已经从 GitHub 删除。

---

## 9. 独立复核意见及逐项裁决

独立复核报告正文未以附件形式随本次对话提供，但其纠正要点已以 V2 任务指令形式固化。下表对 V1 报告中被独立复核指出的事项进行逐项裁决：

| V1 事项 | 独立复核纠正要求 | V2 裁决 |
|---------|----------------|---------|
| P0-1 版本不一致列为 P0 确定缺陷 | 从 P0 移除，降为 P2 版本基准问题；源码零差异，仅 10 个数据 CSV 不同；不得沿用“47+ 提交差异” | 已执行：P0-1 移除，改为 P2 版本基准差异 |
| P0-5 quality 日志不存在列为确定缺陷 | 从确定缺陷删除，改为未验证事项；文件不存在 ≠ 功能从未运行 | 已执行：P0-5 移除，改为 U-4 |
| P0-4 HTTP timeout 修复建议 | 不能直接给外层 AKShare 函数增加 timeout 参数；AKShare 函数内部调用 requests.get，签名无 timeout；实现方式待技术设计；列出候选方案及 monkeypatch 多线程影响 | 已执行：P0-4 保留 P0，修正修复建议 |
| P0-2 单任务失败 | 补充精确失败传播机制；不将 as_completed 本身描述为有缺陷 | 已执行：补充机制说明，澄清 as_completed 无缺陷 |
| P0-3 重试异常类型 | 不能简单建议捕获 ak.AkshareException 统一重试；增加异常分类 | 已执行：增加异常分类要求 |
| output 文件数 | 修正为 20 个 CSV；0 字节不计入有效数据 | 已执行 |
| README 任务数/加速比 | 代码实际 19 个 task；README 18/9 不一致；加速比无基准；push retry 描述与单次 push 不符 | 已执行 |
| H11061 旧文件 | 工作区删除未提交，不得说成已从 GitHub 删除；新旧文件并存需明确迁移策略 | 已执行 |
| 新增 N1-N5 | merge 远程覆盖语义、Shell 测试隔离、工作流分支放宽、README push retry、H11061 新旧文件 | 已执行 |

**冲突记录**：V1 与独立复核在 P0-1 定级、P0-5 定性、P0-4 修复方案可行性上存在冲突，V2 已按独立复核要求裁决，不再沿用 V1 原表述。

---

## 10. P0/P1/P2/P3 问题总表

### P0：采集可靠性（3 项）

| 编号 | 问题 | 类型 | 文件位置 | 验收标准 |
|------|------|------|----------|----------|
| P0-1 | （已移除，降为 P2 版本基准差异） | — | — | — |
| P0-2 | AKShare HTTP 请求缺少有效 timeout | 确定缺陷 | `fetch_pvc.py` AKShare 调用处 | 模拟超时场景，请求能在设定时间内退出并抛出超时异常；正常请求不受影响；多线程场景不影响其他 task |
| P0-3 | 重试机制与异常类型不匹配 | 确定缺陷 | `fetch_pvc.py` 第 25-63 行 `_retryable_call` | 网络错误和限流错误按类型重试；`ValueError`/`RuntimeError`/数据格式异常不重试并直接抛出；重试次数和退避间隔可配置 |
| P0-4 | 单任务失败不传递到整体任务结果 | 确定缺陷 | `fetch_pvc.py` 第 1049-1132 行 `__main__` | 单 task 失败时整体流程报告失败（非零退出码或明确失败汇总），且不修改已有文件 |

> 注：编号按 V2 新顺序排列，P0-1 已移除。

### P1：数据处理与操作安全（3 项）

| 编号 | 问题 | 类型 | 文件位置 | 验收标准 |
|------|------|------|----------|----------|
| P1-1 | 分钟线、日线日期解析未向量化 | 改进建议 | `fetch_pvc.py` `separate_future_timestamps`/`update_minute_bars` | 向量化改造前后输出结果一致（行数、字段值、排序、数据质量） |
| P1-2 | JSONL 多线程写入缺乏并发保护 | 潜在风险 | `fetch_pvc.py` 第 560-622 行 `append_jsonl` | 多线程并发写入同一 JSONL 文件，无记录丢失、无重复记录、文件不损坏 |
| P1-3 | Shell 测试脚本存在误删正式 output 的风险 | 确定缺陷（误操作风险） | `tests/test_workflow_collect.sh` 第 17 行等 | 测试脚本仅操作临时目录，正式 `output/` 文件不被 `rm` 删除 |

### P2：工作流、数据质量和维护（6 项）

| 编号 | 问题 | 类型 | 文件位置 | 验收标准 |
|------|------|------|----------|----------|
| P2-1 | 本地与远程审计基准差异 | 版本基准问题 | `git rev-parse main origin/main` | 明确以哪个版本为修复基准，避免在不一致基准上修改 |
| P2-2 | README 任务数量、加速比和 push retry 描述错误 | 文档问题 | `README.md` | README 任务数与代码一致；加速比声明有基准或删除；push retry 描述与工作流一致 |
| P2-3 | 工作流分支范围约束 | 潜在风险 | `.github/workflows/collect.yml` 第 45-48 行 | 明确允许触发和推送的分支范围，不将“可推任意分支”描述为已证实漏洞 |
| P2-4 | CSV 提交前质量门槛缺失 | 改进建议 | `merge_v0_data.py` / 采集主流程 | 校验能识别重复主键、字段缺失、异常数值 |
| P2-5 | 全量读写、依赖锁定、缓存和并发策略 | 潜在风险/改进建议 | `fetch_pvc.py`/`requirements.txt`/`.github/workflows/collect.yml` | 依赖版本锁定；工作流缓存和并发策略优化 |
| P2-6 | merge_v0_data.py 远程数据覆盖语义 | 设计风险（不直接认定为 bug） | `merge_v0_data.py` | 明确远程数据是否有意作为权威来源 |

### P3：低优先级维护事项（4 项）

| 编号 | 问题 | 类型 | 文件位置 |
|------|------|------|----------|
| P3-1 | 0 字节 H11061 分钟线占位文件策略 | 改进建议 | `output/H11061_minute_bars.csv` |
| P3-2 | H11061 旧新日线文件迁移与清理策略 | 改进建议 | `output/H11061_daily_bars.csv` / `H11061_index_daily.csv` |
| P3-3 | 历史断言数字（4229/2044）与实际不符 | 改进建议 | `merge_v0_data.py` 第 400-401 行 |
| P3-4 | 备份文件管理和注释等维护事项 | 改进建议 | `.kilo/phase4_backup/`、README 注释 |

---

## 11. 修复路线图和依赖关系

### 阶段 1：P0 采集可靠性（阻塞，优先处理）

1. AKShare HTTP 请求超时（待技术设计：候选方案 monkeypatch/封装/替代实现，分析多线程影响）
2. 重试机制异常分类（网络/限流/API/解析/参数异常分类、最大重试、退避策略、日志）
3. 单任务失败传递到整体任务结果（任务结果汇总、非零退出机制）

**依赖关系**：3 项相对独立，可并行设计；超时方案需先完成技术设计再实施。

### 阶段 2：P1 数据处理与操作安全

1. 日期解析向量化（需保证前后输出一致）
2. JSONL 并发安全写入（需文件锁或替代并发安全策略）
3. Shell 测试防止误删正式 output（限定临时目录或路径检查）

### 阶段 3：P2 工作流、数据质量和维护

1. 本地与远程版本基准对齐策略（需用户批准 Git 操作）
2. README 任务数、加速比、push retry 描述修正
3. 工作流分支范围明确
4. CSV 提交前质量门槛
5. 依赖版本锁定、工作流缓存和并发策略
6. merge_v0_data.py 远程数据覆盖语义确认

### 阶段 4：P3 低优先级维护

1. H11061 0 字节占位文件策略
2. H11061 旧新文件迁移与清理
3. 历史断言数字清理
4. 备份文件管理、注释统一

---

## 12. 每项问题的验收标准

| 修复项 | 验收标准（可执行，不得只写“测试通过”） |
|--------|--------------------------------------|
| AKShare HTTP 超时 | 模拟超时场景，请求能在设定时间内退出并抛出超时异常；正常请求不受影响；多线程场景下不影响其他 task |
| 异常类型与重试匹配 | 网络错误和限流错误按类型重试（指数退避）；`ValueError`/`RuntimeError`/数据格式异常不重试并直接抛出；重试次数和退避间隔可配置并可观测 |
| 单任务失败传递 | 单个采集任务失败时，整体流程能够报告失败（非零退出码或明确失败汇总），且不修改已有文件 |
| 日期解析向量化 | 向量化改造前后对同一输入输出结果一致（行数、字段值、排序和数据质量完全一致） |
| JSONL 并发写入 | 多线程并发写入同一 JSONL 文件，无记录丢失、无重复记录、文件不损坏 |
| 测试防误删 | 测试脚本仅操作临时目录，正式 `output/` 文件不被 `rm` 删除 |
| CSV 全量质量检查 | 校验能识别重复主键（`symbol`+`trading_date` / `symbol`+`datetime`）、字段缺失、异常数值（负价格、OHLC 逻辑错误） |
| 工作流权限 | `persist-credentials` 与 `contents: write` 是否保留，基于自动 push 实际需求作出文档化决定 |
| subprocess timeout | `git show` 等子进程增加 `timeout`，超时退出不阻塞主流程 |
| 行数矛盾核实 | 以当前代码重新生成 V0 日线/分钟线，记录实际行数，说明与 4229/2044/2058/2396 的差异原因 |

---

## 13. 未验证事项和证据限制

| 序号 | 未验证事项 | 原因 |
|------|------------|------|
| U-1 | AKShare 真实接口采集是否成功（网络可达性、限流、接口变更） | 测试使用 Mock，未重新运行采集 |
| U-2 | 数据完整性全量校验结果（重复主键、字段缺失、异常数值） | V0 行数三方矛盾未解决，未运行全量质量检查 |
| U-3 | H11061 969 条数据的质量状态（`quality_status` 分布、价格异常） | 仅确认行数，未做字段级质量校验 |
| U-4 | `output/minute_data_quality.jsonl` 不存在是否代表“未产生异常”还是“功能未运行” | 文件缺失，无法区分 |
| U-5 | README 加速比声明准确性；性能基准未建立 | 无性能报告文件，未执行压力测试 |
| U-6 | 工作流 `persist-credentials: true` + `contents: write` 是否符合最小权限与实际自动 push 需求 | 需结合运维需求评估 |
| U-7 | `subprocess.run(["git","show",...])` 无 timeout 在实际运行中的阻塞风险 | 代码层确认，未运行压力场景 |
| U-8 | CI 工作流是否应集成单元测试运行 | 工作流当前未执行测试 |
| U-9 | 本地 `main` 与远程 `origin/main` 的差异内容（10 个数据 CSV） | 仅确认 SHA 不同，未 diff 内容；独立复核已确认源码零差异 |

**证据限制**：本报告全部基于静态代码阅读、Git 元数据只读查询和数据文件行数抽查；未运行真实采集、未触发 GitHub Actions、未执行压力测试、未执行 `merge_v0_data.py`。所有未验证事项均不得作为已确认缺陷。

---

## 14. 暂不建议实施的变更

| 变更 | 不建议实施的理由 |
|------|------------------|
| 删除 `output/H11061_minute_bars.csv` 空占位并宣告“正式迁移完成” | 旧文件删除 ≠ 正式迁移完成；H11061 迁移需代码、数据、文档、工作流全部一致后方可宣告 |
| 将 `workflow_dispatch` 改为 `schedule` 定时触发 | 当前设计为 NAS 手动触发，变更触发方式属运营决策，需用户单独批准 |
| 把 19 个采集任务等同于每轮全部成功 | 任务提交数 ≠ 成功数，需按单任务结果汇总 |
| 将 `persist-credentials: true` + `contents: write` 直接关闭或直接保留 | 需先结合自动 push 实际需求评估，不宜在审计阶段单方面改动 |
| 将无 `timeout` 的 `subprocess` 直接定为安全漏洞并删除 | 无 timeout ≠ 漏洞，应补充 `timeout` 而非删除功能 |
| 因 `minute_data_quality.jsonl` 不存在就认定过滤功能从未运行 | 缺失日志 ≠ 功能未运行，需补充证据 |
| 按任一单一行数（4229/2044/2058/2396）认定数据完整 | 三方数据矛盾，必须并列待核实 |
| 给外层 AKShare 函数直接增加 `timeout` 参数 | AKShare 1.2.0 相关函数签名无 `timeout`，内部直接调用 `requests.get`，不可直接实施 |

---

## 15. 完成声明

本阶段仅处理审计报告修订，不实施任何代码修复，不进入开发阶段。

**明确声明**：
- 未修改任何 Python、Shell、YAML、CSV 或 README 源文件。
- 未运行真实采集。
- 未触发 GitHub Actions。
- 未执行可能修改 output 的测试。
- 未执行 `merge_v0_data.py`。
- 未执行 Git pull、fetch、checkout、reset、clean。
- 未删除、应用或弹出 stash。
- 未删除备份文件。
- 未 commit、push 或创建 PR。
- 未调用 Code Agent 开始修复。

V2 报告文件路径：`.kilo/plans/1793796003000-final-audit-report-v2.md`

等待用户审核 V2，不要自动进入代码修复阶段。
