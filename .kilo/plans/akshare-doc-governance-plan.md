# akshare-futures-data 文档治理实施计划

Status: historical
Version: 1.0
Last updated: 2026-11-05

Baseline note: this plan was authored before `docs/` existed and before
`README.md` reached 191 lines. Statements such as "docs/ missing" and
"README.md (180 行)" are historical baselines, not current facts. The plan is
retained as planning history; its recommendations and acceptance criteria are
not rewritten.

## 1. 目标与边界

### 1.1 目标
- 建立完整、准确、可追溯的项目文档体系。
- README 与当前代码/配置/数据一致。
- 历史审计报告（V1/V2/V2.1/V2.2/V2.3/V2.3.1/V2.3.2）保留并明确标识状态。
- 消除重复、过期、矛盾说明。
- 形成文档入口、维护规则与验收清单。

### 1.2 边界（严格）
- 允许：读取源码/配置/数据做事实核验；修改 Markdown 文档；调整文档目录与链接；归档纯文档临时文件（有依据）。
- 禁止：修改 Python/Shell/YAML/CSV/JSONL/README 运行行为；执行采集/测试/Actions；Git 写操作；伪造测试结果。

### 1.3 不适用项（本仓库不存在）
任务模板中提及的 `STATE_ISOLATION_FINAL_DESIGN.md`、`U1_U3_EVIDENCE_AUDIT.md`、`AUDIT_SCOPE.md`、`BASELINE.md`、`HANDOFF.md`、`_worker.js`、`_worker明.js`、`isValidIP`、`proxyPort`、IPv6、U5–U7、U2/U3 等均**不存在于本仓库**。本仓库为 Python 数据采集项目，无上述 Web/代理组件。这些条目不适用，不得在文档中编造。

## 2. 全项目文档盘点（实际文件）

### 2.1 根目录
| 路径 | 类型 | 状态 | 说明 |
|------|------|------|------|
| `README.md` (180 行) | 主文档 | 需修订 | 项目入口；含任务数/加速比/push retry 等未验证声明 |
| `investigation_report.md` | 调查报告 | 有效（历史） | Git/工作流审计；确认仅 workflow_dispatch |
| `requirements.txt` | 依赖 | 有效 | 版本范围宽松 |
| `test1.py` | 探针脚本 | 临时/非正式 | AKShare 签名探查，非测试套件 |
| `.gitignore` | 配置 | 有效 | 不在本轮自动修改范围 |

### 2.2 .github/workflows
| 路径 | 状态 | 说明 |
|------|------|------|
| `collect.yml` | 有效（需核验） | workflow_dispatch；persist-credentials: true；contents: write；分支检查仅 ref type |
| `collect.yml.bak` | 历史备份 | 旧版 workflow（含 H11061 循环收集），应归档/删除（需批准） |

### 2.3 .kilo/plans（审计/计划记录）
| 路径 | 状态 | 说明 |
|------|------|------|
| `1793796003000-final-audit-report-v2.3.2.md` | **当前审计入口** | 最新，18 项问题 |
| `...-v2.3.1.md` | 历史 | 交叉引用修正版 |
| `...-v2.3.md` | 历史 | |
| `...-v2.2.md` | 历史 | |
| `...-v2.1.md` | 历史 | |
| `...-v2.md` | 历史 | |
| `...-final-audit-report.md` | 历史骨架 | 未填充正文 |
| `1793711576733-h11061-index-daily-plan.md` | 历史计划 | 含过时 Git 基准（9b94b5e/2fa46b7） |
| `1793780657325-h11061-index-daily-revised-plan.md` | 历史计划 | |
| `pvc-final-review.md` | 历史审查 | 25/25 测试（旧计数）；V0 4230/2058（分钟线与实测 2396 矛盾） |
| `pvc-contract-data-review.md` | 历史审查 | AKShare 1.20.0；具体合约可获取性 |
| `pvc-phase1-implementation-plan.md` | 历史计划 | |
| `planner-coder-collaboration-test.md` / `planner-tool-test.md` | 测试产物 | 可归档 |
| `write-test*.md` (a,b,c) | 测试产物 | 可归档/删除（需批准） |

