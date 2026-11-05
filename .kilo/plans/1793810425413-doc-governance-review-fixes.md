# akshare-futures-data 文档治理修复计划（Dot3 + Alpha Review）

Plan file: `.kilo/plans/1793810425413-doc-governance-review-fixes.md`

## 0. 修复前核验结果（R1–R8 是否仍成立）

| 项 | 结论 | 证据 |
|----|------|------|
| R1 V1 报告状态 | **成立（需修）** | `1793796003000-final-audit-report.md` = 406 行完整报告；`1793794755058-final-audit-report.md` = 70 行，仅"编写计划/证据清单"，未填充正文。当前 `docs/audit-history.md` 和 `.kilo/plans/INDEX.md` 把 406 行那份标为 "Skeleton; body not populated"，把 70 行那份标为 "Earlier draft"——**标反了**。 |
| R2 Workflow push 策略 | **成立（需修）** | `.github/workflows/collect.yml` 第 86 行仅 `git push origin "HEAD:refs/heads/${GITHUB_REF_NAME}"`，无 `git fetch`/`git rebase`，无 retry loop。`README.md` L163、L169 和 `docs/operations.md` L39 仍声称 "git fetch + rebase origin/main"。 |
| R3 H11061 volume/hold | **成立（需修）** | CSV 表头：`symbol,name,index_code,trading_date,close,settle,change,pct_change,quality_status,source,collected_at` — 无 volume/hold。`fetch_pvc.py` `update_index_daily_bars()` 记录构造（L347–L359）不含 volume/hold。但 `README.md` L125 和 `docs/data.md` L61 仍称 "`volume`、`hold` 固定为 0 (占位)"；`README.md` L79 数据表也称 "Volume and open interest are 0"。 |
| R4 V0 OHLC 异常状态 | **成立（需修）** | `output/V0_daily_bars.csv` 第 395 行（2011-01-03）和第 2720 行（2020-08-06）均 `quality_status=valid`。源码 `known_bad_dates` 识别逻辑不代表历史 CSV 已重处理。文档需明确"记录仍存在且仍为 valid，尚未修复/重核实"。 |
| R5 治理计划 README 行数 | **成立（需注释）** | 计划 §2.1 写 `README.md (180 行)`；当前 README = 192 行。应仅在 INDEX.md 说明这是计划编制时的历史基线，不改写历史计划。 |
| R6 INDEX 遗漏 test1.py | **部分成立（需注释）** | `test1.py` 存在（14 行 AKShare 签名探针，非测试套件）。INDEX.md 范围仅 `.kilo/plans/`，`test1.py` 为根目录文件，不在其索引范围。应在 INDEX.md 增加"根目录非文档文件"简短说明，或明确声明范围。 |
| R7 merge_v0_data.py 行数 | **成立（需修）** | 实际 501 行；`docs/architecture.md` L18 写 502 行。 |
| R8 版本标签说明 | **成立（需简化）** | 文件名 V2.3.2 与内部 H1 V2.3.1 的差异披露目前措辞冗长，易误解为两份不同报告。需简化 INDEX.md 和 audit-history.md 措辞，保留披露。 |

所有 8 项均仍成立。无一项已自动修复。

## 1. 范围与边界

