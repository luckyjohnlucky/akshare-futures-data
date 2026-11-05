# akshare-futures-data 项目最终审计总报告

**项目路径**：`/Users/johnm/Projects/akshare-futures-data`
**报告性质**：仅汇编已完成审计模块的证据，**不实施任何修复**
**审计基准**：工作区当前状态（只读取现有文件、Git 元数据、代码与测试；不重新运行采集、不触发 GitHub Actions、不执行压力测试、不修改任何源代码/配置/数据）

---

## 1. 项目概况与审计基准

### 1.1 项目基本信息

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
| 数据输出目录 | `output/`（19 个 CSV 文件，其中 H11061_minute_bars.csv 为 0 字节空占位） |
| 备份目录 | `.kilo/phase4_backup/`（含 `V0_daily_bars.csv.pre_merge`、`V0_minute_bars.csv.pre_merge` 等） |
| 本地备份分支 | `backup/local-before-merge`、`backup/remote-before-merge`（仅存在于本地，不存在于远程） |

### 1.2 Git 版本基准（必须区分本地与远程）

经 `git rev-parse` 确认：

| 分支 | SHA（完整） | 说明 |
|------|-------------|------|
| 本地 `main` | `fb97907fcb2678450abdd33d85ac32c3f19e2264` | 提交信息：`feat: add H11061 index daily line independent structure (B1-B3)` |
| 远程 `origin/main` | `bdecae1687bd7c48442fb24f8aaaf7cbd2695bc0` | 提交信息：`chore: auto-collect commodity futures data (2026-11-04T09:40:39Z)` |
| 远程 HEAD 指向 | `remotes/origin/HEAD -> origin/main` | |

**结论**：本地 `main` 与远程 `origin/main` SHA 不一致，本地落后远程。报告中所有版本引用必须明确标注“本地”或“远程”，不得混用。`.kilo/plans/1793711576733-h11061-index-daily-plan.md` 中记载的旧 SHA（本地 `9b94b5e`、远程 `2fa46b7`、领先 47 个提交）已过时，不应作为当前基准。

### 1.3 审计基准与限制

- 只汇编现有证据，不重新运行采集、不触发 GitHub Actions、不执行压力测试。
- 不修改项目代码、README、配置或数据；不执行 `git add/commit/push/pull/reset/clean`、`stash`；不删除备份或未跟踪文件；不自行创建修复分支。
- 已有审计报告之间存在矛盾时，明确列出，不自行猜测或选择其中一个数字。
- 明确区分：确定缺陷、潜在风险、改进建议、未验证事项。

---

## 2. 审计范围和方法

### 2.1 11 个审计模块（全部已完成，本报告汇编）

| 序号 | 审计模块 | 主要证据来源 |
|------|----------|--------------|
| 1 | Git 工作区状态 | `git status`、`git branch -vv`、`git rev-parse`、`investigation_report.md` |
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

### 2.2 证据文件清单（已读取）