### 2.4 其他
| 路径 | 状态 | 说明 |
|------|------|------|
| `backup/` (collect.yml, fetch_pvc.py, README.md) | 历史备份 | 旧版文件副本 |
| `.kilo/phase4_backup/` | 历史备份 | V0 pre_merge + V2701/2705/2709 数据 |
| `plan/pvc-contract-data-review.md` | 重复 | 与 .kilo/plans 同名文件重复 |
| `.vscode/settings.json` | 配置 | 非文档 |
| `tests/` (5 py + 1 sh + conftest) | 测试 | 已盘点 |
| `output/` (20 CSV) | 数据 | 非文档，但 README 描述需核验 |

### 2.5 缺失的文档（建议新增）
- `docs/` 目录不存在；建议创建最小文档集：
  - `docs/README.md` 或保留根 README 为唯一入口
  - `docs/architecture.md`（架构与数据流）
  - `docs/data.md`（数据源、字段、交易日规则）
  - `docs/operations.md`（本地运行、Actions、故障排查）
  - `docs/testing.md`（测试与验收、证据边界）
  - `docs/audit-history.md`（审计报告索引与状态）

## 3. 重点文件核验任务

### 3.1 README.md（必须修订）
已知问题（来自审计报告）：
- "19 个采集任务" vs 代码 19 task（巧合一致，但"每轮全部成功"未验证）
- "6-7x/3-4x 加速比" 无基准证据 → 标记未验证
- "push failure retries up to 3 times" vs workflow 单次 push → 已确认不一致
- 任务数描述 18/9 vs 代码 19 → 已确认不一致
- H11061 旧/新文件并存未说明
- H11061 已有 969 条数据记录，字段级质量未验证
- 测试说明：50 Python + 8 Shell 场景

### 3.2 .kilo/plans 审计报告
- V2.3.2 为当前审计入口；其余标为"历史"。
- 历史报告保留，不删除（追溯价值）。
- 过时 Git 基准（47 提交、9b94b5e/2fa46b7）需在报告中明确过时，不作为当前事实。

### 3.3 .github/workflows/collect.yml
- 触发方式：workflow_dispatch（手动），非定时。
- 分支检查：仅 ref type，不再限定 release/pvc-nine-contracts。
- persist-credentials: true + contents: write 配合自动 push。
- README 描述需与之一致。

### 3.4 .gitignore
- 本轮不自动修改；如需调整单独列出待批准。

## 4. 一致性核对矩阵

| 主题 | 文档来源 | 代码/配置来源 | 核验点 |
|------|----------|---------------|--------|
| 采集任务数 | README (18/9, 19) | fetch_pvc.py ACTIVE_CONTRACTS (10 合约, 19 task) | 以代码为准 |
| 触发方式 | README, investigation_report | collect.yml (workflow_dispatch) | 手动，非定时 |
| 分支范围 | README, investigation_report | collect.yml (ref type only) | 已放宽 |
| push 重试 | README (3 次) | collect.yml (单次 push) | 不一致，修正 README |
| 加速比 | README (6-7x/3-4x) | 无基准 | 标记未验证 |
| H11061 数据 | README, pvc-final-review | output/H11061_index_daily.csv (969 行) | 已有数据，字段质量未验证 |
| 测试数量 | README (25/25) | grep def test_ (50) + 8 Shell | 以代码为准 |
| V0 行数 | pvc-final-review (4230/2058) | wc -l (4230/2396) | 分钟线矛盾待解释 |
| AKShare 版本 | pvc-contract-data-review (1.20.0) | requirements.txt (>=1.20,<2.0) | 一致 |

## 5. 清理与结构统一方案

