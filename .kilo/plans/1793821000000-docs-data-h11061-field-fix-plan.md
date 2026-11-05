# docs/data.md H11061 field list correction plan

Plan file: `.kilo/plans/1793821000000-docs-data-h11061-field-fix-plan.md`

## Goal

Correct only the H11061 field list in `docs/data.md` so it includes `symbol` and
`name` in the same order as the actual CSV header and collection code.

No other file may be changed.

## Pre-checks (read-only)

- Current branch: `main`
- HEAD: `fb97907fcb2678450abdd33d85ac32c3f19e2264`
- `docs/data.md` exists and is untracked.
- Actual CSV header:
  `symbol,name,index_code,trading_date,close,settle,change,pct_change,quality_status,source,collected_at`
- Code verification:
  - `fetch_pvc.py:update_index_daily_bars()` builds records with
    `symbol`, `name`, `index_code`, `trading_date`, `close`, `settle`,
    `change`, `pct_change`, `quality_status`, `source`, `collected_at`.
  - `name` is fixed as `中证商品期货指数`.
  - `index_code` is fixed as `100001.CCI`.
- Record `git status --short` and SHA-256 of `docs/data.md` before editing.

## Authorized edit

File to modify:

- `docs/data.md`

No other file may be changed.

## Exact change

In `## H11061 index daily fields`, replace:

```markdown
`trading_date, index_code(100001.CCI), close, settle, change, pct_change,
quality_status, source, collected_at`
```

with:

```markdown
`symbol, name, index_code(100001.CCI), trading_date, close, settle, change,
pct_change, quality_status, source, collected_at`
```

Keep the following bullet unchanged:

```markdown
- No OHLC / volume / hold fields (an index has no volume or open interest).
```

No other paragraph, heading, table, or wording may change.

## Validation

After editing, verify:

1. `sed -n '55,64p' docs/data.md` shows the corrected field list.
2. `head -n 1 output/H11061_index_daily.csv` matches the documented field order.
3. `git diff -- docs/data.md` contains only the field-list change.
4. `git status --short` has no additional entries beyond the pre-recorded state.
5. SHA-256 comparison shows only `docs/data.md` changed.

## Rollback

If validation fails, restore `docs/data.md` only from its exact pre-edit content or
snapshot. Do not use `git checkout`, `git restore`, `git reset`, or any other Git
write operation. If exact restoration cannot be guaranteed, stop and report
without attempting rollback.
```
filePath">
/Users/johnm/Projects/akshare-futures-data/.kilo/plans/1793821000000-docs-data-h11061-field-fix-plan.md