| 文件 | 类型 | 关键信息 |
|------|------|----------|
| `investigation_report.md` | Git/工作流审计 | 本地 main fb97907 vs 远程 bdecae1；仅 `workflow_dispatch` 触发，无 `schedule`/`cron`/`repository_dispatch`；自动采集提交由手动触发工作流产生 |
| `.kilo/plans/1793794755058-final-audit-report.md` | 审计报告骨架 | 14 章结构、证据清单、8 项关键矛盾点（均未填充正文） |
| `.kilo/plans/1793711576733-h11061-index-daily-plan.md` | H11061 计划 | 过时的 Git 基准（9b94b5e/2fa46b7、领先 47 提交）；B1-B3 函数实现状态；14+8 测试 |
| `.kilo/plans/pvc-final-review.md` | 功能/数据验证 | 25/25 测试通过（旧计数）；V0 日线 4230 行、V0 分钟线 2058 行（与当前实测 2396 行矛盾）；声明“可进行生产部署” |
| `.kilo/plans/pvc-contract-data-review.md` | 架构/接口验证 | AKShare 1.20.0、具体合约 V2701/V2705/V2709 可获取、V2801 等未挂牌 |
| `fetch_pvc.py` | 核心代码 | 10 合约 + H11061，`ACTIVE_CONTRACTS`；并行采集、`_retryable_call`（仅重试 `requests.RequestException`）、原子写入、`append_jsonl` 无锁 |
| `merge_v0_data.py` | 合并脚本 | 预期 4229/2044 行；`subprocess.run` 执行 `git show`（无 `timeout`）；10 个成交量冲突硬编码 |
| `.github/workflows/collect.yml` | CI/CD | `workflow_dispatch` 手动触发；`permissions: contents: write`；`persist-credentials: true`；推送到 `${GITHUB_REF_NAME}`；分支检查已放宽（仅判断是 branch，不再限定 release/pvc-nine-contracts） |
| `tests/test_daily_quality.py` | 单元测试 | 11 个测试 |
| `tests/test_minute_quality.py` | 单元测试 | 14 个测试 |
| `tests/test_json_csv_consistency.py` | 单元测试 | 7 个测试 |
| `tests/test_failure_safety.py` | 单元测试 | 4 个测试 |
| `tests/test_index_daily.py` | 单元测试 | 14 个测试 |
| `tests/test_workflow_collect.sh` | 工作流测试 | 8 个场景（`rm -rf output` 操作测试目录） |
| `tests/conftest.py` | 测试配置 | 所有输出重定向到临时目录，不读写正式数据 |
| `output/` | 数据抽查 | V0_daily 4231 行（4230 数据）、V0_minute 2397 行（2396 数据）、H11061_index 970 行（969 数据）、H11061_minute 0 字节 |
| `output/minute_data_quality.jsonl` | 质量日志 | **文件不存在** |
| `requirements.txt` | 依赖 | 版本范围宽松（`<2.0`、`<3.0`、`<4.0`） |

### 2.3 审计方法

- 代码静态阅读：完整读取 `fetch_pvc.py`、`merge_v0_data.py`、工作流文件、全部测试文件。
- Git 元数据只读：`git status`、`git branch -vv`、`git rev-parse main origin/main`、`git log --oneline -5`。
- 数据文件抽查：`wc -l` 统计 `output/` 中 CSV 行数（含表头）。
- 证据交叉核对：将各审计模块的数字（行数、测试数、SHA）相互对照，找出矛盾并列出，不自行裁决。

---

## 3. 总体审计结论

项目代码结构清晰，采集/验证/去重/原子写入分层明确；单元测试使用临时目录与 Mock，未接触真实网络和正式数据，测试隔离性良好；H11061 指数日线已实现独立采集流程（`normalize_index_daily_bars` / `validate_index_daily_bars` / `update_index_daily_bars`）并配有 14 个单元测试。

**但存在若干需在修复阶段解决的问题**：本地与远程 `main` 版本不一致；11 个审计模块的部分数字互相矛盾（V0 行数、测试总数、H11061 验证状态）；README 中“19 个采集任务”“加速比 6-7x”等声明与实际需核对；工作流仅 `workflow_dispatch` 手动触发，不应描述为定时采集；`merge_v0_data.py` 中 `subprocess` 无 `timeout` 且含硬编码断言；`output/minute_data_quality.jsonl` 不存在；无独立的性能报告（cProfile）和安全审查报告文件。

**总体结论**：代码逻辑层基本可用，但数据完整性、版本一致性、文档准确性、工作流权限与安全分级等方面存在确认缺陷和潜在风险，**建议先进入修复阶段处理 P0 缺陷，再进行正式发布**。详见第 14 章最终验收意见。

---

## 4. 已确认的问题（按严重程度排序）

下表区分“确定缺陷”“潜在风险”“改进建议”“未验证事项”。同一严重程度内按发现顺序列出。

### P0 - 确定缺陷（阻塞，建议首批修复）

