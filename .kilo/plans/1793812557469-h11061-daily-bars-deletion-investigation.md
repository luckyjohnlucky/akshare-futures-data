# H11061 日线历史数据文件删除状态调查报告

调查范围：`output/H11061_daily_bars.csv`（只读，未恢复/修改任何文件）。

## 1. 文件当前状态及可核实的历史信息

- 工作区状态：`deleted`（`git status` 显示 ` D output/H11061_daily_bars.csv`），删除未提交。
- Git 跟踪状态：被跟踪（`git ls-files` 含该路径）；本地 `HEAD`（`fb97907`）与 `origin/main`（`e793566`）的 tree 中均存在该文件。
- 历史版本：仅一次提交触及该文件 — `382430f feat: 添加中证商品期货指数 H11061 日线采集支持`（新增，969 条记录）。`git log --all --diff-filter=D` 无结果，没有任何提交删除过它。
- 后续提交：`fb97907 feat: add H11061 index daily line independent structure (B1-B3)` 新增 `output/H11061_index_daily.csv`，未修改旧文件。
- 文件规模：159,288 字节，970 行（1 表头 + 969 数据）；日期范围 2022-11-03 至 2026-11-03；source=`AKShare futures_zh_daily_sina`；schema 为通用日线（open/high/low/close/volume/open_interest/settle_raw/settle/...）。
- stash `stash@{0}` 不包含该文件。
- `.gitignore` 未忽略 `output/*.csv`，故 tracked 状态有效。

## 2. 被哪些模块或流程引用

- `fetch_pvc.py`：无对 `H11061_daily_bars.csv` 的实际读写。H11061 走独立指数分支，写入 `output/H11061_index_daily.csv`。`ACTIVE_CONTRACTS` 含 H11061，但 `_run_daily_bars` 调用 `fetch_and_update_daily_bars`，其中 H11061 分支使用 `update_index_daily_bars`。仅日志里 `get_daily_csv(symbol)` 仍拼出旧路径（显示性不一致，非数据依赖）。
- `.github/workflows/collect.yml`：条件性加入该文件（若存在）；不生成它。
- `tests/test_workflow_collect.sh`：测试条件收集逻辑，使用 touch 模拟，不依赖真实文件。
- 文档：`README.md`（注记 tracked 但本地删除，替代为新文件）、`docs/operations.md`（troubleshooting）、`docs/architecture.md`/`docs/data.md`（仅新文件）。
- 计划/审计：`.kilo/plans/1793780657325-...` 标注“旧格式，已按计划删除，保持 D 状态”；多份审计报告记录“tracked 但本地已删、未提交”及 P3-2 迁移/清理建议。
- `backup/`、`.kilo/phase4_backup/`：仅备份副本，非活跃流程。
- `merge_v0_data.py`：无引用。

结论：无运行时/数据合并依赖；仅 workflow 条件引用与测试场景引用。

## 3. 删除对项目的实际影响

- 采集功能：不受影响；H11061 日线仍通过指数路径采集并写入新文件。
- 数据合并：无脚本引用旧文件；不受影响。
- 下游分析：仓库内无源码/测试依赖旧文件；风险主要来自远端仍保留该文件，CI checkout 会物化它，workflow 可能提交未变更副本，导致远端保留过时旧 schema 数据。
- 历史数据：旧数据仍可从 Git 历史（`382430f`、`origin/main`）恢复；新文件为设计上的替代，但 schema 与日期范围并不完全一致（旧：2022-11-03..2026-11-03；新：2022-11-04..2026-11-04），不能视为字节等价替换。
- 工作区：减少约 159KB 旧 schema 文件，移除本地对过时格式的可见性。

## 4. 删除是否符合当前项目设计

- 符合本地/文档层面的设计：README、docs/operations 与修订计划均将旧文件视为过时、删除视为预期的本地状态，当前采集实现只产出新指数文件。因此本地删除与文档化迁移方向一致。
- 不符合“仓库级移除”层面：删除未提交，`origin/main` 仍含该文件，workflow 仍条件引用它。当前状态是“工作树删除”，而非“从仓库移除”。设计处于过渡态，存在不一致。

## 5. 仍然无法确认的事项及证据缺口

- 没有提交或 PR 明确授权删除，依据仅来自计划/审计文档。
- 无法从仓库验证用户是否批准了该删除。
- 无法验证仓库外是否存在依赖该文件的外部消费者。
- 旧/新文件的数据语义等价性（除行数）未核验。
- P3-2（迁移与清理策略）仍为开放改进建议，长期策略未定。

## 6. 明确建议

建议：**保留删除状态（不恢复）**。

理由：与已文档化的迁移方向和当前采集实现一致，且无运行时/合并依赖。但该删除仅是工作树状态，远端仍保留文件；若目标是彻底从仓库移除旧文件，应另开经授权的任务，包含：从 Git 跟踪移除、更新 workflow/tests/docs 中的旧文件引用、并决定数据保留/迁移策略。当前不建议提交/推送任何移除操作。

## 结论

`output/H11061_daily_bars.csv` 的本地删除与当前项目文档化迁移方向一致，不影响 H11061 采集与数据合并；但删除未提交，远端仍保留过时副本，仓库级清理仍属未决事项。本调查到此结束，等待用户审阅。