### 5.1 建议目录结构（最小改动）
```
akshare-futures-data/
├── README.md                    # 入口（修订）
├── docs/
│   ├── architecture.md          # 新增：架构与数据流
│   ├── data.md                  # 新增：数据源、字段、交易日规则
│   ├── operations.md            # 新增：本地运行、Actions、故障排查
│   ├── testing.md               # 新增：测试与验收、证据边界
│   └── audit-history.md         # 新增：审计报告索引与状态
├── .kilo/plans/                 # 保留，新增 INDEX.md 索引
├── tests/
├── output/
├── backup/                      # 历史备份，保留
└── .kilo/phase4_backup/         # 历史备份，保留
```

### 5.2 清理动作（需批准）
- `collect.yml.bak`：归档或删除（建议归档到 backup/）
- `test1.py`：归档或删除（探针脚本，非正式测试）
- `write-test*.md`：删除（测试产物）
- `planner-*-test.md`：删除（测试产物）
- `plan/pvc-contract-data-review.md`：与 .kilo/plans 同名重复，合并或删除
- `backup/` 旧文件：保留（追溯价值）

### 5.3 文档入口规则
- README.md 为唯一对外入口。
- docs/ 为详细说明。
- .kilo/plans/ 为审计/计划历史，不作为用户入口。
- 每份文档头部注明：状态（有效/历史/废弃）、对应版本、最后更新。

## 6. 风险与保护措施
- 风险：误删有追溯价值的历史报告 → 保护：仅归档，不删除审计报告。
- 风险：README 改动破坏现有引用 → 保护：保留章节锚点，逐步迁移。
- 风险：文档与代码不一致 → 保护：每项声明标注证据状态（已确认/未验证）。
- 风险：.gitignore 修改影响构建 → 保护：单独列出，等待批准。

## 7. 执行阶段（Code 按此执行）

### 阶段 1：盘点与基线（只读）
- [x] 全文件扫描完成（本计划）
- [ ] 读取 README、investigation_report、各 plan 文件全文
- [ ] 记录每份文档状态到清单

### 阶段 2：事实核验（只读）
- [ ] 核验 README 每条声明 vs 代码/配置/数据
- [ ] 核验 V2.3.2 审计结论与 README/BASELINE/HANDOFF 无冲突
- [ ] 标记未验证项

### 阶段 3：README 修订
- [ ] 修正任务数、push retry、加速比表述
- [ ] 补充 H11061 说明
- [ ] 更新测试数量
- [ ] 修正工作流触发描述

### 阶段 4：新增 docs/ 结构
- [ ] 创建 docs/ 目录
- [ ] 编写 architecture.md, data.md, operations.md, testing.md, audit-history.md

### 阶段 5：清理与归档
- [ ] 归档 collect.yml.bak, test1.py
- [ ] 删除 write-test*.md, planner-*-test.md（需批准）
- [ ] 合并重复 plan/pvc-contract-data-review.md
- [ ] 创建 .kilo/plans/INDEX.md

### 阶段 6：Review 验收
- [ ] 独立 Review 检查遗漏、矛盾、链接有效性
- [ ] 修正 Review 发现的问题

### 阶段 7：最终交付
- [ ] 生成文档总清单
- [ ] 生成变更报告
- [ ] 生成一致性验收报告
- [ ] 生成最终状态摘要

## 8. 验收标准
- README 与当前项目功能一致
- 数据/接口/字段/交易日/存储说明有依据
- 工作流说明与当前配置一致
- 历史审计结论和证据边界未被破坏
- 过期/重复/矛盾文档已妥善处理
- 文档链接和章节引用有效
- Review 独立通过
- 所有未解决事项已明确列出

## 9. 需用户批准的事项
1. 删除 `write-test*.md`、`planner-*-test.md` 测试产物
2. 归档/删除 `collect.yml.bak`、`test1.py`
3. 合并/删除 `plan/pvc-contract-data-review.md`
4. 修改 `.gitignore`
5. 创建 `docs/` 目录与新文件

## 10. 本计划不实施的内容
- 不修改任何源码、配置、数据
- 不执行采集、测试、Actions
- 不执行 Git 写操作
- 代码问题仅记录，不修复

---
本计划为文档治理实施计划，待用户批准后由 Code 按阶段执行。