| 编号 | 问题 | 类型 | 证据与位置 |
|------|------|------|------------|
| P0-1 | 本地 `main`（fb97907）与远程 `origin/main`（bdecae1）SHA 不一致，版本基准混乱 | 确定缺陷 | `git rev-parse main origin/main`；`investigation_report.md` 第 1 章 |
| P0-2 | `fetch_pvc.py` 主循环中各采集任务异常仅被 `try/except` 捕获并写日志，**单个任务失败不传递到整体任务结果**，`__main__` 通过 `future.result()` 仅确认完成，整体流程不会因单流失败而报告失败 | 确定缺陷 | `fetch_pvc.py` 第 1049-1132 行，`_run_minute_bars`/`_run_daily_bars` 均只 `logger.error` 不抛出 |
| P0-3 | `fetch_pvc.py` 对 AKShare 接口调用仅通过 `_retryable_call` 重试 `requests.RequestException`，**AKShare 异常类型（如 `Length mismatch`、`ValueError`、`RuntimeError`）与重试机制不匹配**，网络超时/限流未按类型分类重试 | 确定缺陷 | `fetch_pvc.py` 第 25-63 行 `_retryable_call`，第 1069/1090/1115 行异常分支 |
| P0-4 | `fetch_pvc.py` 无 HTTP 请求超时参数控制，AKShare/底层请求可能无限期阻塞 | 确定缺陷 | `fetch_pvc.py` 调用 `ak.futures_zh_minute_sina` / `ak.futures_zh_daily_sina` / `ak.futures_index_ccidx` 无超时 |
| P0-5 | `output/minute_data_quality.jsonl` 质量日志文件不存在，无法判定未来时间戳过滤功能是否曾运行 | 确定缺陷（状态确认） | `ls output/minute_data_quality.jsonl` 返回 "No such file or directory" |

### P1 - 确定缺陷 / 改进建议（高优先级）

| 编号 | 问题 | 类型 | 证据与位置 |
|------|------|------|------------|
| P1-1 | 分钟线、日线日期解析未向量化（`iterrows` 逐行处理），大数据量下性能较差 | 改进建议 | `fetch_pvc.py` `separate_future_timestamps`（第 777-830 行）、`update_minute_bars`（第 880-933 行） |
| P1-2 | `append_jsonl` 读取全文、写临时文件再原子替换，**并发场景下无文件锁，存在竞争/记录覆盖风险** | 潜在风险 | `fetch_pvc.py` 第 560-622 行 `append_jsonl` |
| P1-3 | 缺少 CSV 全量质量检查与提交前质量门槛（重复主键、字段缺失、异常数值） | 改进建议 | `merge_v0_data.py` 有简单校验但未集成到采集主流程提交前 |
| P1-4 | 测试脚本 `test_workflow_collect.sh` 含 `rm -rf output`，**误删正式 output 数据的风险** | 确定缺陷（误操作风险） | `tests/test_workflow_collect.sh` 第 17 行 `rm -rf output` |
| P1-5 | README 声明“19 个采集任务”与“加速比 6-7x/3-4x”未经当前代码核实，可能不准确 | 改进建议 | README 第 33-35 行；实际任务数 = 9 合约 × 2 流 + H11061 日线 = 19（任务数本身巧合一致，但“每轮全部成功”未验证） |

### P2 - 潜在风险 / 改进建议（中优先级）

| 编号 | 问题 | 类型 | 证据与位置 |
|------|------|------|------------|
| P2-1 | 日线全量下载、全量排序和写回优化未评估，历史数据无保留策略，文件无限增长 | 潜在风险 | README "Known Limitations" 数据保留策略；`update_daily_bars` 全量读取再写回 |
| P2-2 | 工作流缓存和任务并发策略未优化；`cancel-in-progress: false` | 改进建议 | `.github/workflows/collect.yml` 第 9-11 行 |
| P2-3 | 依赖版本锁定策略缺失，`requirements.txt` 使用宽松范围 | 改进建议 | `requirements.txt` |
| P2-4 | 工作流推送到 `${GITHUB_REF_NAME}`，分支检查已放宽为仅判断 `GITHUB_REF_TYPE == branch`，不再强制 `release/pvc-nine-contracts` | 潜在风险 | `.github/workflows/collect.yml` 第 45-48 行（对比 investigation_report.md 旧版强制限定） |

