# V0 invalid_ohlc 下游数据链路治理执行计划

基于只读核验报告（2026‑11‑04）制定。本计划仅限文档与治理约定，不修改源码、数据或 Workflow。

## 1. 背景与事实

- `output/V0_daily_bars.csv` 第 395 行（2011‑01‑03）与第 2720 行（2020‑08‑06）已标记 `quality_status=invalid_ohlc`，OHLC 值未动。
- 仓库内不存在指标计算、API 输出或数据库链路；唯一消费者读取层为 `csv_to_records()` 与 `merge_v0_data.py`，均原样透传 `invalid_ohlc`，无排除逻辑。
- README.md 第 180 行、docs/data.md 第 109‑118 行仍写 “still carry quality_status = valid”，与工作区实际状态不符。

## 2. 执行范围（仅文档/治理约定）

1. 更新 README.md 与 docs/data.md 中关于 V0 OHLC 异常状态的描述，改为 “已标记 invalid_ohlc”。
2. 在 docs/data.md 追加消费契约：下游读取 CSV 时应先过滤 `quality_status == "valid"`，滚动窗口不得跨越 `invalid_ohlc` 记录。
3. 在 docs/architecture.md 或 docs/data.md 记录 `merge_v0_data.py` 的 `quality_status` 盲点，建议未来若继续使用该脚本，应在 `validate_records()` 中增加状态检查。
4. 在 .kilo/plans/INDEX.md 或 docs/audit-history.md 补充“未来新增指标/API 模块时，必须在消费入口增加 invalid_ohlc 排除过滤与对应测试”的约定。
5. 不修改 `fetch_pvc.py`、`merge_v0_data.py`、CSV、Workflow、测试。

## 3. 任务清单

| 编号 | 文件 | 修改位置 | 目的 | 验收标准 |
|------|------|----------|------|----------|
| T1 | README.md | Known Limitations 表第 180 行 | 状态描述与实际一致 | grep “still carry quality_status = valid” 无匹配 |
| T2 | docs/data.md | Known data-quality issue 第 109‑118 行 | 状态描述与实际一致 | 同上 |
| T3 | docs/data.md | §Daily bars fields / Known data-quality issue | 追加消费契约 | 文档明确“过滤 quality_status=valid” |
| T4 | docs/architecture.md | Output layout 或 Related docs | 记录 merge 脚本盲点 | 文档明确“merge_v0_data.py 不检查 quality_status” |
| T5 | .kilo/plans/INDEX.md 或 docs/audit-history.md | 末尾追加约定 | 未来模块准入约定 | 文档明确“新增指标/API 必须排除 invalid_ohlc 并加测试” |

## 4. 验证步骤

1. `grep -rn "still carry \`quality_status = valid\`" README.md docs/` → 无匹配。
2. `grep -rn "invalid_ohlc" README.md docs/` → 至少 3 处（T1/T2/T3）。
3. `git diff --stat` 仅显示 Markdown 文件改动，无源码/配置/数据改动。

## 5. 不在范围

- 不修改源码、CSV、Workflow、测试。
- 不新增指标/API/排除逻辑实现。
- 不执行 Git 写操作。

## 6. 风险与注意事项

- T1/T2 仅更新文字，不涉及数据。
- T3/T4/T5 为约定性文档，无运行时影响。
- 若未来新增消费端，必须同步实现排除逻辑与测试，本计划不覆盖实现。