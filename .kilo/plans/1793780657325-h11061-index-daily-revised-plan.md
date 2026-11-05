# H11061 指数日线功能发布后验证与收尾计划

## 项目背景

**项目路径**: `/Users/johnm/Projects/akshare-futures-data`
**当前分支**: `main`
**最新提交**: `fb97907fcb2678450abdd33d85ac32c3f19e2264` (feat: add H11061 index daily line independent structure (B1-B3))
**远程 HEAD**: `fb97907fcb2678450abdd33d85ac32c3f19e2264` ✅ 已同步

## 当前状态确认（基于审计结果）

### ✅ 已完成事项
- **提交与推送**: fb97907 已推送至 origin/main
- **H11061 代码实现**: B1-B3 完整实现 (normalize/validate/update_index_daily_bars + fetch_and_update_daily_bars 分支)
- **README.md 文档**: H11061 相关文档已补充
- **Workflow 修复**: collect.yml 修复 H11061 重复收集，显式收集 3 个文件
- **测试文件**: test_index_daily.py (14 测试)、test_workflow_collect.sh (16 场景) 已添加
- **数据文件**: output/H11061_index_daily.csv (970 行 = 969 数据 + 1 表头) 已生成并提交
- **Git 同步**: 本地与远程 HEAD 均为 fb97907

### 📋 当前工作区状态
```
D  output/H11061_daily_bars.csv        # 旧格式指数日线，已按计划删除
?? .github/workflows/collect.yml.bak   # 备份文件
?? .kilo/plans/...                     # 计划文件
?? backup/                             # 备份目录
?? output/H11061_minute_bars.csv       # 空文件 (0 字节)，占位用
```

### 📊 测试状态
- **总计**: 66 个测试 (原有 36 + 新增 14 + 16)
- **注**: 因网络/依赖环境限制，未能在审计期间运行完整测试套件
- **需验证**: 完整测试套件运行结果

---

## 剩余验证与收尾计划

### 任务 1：测试验证（优先级：高）
**目标**: 确认所有 66 个测试通过

- [ ] 运行 `python -m pytest tests/test_index_daily.py -v` (14 个测试)
- [ ] 运行 `bash tests/test_workflow_collect.sh` (16 个场景)
- [ ] 运行完整测试套件：`python -m unittest discover -s tests -v` (预期 66 个测试全部通过)

**前置条件**: 需在有依赖的环境中运行（如 .venv）

---

### 任务 2：GitHub Actions 验证（优先级：高）
**目标**: 确认远程工作流正确触发并运行

- [ ] 手动触发 GitHub Actions: `.github/workflows/collect.yml` (workflow_dispatch)
- [ ] 确认工作流成功运行，收集 18 个商品期货文件 + 3 个 H11061 文件
- [ ] 确认无推送冲突、无失败重试超限

---

### 任务 3：数据质量复核（优先级：中）
**目标**: 确认 H11061 数据文件完整性

- [ ] 确认 `output/H11061_index_daily.csv` 远程存在且 970 行 (969 数据 + 1 表头)
- [ ] 抽样检查字段完整性：`symbol, name, index_code, trading_date, close, settle, change, pct_change, quality_status, source, collected_at`
- [ ] 确认 `index_code` 全为 `100001.CCI`，`quality_status` 全为 `valid`
- [ ] 确认无 OHLC/volume/hold 字段混入

---

### 任务 4：工作区清理（优先级：中）
**目标**: 清理临时文件，保持仓库整洁

**需清理（未跟踪文件）**：
- [ ] `.github/workflows/collect.yml.bak`
- [ ] `.kilo/plans/1793711576733-h11061-index-daily-plan.md`
- [ ] `.kilo/plans/1793780657325-h11061-index-daily-revised-plan.md`
- [ ] `backup/`
- [ ] `output/H11061_minute_bars.csv` (空文件，占位用，不应提交)

**需保留（已删除但历史记录保留）**：
- `output/H11061_daily_bars.csv` (旧格式，已按计划删除，保持 D 状态)

---

### 任务 5：Stash 处理（优先级：低）
**目标**: 验证通过后安全删除备份

- [ ] 确认所有验证通过（测试、Actions、数据质量）
- [ ] 执行 `git stash drop stash@{0}` 删除备份
- [ ] 确认 `git stash list` 为空

---

### 任务 6：技术债务跟进（优先级：低，后续迭代）
**已识别债务项**（不阻塞当前发布）：

| 编号 | 项目 | 优先级 | 备注 |
|------|------|--------|------|
| TD-001 | confirmed_errors 外部化配置 | P1 | 硬编码 8 条记录 |
| TD-002 | known_bad_dates 外部化配置 | P1 | 硬编码 2 个日期 |
| TD-004 | 数据保留策略 | P1 | 无保留期限，CSV 无限增长 |
| TD-006 | 节假日交易日历集成 | P2 | 无交易日历 |
| TD-005 | 分钟数据历史归档 | P2 | 仅滚动窗口 ~1023 条 |
| TD-003 | 注释语言统一 | P3 | 中英混杂 |
| TD-007 | H11061 旧文件历史清理 | P3 | 可选 |

---

## 验收标准

| 标准 | 状态 | 备注 |
|------|------|------|
| 所有 66 个测试通过 | 待验证 | 需在有依赖环境运行 |
| GitHub Actions 成功运行 | 待触发 | 手动触发 workflow_dispatch |
| H11061 数据文件完整 | ✅ 本地确认 | 远程需再次确认 |
| Git 历史整洁 | ✅ | fb97907 单提交，无冲突 |
| 提交仅含 H11061 相关文件 | ✅ | 6 个白名单文件 |
| 无意外商品期货数据混入 | ✅ | 已核对暂存区 |
| Stash 已安全删除 | 待执行 | 验证通过后删除 |

---

## 风险提示

| 风险 | 影响 | 缓解 |
|------|------|------|
| 测试环境依赖缺失 | 无法验证测试 | 在 .venv 或 CI 中运行 |
| Actions 触发失败 | 需排查权限/配置 | 检查 GITHUB_TOKEN 权限 |
| 远程数据文件异常 | 需回滚 | git revert fb97907 |

---

## 执行顺序建议

1. **立即**: 任务 1 (测试验证) + 任务 2 (Actions 验证) - 并行
2. **通过后**: 任务 3 (数据复核) + 任务 4 (工作区清理)
3. **最后**: 任务 5 (删除 stash)
4. **后续**: 任务 6 (技术债务) 纳入下一迭代规划

---

*计划更新时间: 2026-11-04 (v3 - 发布后验证版)*
*基于审计结果与实际提交状态生成*