### P3 - 低优先级维护事项

| 编号 | 问题 | 类型 | 证据与位置 |
|------|------|------|------------|
| P3-1 | 备份目录 `.kilo/phase4_backup/` 管理策略缺失 | 改进建议 | 目录下存在 `*.pre_merge` 及多个 V2701/V2705/V2709 文件 |
| P3-2 | `output/H11061_minute_bars.csv` 为 0 字节空占位文件，策略不明 | 改进建议 | `output/` 目录列表，0 字节 |
| P3-3 | `merge_v0_data.py` 一次性合并脚本的旧行数断言（4229/2044）与实际不符，为一次性脚本 | 改进建议 | `merge_v0_data.py` 第 400-401 行 |
| P3-4 | 注释中英混杂，影响阅读体验 | 改进建议 | README "Known Limitations" 注释语言条目 |

---

## 5. 潜在风险与改进建议

### 5.1 安全相关潜在风险（7 项，不得全部描述为“安全漏洞”）

经 `.github/workflows/collect.yml` 和 `fetch_pvc.py` 审查，识别出 7 项潜在风险，须分级描述，**不得全部定性为安全漏洞**：

| 序号 | 风险项 | 定性 | 说明与证据 | 建议处理 |
|------|--------|------|------------|----------|
| S-1 | `persist-credentials: true` | 潜在风险（非直接漏洞） | 工作流 checkout 使用 `token: ${{ secrets.GITHUB_TOKEN }}` 并 `persist-credentials: true`，后续 `git push` 可使用该凭据 | 结合当前“自动 push 数据到远程分支”的实际需求评估是否必需；如非必需建议设为 `false` |
| S-2 | `contents: write` 权限 | 潜在风险（非直接漏洞） | 工作流 `permissions: contents: write`，允许提交和推送数据文件 | 评估最小权限原则，仅在需要自动 push 时保留 |
| S-3 | `git push origin "HEAD:refs/heads/${GITHUB_REF_NAME}"` | 潜在风险（非直接漏洞） | 工作流自动推送数据变更，若触发频率高或分支检查放宽，可能意外覆盖分支 | 加强分支保护与推送目标确认 |
| S-4 | `subprocess.run(["git", "show", ...])` 无 `timeout` | 潜在风险（不直接等同于漏洞） | `merge_v0_data.py` 第 94/109 行，`subprocess.run` 无 `timeout` 参数 | 无 timeout subprocess 不应直接认定为漏洞，但建议补充 `timeout` 避免阻塞 |
| S-5 | AKShare 接口依赖（新浪财经） | 潜在风险（外部依赖） | 采集完全依赖 `ak.futures_zh_*` / `ak.futures_index_ccidx`，接口变更会影响采集 | 监控接口可用性，版本锁定 |
| S-6 | 测试脚本 `rm -rf output` | 误操作风险（非安全漏洞） | `tests/test_workflow_collect.sh` 第 17 行 | 测试应限定临时目录，禁止操作正式 output |
| S-7 | 历史数据永久保留、文件无限增长 | 运营风险（非安全漏洞） | `merge_v0_data.py` / `fetch_pvc.py` 无数据保留策略 | 增加归档或保留策略 |

**安全性审查结论**：未发现可直接利用的代码层安全漏洞；7 项均为潜在风险/误操作风险/运营风险，应分级处理，其中 S-1/S-2 需结合自动 push 实际需求评估。

### 5.2 非安全类改进建议

- 分钟线/日线日期解析向量化（P1-1）。
- JSONL 并发安全与增量写入（P1-2）。
- CSV 提交前质量门槛（P1-3）。
- 测试脚本防止误删正式 output（P1-4）。
- 依赖版本锁定（P2-3）。
- 工作流分支检查收紧（P2-4）。

---

## 6. 数据完整性审查结论

### 6.1 现有数据文件行数（实测证据）

`wc -l` 统计（行数含 1 行表头，数据行 = 行数 - 1）：