- **只允许修改 Markdown 文件**（README.md、docs/*.md、.kilo/plans/INDEX.md、.kilo/plans/akshare-doc-governance-plan.md 可追加注释）。
- **禁止**：修改源码、YAML、CSV、Workflow、Git 操作、运行测试/采集。
- **历史报告**（`.kilo/plans/1793796003000-final-audit-report*.md`）**原样保留**，不改 H1。

## 2. 任务列表（按 R 编号）

### T1 — R1：纠正 V1 历史审计报告状态

**文件**：`docs/audit-history.md`、`.kilo/plans/INDEX.md`

**audit-history.md**：
- L26：`| 1793796003000-final-audit-report.md | V1 | historical | — | Skeleton; body not populated. |`
  → `| 1793796003000-final-audit-report.md | V1 | historical | — | Complete report (406 lines); V1 entry point of the audit series. |`
- L27：`| 1793794755058-final-audit-report.md | — | historical | — | Earlier draft, "编写计划" section. |`
  → `| 1793794755058-final-audit-report.md | — | historical | — | Skeleton/draft (70 lines): only "编写计划" + evidence list + contradiction notes; body not populated. |`

**INDEX.md**：
- L21：`| 1793796003000-final-audit-report.md | V1 | historical (skeleton) |`
  → `| 1793796003000-final-audit-report.md | V1 | historical (complete report) |`
- L22：`| 1793794755058-final-audit-report.md | — | historical (draft) |`
  → `| 1793794755058-final-audit-report.md | — | historical (skeleton/draft) |`

### T2 — R2：纠正 Workflow push 策略描述

**文件**：`README.md`、`docs/operations.md`

**README.md**：
- L163：`- Push strategy: git fetch + rebase origin/main is run before push; push is a single git push with no retry loop. (The "retries up to 3 times" claim previously appearing here is not supported by the current workflow.)`
  → `- Push: a single git push origin "HEAD:refs/heads/${GITHUB_REF_NAME}" after commit. The workflow does not run git fetch or git rebase, and has no push retry loop.`
- L169：`- Workflow git push executes git fetch + rebase before push; the workflow performs a single push with no retry loop, and avoids push rejection caused by concurrent submissions via concurrency.group: pvc-collect-nine, cancel-in-progress: false.`
  → `- Workflow git push is a single push after commit; no git fetch/rebase and no retry loop. Concurrent-run protection is via concurrency.group: pvc-collect-nine, cancel-in-progress: false.`

**docs/operations.md**：
- L39–L41：`- Push: git fetch + rebase origin/main, then a single git push origin "HEAD:refs/heads/${GITHUB_REF_NAME}". There is no retry loop in the workflow.`
  → `- Push: a single git push origin "HEAD:refs/heads/${GITHUB_REF_NAME}" after commit. The workflow does not run git fetch or git rebase, and has no push retry loop.`

### T3 — R3：纠正 H11061 volume/hold 字段描述

**文件**：`README.md`、`docs/data.md`

**README.md**：
- L79：`| output/H11061_index_daily.csv | ... Volume and open interest are 0 (index has no volume/open interest data) |`
  → `| output/H11061_index_daily.csv | ... No volume or open interest fields (index has no volume/open interest data) |`
- L124：保留 `无 OHLC、volume、hold 字段 (指数无成交量/持仓)`（正确）。
- L125：`- volume、hold 固定为 0 (占位)` → 删除该行。

**docs/data.md**：
- L60–L61：`- No OHLC / volume / hold fields (an index has no volume or open interest).` + `- volume and hold are fixed at 0 as placeholders.`
  → 保留第一行，删除第二行。

### T4 — R4：明确 V0 OHLC 异常数据处理状态

**文件**：`README.md`（Known Limitations 行）、`docs/data.md`（Known data-quality issue）

**README.md** L177 行（Known Limitations 表）：
- 现有：`| V0 daily OHLC anomalies | Two records ... currently carry quality_status = valid despite the OHLC logic violation | May affect downstream data quality | Verify whether they should be marked invalid_ohlc or removed; see audit report V2.3.2 §4.5 (P1-4) |`
  → 追加说明：`Both records still exist in the historical CSV (output/V0_daily_bars.csv) with quality_status = valid. The source-code known_bad_dates recognition does not imply the historical CSV has been reprocessed. Historical data repair / re-verification is NOT done; status remains open (P1-4).`

**docs/data.md** L108–L118（Known data-quality issue）：
- 在表格后追加：
  ```
  Both records still exist in the historical CSV `output/V0_daily_bars.csv` and
  still carry `quality_status = valid`. The `known_bad_dates` recognition in
  source code does not imply the historical CSV has been reprocessed. Historical
  data repair and re-verification remain open (audit issue P1-4, V2.3.2 §4.5).
  No data file is modified by this governance pass.
  ```

### T5 — R5：治理计划历史基线说明

**文件**：`.kilo/plans/INDEX.md`

- 在 "Plans" 表或文档末尾追加 note：
  ```
  ## Historical baseline note
  .kilo/plans/akshare-doc-governance-plan.md §2.1 records README.md as "180 行".
  That figure is the baseline at plan authoring time (2026-11-05); the current
  README.md is 192 lines. The plan is retained as historical record; its
  line-count baseline is not updated retroactively.
  ```

### T6 — R6：INDEX 补充 test1.py 说明

**文件**：`.kilo/plans/INDEX.md`

- 追加小节（根目录非文档文件，不在 `.kilo/plans/` 范围内）：
  ```
  ## Root-level non-document files (outside this index's scope)
  - `test1.py` — AKShare signature probe (14 lines); not part of the test suite.
    Listed as a cleanup candidate in akshare-doc-governance-plan.md §2.1/§5.2.
  ```

### T7 — R7：修正 merge_v0_data.py 行数

**文件**：`docs/architecture.md`

- L18：`| V0 merge tool | merge_v0_data.py (502 lines) | ... |`
  → `| V0 merge tool | merge_v0_data.py | ... |`（删除易过时的行数）。

### T8 — R8：简化 V2.3.2 版本标签说明

**文件**：`.kilo/plans/INDEX.md`、`docs/audit-history.md`

**INDEX.md** L15：`| 1793796003000-final-audit-report-v2.3.2.md | V2.3.1 (internal) | **current entry** |`
  → `| 1793796003000-final-audit-report-v2.3.2.md | V2.3.2 (file) / V2.3.1 (internal H1) | **current entry** |`

并简化 L15 行内 note（当前无 note 列）——在文件末尾或该行后加一行说明：
  ```
  Note: the file name uses V2.3.2 while its internal H1 heading reads V2.3.1.
  This is a preserved revision-scope artifact, not two separate reports.
  ```

**audit-history.md** L20：Notes 列当前写 "File name says V2.3.2; the H1 heading inside the file is labeled V2.3.1 by design of the prior revision scope. Not "fixed" — preserved as-is."
  → 简化为："File name V2.3.2, internal H1 V2.3.1 (preserved revision-scope artifact; one report, not two)."

## 3. 验证步骤（实施后）

1. `grep -n "git fetch + rebase\|git fetch or git rebase" README.md docs/operations.md` → 应无残留错误描述（仅否定性描述）。
2. `grep -n "固定为 0\|fixed at 0\|Volume and open interest are 0" README.md docs/data.md` → 应无匹配。
3. `grep -n "Skeleton; body not populated" docs/audit-history.md .kilo/plans/INDEX.md` → 应无匹配。
4. `grep -n "502 lines" docs/architecture.md` → 应无匹配。
5. 确认历史报告 H1 未改动：`head -1 .kilo/plans/1793796003000-final-audit-report-v2.3.2.md` 仍为 "V2.3.1"。
6. `git diff --stat` 仅显示 Markdown 文件改动；无源码/配置/数据改动。

## 4. 不在本次范围

- 不修改 `.github/workflows/collect.yml`。
- 不修改 `fetch_pvc.py`、`merge_v0_data.py`、CSV。
- 不删除历史审计报告、备份、重复文件。
- 不运行测试或采集。
- 不执行 Git 写操作。

## 5. 风险与注意事项

- R4 仅澄清状态，不修复数据；历史 CSV 仍保留 anomaly 行。
- R5/R6 仅追加注释，不改写历史计划正文。
- R8 仅简化措辞，保留披露。