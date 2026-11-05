# V0 历史 OHLC 异常记录独立核验报告

调查对象：`output/V0_daily_bars.csv` 中两条已知 OHLC 异常记录（2011-01-03、2020-08-06）。全程只读，未修改任何文件。

## 1. 异常记录原始字段值

CSV 表头：`symbol,name,trading_date,open,high,low,close,volume,open_interest,settle_raw,settle,quality_status,source,collected_at`

- 2011-01-03（第 395 行）：
  `V0,PVC连续,2011-01-03,8375,7885,8375,8375,0,0,0,,valid,AKShare futures_zh_daily_sina,2026-11-03T19:33:07.536538+08:00`
  - open=8375, high=7885, low=8375, close=8375, volume=0, open_interest=0, settle_raw=0, settle=空, quality_status=valid
- 2020-08-06（第 2720 行）：
  `V0,PVC连续,2020-08-06,6750,6770,6635,6610,144719,115643,0,,valid,AKShare futures_zh_daily_sina,2026-11-03T19:33:07.536538+08:00`
  - open=6750, high=6770, low=6635, close=6610, volume=144719, open_interest=115643, settle_raw=0, settle=空, quality_status=valid

相邻记录：
- 2010-12-31 close=8375；2011-01-04 open=8420/close=8515。
- 2020-08-05 close=6750；2020-08-07 open=6635/close=6580。

## 2. 异常表现与判定依据

- 2011-01-03：high(7885) < open/low/close(8375)，违反 OHLC（high 应为最高价）。volume/oi/settle 均为 0，疑似非交易日占位记录。2011-01-01 至 01-03 为元旦休市（SHFE 公告确认 01-01~01-03 休市；DCE 遵循国家假日），因此该行不应代表有效交易。
- 2020-08-06：low(6635) > close(6610)，违反 OHLC（low 应 <= close）。volume/oi 正常，settle 缺失（0/空），为真实交易日异常。

判定依据：OHLC 关系 `high < max(open,close,low)` / `low > min(open,close,high)`；代码 `validate_daily_bars()` 中 `invalid` 掩码定义与此一致。

## 3. 外部核验来源与结果

- AKShare 上游 Sina Finance 接口 `futures_zh_daily_sina(symbol="V0")`（URL `stock2.finance.sina.com.cn/.../InnerFuturesNewService.getDailyKLine`）：
  - 2011-01-03：`{"d":"2011-01-03","o":"8375.000","h":"7885.000","l":"8375.000","c":"8375.000","v":"0","p":"0","s":"0.000"}` — 与 CSV 完全一致。
  - 2020-08-06：`{"d":"2020-08-06","o":"6750.000","h":"6770.000","l":"6635.000","c":"6610.000","v":"144719","p":"115643","s":"0.000"}` — 与 CSV 完全一致。
  - 结论：异常值来自上游源数据，非本地转换/合并引入。
- DCE 官方日行情页面尝试访问未成功（412/页面非结构化），未获得独立交易日记录；SHFE 公告仅支持 2011-01-03 为休市日的旁证。未获得 2020-08-06 的独立交易所数据。
- 因此 2020-08-06 哪个字段错误（low 或 close）无法外部判定；2011-01-03 行与休市日一致，疑似占位/错误记录。

## 4. 异常最可能成因及证据强度

- 2011-01-03：源数据异常（占位/错误行）——证据强度：中高。上游 Sina 原样返回相同异常值；volume=0 且日期处于元旦休市期；但未获得 DCE 官方当日行情直接确认。
- 2020-08-06：源数据异常（OHLC 字段不一致）——证据强度：高（上游原样返回相同值）。具体哪个字段应为正确值：证据不足，不能判定。

排除：接口转换问题（字段映射与数值一致）；历史合并问题（行未被合并/覆盖异常引入；CSV 值与上游一致）。

## 5. 代码识别状态 vs CSV 实际状态

- `validate_daily_bars()`：
  - `known_bad_dates = {"2011-01-03", "2020-08-06"}`；`known_bad = normalized_dates.isin(...) & invalid`；`unexpected_bad = invalid & ~known_bad`。
  - 已知异常日期保留记录并标记 `quality_status = invalid_ohlc`；未知异常也标记 `invalid_ohlc` 并告警。
  - `confirmed_errors` 仅对 TA0/L0/HC0 的特定日期执行删除；V0 不在其中，因此 V0 异常不会被删除。
- CSV 实际状态：两条记录 `quality_status = valid`。原因是历史 CSV 由增量合并生成：`update_daily_bars` 保留旧记录原样，仅新采集行经过 `validate_daily_bars()`；这两条历史行从未被重新校验/重写，因此状态停留在采集 당시的 `valid`。源码识别逻辑并不自动回填历史 CSV。
- 测试 `test_daily_quality.py` 明确期望 known bad date 在当次验证时被标记 `invalid_ohlc`，与代码一致。

## 6. 修复条件与建议

- 是否具备修复条件：部分具备。
  - 2011-01-03：可考虑删除该行（休市日占位/错误记录）或标记 invalid_ohlc；但删除需确认 DCE 当日无交易（旁证支持，未获官方当日数据）。建议优先标记 invalid_ohlc，保留数据可追溯；若确认休市，可删除。
  - 2020-08-06：无法确定正确字段值，不具备直接修正条件；应保持 invalid_ohlc 标记，不猜测数值。
- 具体字段/建议值/来源：
  - 2011-01-03：建议 `quality_status` 从 `valid` 改为 `invalid_ohlc`（或删除整行）；依据：Sina 上游原始值 high<open，volume=0，日期处于元旦休市期。无可靠建议 OHLC 替代值。
  - 2020-08-06：建议 `quality_status` 从 `valid` 改为 `invalid_ohlc`；不修改 OHLC；依据：Sina 上游原始值 low>close，无法判定哪一字段错误。
- 若执行修复（需用户授权，本任务不执行）：应通过重新运行采集/或受控数据治理脚本更新 `quality_status`，并保留审计记录；不得静默改写 OHLC。

## 7. 两条记录处理建议

- 2011-01-03：标记为 `invalid_ohlc`（或在确认休市后删除），不提供 OHLC 替代值。
- 2020-08-06：标记为 `invalid_ohlc`，保留原始 OHLC，等待独立交易所数据或人工复核后再决定是否修正/删除。

## 结论

两条异常均为上游源数据异常，非本地转换或合并问题。代码在当次校验时会将其标记为 `invalid_ohlc`，但历史 CSV 因增量合并保留了过时的 `valid` 状态。当前不具备安全修正数值的条件；建议先将状态更正为 `invalid_ohlc`（需授权执行），OHLC 值保持原样，删除仅在确认休市/错误来源后进行。