| 文件 | 总行数 | 数据行 | 备注 |
|------|--------|--------|------|
| `output/V0_daily_bars.csv` | 4231 | 4230 | |
| `output/V0_minute_bars.csv` | 2397 | 2396 | |
| `output/H11061_index_daily.csv` | 970 | 969 | **969 条真实数据** |
| `output/H11061_minute_bars.csv` | 1（0 字节） | 0 | 空占位文件 |

### 6.2 已确认的行数矛盾（必须并列，待核实，不得自行选择）

同一数据的三个不同来源给出不同数字，**矛盾未解决，必须在报告中明确列出并列为待核实**：

| 数据项 | merge_v0_data.py 预期 | pvc-final-review.md 报告 | 当前实测（`wc -l`） | 状态 |
|--------|----------------------|------------------------|---------------------|------|
| V0 日线数据行 | 4229 | 4230 | 4230 | **矛盾：4229 vs 4230** |
| V0 分钟线数据行 | 2044 | 2058 | 2396 | **矛盾：2044 vs 2058 vs 2396（三个不同数字）** |

**结论**：不得仅凭某一数字认定数据完整性。V0 日线 4230 行与 pvc-final-review 一致，但与 merge 脚本预期 4229 不符；V0 分钟线三方数据均不一致（2044 / 2058 / 2396），必须在修复阶段以当前代码重新跑一致性校验后以实际为准，并说明差异原因。

### 6.3 H11061 验证状态纠正

- `pvc-final-review.md` 及早期计划曾将 H11061 指数日线标记为“未验证”。
- **实测证据**：`output/H11061_index_daily.csv` 共 970 行，扣除表头后 **969 条真实数据**，不应再标记为“未验证”。
- `output/H11061_minute_bars.csv` 为 0 字节，符合“指数无分钟线”的设计（空占位）。

### 6.4 质量日志不存在 ≠ 过滤功能从未运行

`output/minute_data_quality.jsonl` 文件不存在，但这**不能**推断为 `separate_future_timestamps` / `filter_future_anomalies` 从未运行；可能是本次采集未产生未来时间戳异常，或日志被清理/未生成。此项列为“未验证事项”，不得作为功能缺失的定论。

### 6.5 数据完整性审查结论

数据文件存在且行数可核对，但存在 V0 行数三方矛盾；H11061 已有 969 条真实数据；质量日志缺失。数据完整性**未通过全面验收**，需在修复阶段以 CSV 全量质量检查（重复主键、字段缺失、异常数值）并列出差异原因后方可认定。

---

## 7. 安全性审查结论

详见第 5.1 章。总结：

- 工作流触发方式为 `workflow_dispatch`（手动），**无 `schedule`/`cron`、`repository_dispatch`**，确认无定时自动触发。
- 工作流仅在 `GITHUB_REF_TYPE == branch` 时运行（旧版曾强制 `release/pvc-nine-contracts`，当前已放宽）。
- `persist-credentials: true` + `contents: write` 配合自动 `git push`，需结合当前自动 push 实际需求评估最小权限。
- `subprocess` 无 `timeout` **不直接等同于安全漏洞**，属潜在风险，建议补充 `timeout`。
- 未发现直接可利用的代码层安全漏洞；7 项风险应分级描述，不得全部定性为“安全漏洞”。

**安全性审查结论**：总体可控，无高危安全漏洞证据；7 项潜在风险需分级处理，其中 S-1/S-2 需用户结合自动 push 需求决定。

---

## 8. 性能与资源审查结论

### 8.1 并发模型

`fetch_pvc.py` 使用 `ThreadPoolExecutor(max_workers=len(tasks))`，每个合约的每个流（分钟/日线）作为独立任务提交。README 声明：
- 15:00 后 18 个任务：总耗时缩减约 80%-90%，加速比 6-7x；
- 15:00 前 9 个任务：总耗时缩减约 70%-80%，加速比 3-4x。

**实际任务数**：9 合约 × 2 流 + H11061 日线 = 19 个任务（H11061 无分钟线）。19 个任务的提交**不等于**每轮全部成功；单任务失败仅记录日志，不影响其他任务，也不会使整体流程报告失败（见 P0-2）。

### 8.2 cProfile 性能数据注意事项

**未发现独立的 cProfile 性能报告文件**（工作区无 `*.prof` 或性能报告 `.md`/`.txt`）。若后续引入 cProfile 数据，必须注意：cProfile 累计耗时（cumulative time）中子函数耗时可能超过父函数耗时（多次调用、递归或重叠计算导致），**不得将各项时间直接相加**作为总耗时。

### 8.3 性能与资源审查结论

并发模型合理，故障隔离好；但缺少可追溯的量化性能报告（cProfile 等），README 中的加速比声明未经当前代码与数据量核实，属“未验证/需核实”项。资源占用方面，无压力测试数据，无法给出结论。

---

## 9. 测试与 CI/CD 验证情况

### 9.1 单元测试数量

经 `grep "def test_"` 统计：

| 测试文件 | 测试用例数 |
|----------|------------|
| `tests/test_daily_quality.py` | 11 |
| `tests/test_minute_quality.py` | 14 |
| `tests/test_json_csv_consistency.py` | 7 |
| `tests/test_failure_safety.py` | 4 |
| `tests/test_index_daily.py` | 14 |
| **Python 单元测试合计** | **50** |
| `tests/test_workflow_collect.sh` | 8 个场景 |
| **全部测试项合计** | **58** |

`pvc-final-review.md` 中的“25/25 通过”属旧计数（未包含 H11061 14 个测试与工作流 8 个场景），与当前 50+8 不一致，应以当前代码为准。

### 9.2 测试隔离性

`tests/conftest.py` 和各测试文件均使用 `tempfile.TemporaryDirectory()` 并 Mock 网络，README 明确："All tests use temporary directories and Mocks, do not access the real network, do not read or write formal data files." **测试不触碰正式 output 数据**。

### 9.3 重要限制（必须注明）

- **50 个测试通过 ≠ 真实采集通过**：测试不访问真实网络，不等同于 AKShare 接口真实采集成功。
- **50 个测试通过 ≠ 数据完整性验收通过**：V0 行数矛盾未解决，H11061 虽有 969 条数据但未做全量质量校验。
- **50 个测试通过 ≠ 性能验收通过**：无 cProfile/压力测试数据。

### 9.4 CI/CD 工作流

- `.github/workflows/collect.yml`：`workflow_dispatch` 手动触发，`actions/checkout@v4`（`persist-credentials: true`），`actions/setup-python@v5`（Python 3.11），缓存 pip，安装 `requirements.txt`，运行 `python fetch_pvc.py`，提交并推送变更到 `${GITHUB_REF_NAME}`。
- 触发方式确认为**手动触发**，不得描述为“定时采集”或“每 5 分钟自动采集”。历史自动采集提交（`investigation_report.md`）均由手动触发工作流产生，非 cron。
- 工作流未在 CI 中运行 Python 单元测试（工作流只执行 `fetch_pvc.py` 采集并提交数据，未调用 `python -m unittest discover -s tests`），这是 CI/CD 覆盖缺口。

**测试与 CI/CD 验证结论**：50 个 Python 单元测试 + 8 个工作流场景，隔离性好，但测试不等同于真实采集/数据完整性/性能验收；CI 工作流未集成单元测试运行；触发方式为手动，非定时。

---

## 10. 尚未验证事项

| 序号 | 未验证事项 | 原因 |
|------|------------|------|
| U-1 | AKShare 真实接口采集是否成功（网络可达性、限流、接口变更） | 测试使用 Mock，未重新运行采集 |
| U-2 | 数据完整性全量校验结果（重复主键、字段缺失、异常数值） | V0 行数三方矛盾未解决，未运行全量质量检查 |
| U-3 | H11061 969 条数据的质量状态（`quality_status` 分布、OHLC/价格异常） | 仅确认行数，未做字段级质量校验 |
| U-4 | `output/minute_data_quality.jsonl` 不存在是否代表“未产生异常”还是“功能未运行” | 文件缺失，无法区分 |
| U-5 | cProfile 累计耗时与实际总耗时关系；README 加速比声明准确性 | 无性能报告文件，未执行压力测试 |
| U-6 | 工作流 `persist-credentials: true` + `contents: write` 是否符合最小权限与实际自动 push 需求 | 需结合运维需求评估 |
| U-7 | `subprocess.run(["git","show",...])` 无 timeout 在实际运行中的阻塞风险 | 代码层确认，未运行压力场景 |
| U-8 | CI 工作流是否应集成单元测试运行 | 工作流当前未执行测试 |
| U-9 | 本地 `main` 与远程 `origin/main` 的差异内容（47+ 提交差异） | 仅确认 SHA 不同，未 diff 内容 |

---

## 11. 修复优先级与实施路线图（仅提出计划，不执行）

### P0
1. AKShare HTTP 请求超时：为 `ak.futures_zh_*` / `ak.futures_index_ccidx` 调用增加超时控制，超时能按设定时间退出。
2. AKShare 异常类型与项目重试机制匹配：将 `Length mismatch`、`ValueError`、`RuntimeError` 等按类型归类，网络错误和限流错误按类型重试，非重试类异常直接抛出。
3. 单个采集任务失败必须能传递到整体任务结果：`__main__` 中任务失败时整体流程报告失败，不再仅写日志。

### P1
1. 分钟线、日线日期解析向量化：向量化改造前后输出结果一致。
2. JSONL 质量日志并发安全和增量写入：并发写入无记录丢失，重复记录不重复写入。
3. CSV 全量质量检查与提交前质量门槛：能识别重复主键、字段缺失、异常数值。
4. 测试脚本防止误删正式 output 数据：将 `rm -rf output` 限定在临时目录。

### P2
1. 日线全量下载、全量排序和写回优化评估。
2. 工作流缓存和任务并发策略；分支检查收紧。
3. README 任务数量、加速比等不准确声明修正。
4. 依赖版本锁定策略。

### P3
1. 备份目录 `.kilo/phase4_backup/` 管理。
2. 空占位文件 `H11061_minute_bars.csv` 策略。
3. 一次性合并脚本 `merge_v0_data.py` 旧行数断言（4229/2044）清理或参数化。
4. 其他低优先级维护事项（注释语言统一、数据保留策略等）。

---

## 12. 每项修复的验收标准

每项修复必须有可执行的验收条件，**不得只写“测试通过”**：

| 修复项 | 验收标准（可执行） |
|--------|-------------------|
| AKShare HTTP 超时 | 模拟超时场景，请求能在设定时间内退出并抛出超时异常；正常请求不受影响。 |
| 异常类型与重试匹配 | 网络错误/限流错误按类型重试（指数退避）；`ValueError`/`RuntimeError`/数据格式异常不重试并直接抛出。 |
| 单任务失败传递 | 单个采集任务失败时，整体流程能够报告失败（非零退出码或明确失败汇总），且不修改已有文件。 |
| 日期解析向量化 | 向量化改造前后对同一输入输出结果一致（行数、字段、排序一致）。 |
| JSONL 并发写入 | 多线程并发写入同一 JSONL 文件，无记录丢失、无重复记录、文件不损坏。 |
| CSV 全量质量检查 | 校验能识别重复主键（`symbol`+`trading_date` / `symbol`+`datetime`）、字段缺失、异常数值（负价格、OHLC 逻辑错误）。 |
| 测试防误删 | 测试脚本仅操作临时目录，正式 `output/` 文件不被 `rm` 删除。 |
| 工作流权限 | `persist-credentials` 与 `contents: write` 是否保留，基于自动 push 实际需求作出文档化决定。 |
| subprocess timeout | `git show` 等子进程增加 `timeout`，超时退出不阻塞主流程。 |
| 行数矛盾核实 | 以当前代码重新生成 V0 日线/分钟线，记录实际行数，说明与 4229/2044/2058/2396 的差异原因。 |

---

## 13. 暂不建议实施的变更

| 变更 | 不建议实施的理由 |
|------|------------------|
| 删除 `output/H11061_minute_bars.csv` 空占位并宣告“正式迁移完成” | 旧文件删除 ≠ 正式迁移完成；H11061 迁移需代码、数据、文档、工作流全部一致后方可宣告 |
| 将 `workflow_dispatch` 改为 `schedule` 定时触发 | 当前设计为 NAS 手动触发，变更触发方式属运营决策，需用户单独批准 |
| 把 19 个采集任务等同于每轮全部成功 | 任务提交数 ≠ 成功数，需按单任务结果汇总 |
| 将 `persist-credentials: true` + `contents: write` 直接关闭或直接保留 | 需先结合自动 push 实际需求评估，不宜在审计阶段单方面改动 |
| 将无 `timeout` 的 `subprocess` 直接定为安全漏洞并删除 | 无 timeout ≠ 漏洞，应补充 timeout 而非删除功能 |
| 因 `minute_data_quality.jsonl` 不存在就认定过滤功能从未运行 | 缺失日志 ≠ 功能未运行，需补充证据 |
| 按任一单一行数（4229/2044/2058/2396）认定数据完整 | 三方数据矛盾，必须并列待核实 |

---

## 14. 最终验收意见

### 14.1 是否建议进入修复阶段

**建议：是，进入修复阶段，但优先处理 P0 缺陷。** 代码层采集/验证/原子写入逻辑基本可用，单元测试隔离性好，H11061 已有 969 条真实数据；但存在 P0 级确定缺陷（版本不一致、单任务失败不传递、异常类型与重试不匹配、无请求超时、质量日志缺失）以及 V0 行数三方矛盾、文档不准确、工作流权限待评估等问题，不宜直接进入正式发布。

### 14.2 首批应修复的三个问题

1. **AKShare HTTP 请求超时与异常类型重试匹配（P0-3/P0-4）**：直接影响采集可靠性，无超时可能无限期阻塞，异常分类错误会导致应重试的错误被直接抛出或应抛出的错误被错误重试。
2. **单个采集任务失败传递到整体任务结果（P0-2）**：当前单流失败仅写日志，整体流程不会报告失败，会导致部分数据缺失却被误认为全部成功。
3. **本地 `main` 与远程 `origin/main` 版本不一致（P0-1）**：修复前必须明确以哪个版本为基准，避免在不一致基准上修改代码产生冲突。

### 14.3 哪些问题必须先补充证据

- U-2 数据完整性全量校验（V0 行数 4229/4230 vs 2044/2058/2396 三方矛盾）。
- U-3 H11061 969 条数据的字段级质量状态。
- U-4 `minute_data_quality.jsonl` 缺失原因（未产生异常 vs 功能未运行）。
- U-5 性能报告（cProfile）与 README 加速比声明的准确性。
- U-6 工作流 `persist-credentials` + `contents: write` 是否符合实际自动 push 需求。
- U-9 本地与远程差异内容（diff 两个 SHA）。

### 14.4 哪些改动需要用户单独批准

根据权限约束，以下改动**不得由实施方自行执行**，需用户单独批准：

1. 修改 `.github/workflows/collect.yml` 中的 `persist-credentials: true`、`contents: write` 权限或推送目标分支（涉及自动 push 与仓库写入权限）。
2. 将工作流触发方式从 `workflow_dispatch` 改为 `schedule` 定时触发（涉及运营方式变更）。
3. Git 变更操作（`git commit/push/pull/reset` 等），包括合并本地 `main` 与远程 `origin/main`。
4. 删除或覆盖备份目录 `.kilo/phase4_backup/` 及本地备份分支 `backup/local-before-merge`、`backup/remote-before-merge`。
5. 修改 `requirements.txt` 依赖版本锁定策略。
6. 删除 `output/H11061_minute_bars.csv` 空占位或宣告 H11061 正式迁移完成。

---

**本报告仅汇编现有证据，不实施修复。各修复项的实施、验收及 Git 操作需在用户授权后由实施方按第 11-12 章执行。**

报告完成，等待用户审阅。
