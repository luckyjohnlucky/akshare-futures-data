# Audit History

Status: current
Version: 1.0
Last updated: 2026-11-05

All audit reports are retained for traceability. None are deleted in this
governance pass. Reports are listed newest-first.

## Entry point

**`1793796003000-final-audit-report-v2.3.2.md`** — 18 issues (P0×3, P1×4,
P2×7, P3×4). This is the current audit entry point; supersede it only with a new
report.

## Audit reports

| File | Label | Status | Issues | Notes |
|------|-------|--------|--------|-------|
| `1793796003000-final-audit-report-v2.3.2.md` | V2.3.2 (file) / V2.3.1 (internal H1) | **current entry** | 18 (P0×3, P1×4, P2×7, P3×4) | File name V2.3.2, internal H1 heading V2.3.1 — a preserved revision-scope artifact, one report, not two. |
| `1793796003000-final-audit-report-v2.3.1.md` | V2.3.1 | historical | — | Cross-reference correction revision. |
| `1793796003000-final-audit-report-v2.3.md` | V2.3 | historical | — | Evidence-expression revision. |
| `1793796003000-final-audit-report-v2.2.md` | V2.2 | historical | — | |
| `1793796003000-final-audit-report-v2.1.md` | V2.1 | historical | — | Fact-error and grading revision. |
| `1793796003000-final-audit-report-v2.md` | V2 | historical | — | |
| `1793796003000-final-audit-report.md` | V1 | historical | — | Complete report (406 lines); the V1 entry point of the audit series. |
| `1793794755058-final-audit-report.md` | — | historical | — | Skeleton/draft (70 lines): only "编写计划" + evidence list + contradiction notes; body not populated. |

## Issue summary (V2.3.2, current)

| Severity | Count | Topics |
|----------|-------|--------|
| P0 | 3 | single-task failure not propagated; retry/exception-type mismatch; AKShare requests have no effective timeout |
| P1 | 4 | non-vectorized date parsing; JSONL concurrent write without lock; Shell test `rm -rf output` risk; two V0 OHLC anomalous records marked `valid` at audit time (corrected to `invalid_ohlc` on 2026-11-05) |
| P2 | 7 | missing pre-commit CSV quality gate; local vs remote audit baseline divergence; README task-count/speedup/push-retry errors; workflow branch scope; CI without unit tests; full read/write, dependency lock, cache, concurrency; `merge_v0_data.py` remote-priority override semantics |
| P3 | 4 | 0-byte H11061 minute placeholder; H11061 old/new daily file migration; stale assertion numbers 4229/2044; backup management |

## V0 OHLC anomaly status (time-limited)

- Audit V2.3.2 recorded the two V0 daily records (`2011-01-03`,
  `2020-08-06`) with `quality_status = valid` as the audit-time state.
- On 2026-11-05, both records were corrected to `invalid_ohlc` in
  `output/V0_daily_bars.csv`; OHLC values were not changed. Evidence:
  `.kilo/plans/1793814557469-v0-ohlc-fix-execution.md`.
- Historical audit conclusions remain accurate for their audit-time state and
  are not rewritten.

## Unverified items (V2.3.2 §13)

U-1 real AKShare collection success · U-2 field-level/completeness validation ·
U-3 H11061 969-record field quality · U-4 absence of
`minute_data_quality.jsonl` · U-5 README speedup accuracy · U-6
`persist-credentials`/`contents: write` necessity · U-7 `subprocess` without
timeout blocking risk · U-8 whether CI should run unit tests · U-9 scope of the
local-vs-remote difference (10 data CSVs).

None of these may be treated as confirmed defects.

## Out-of-scope code issues (recorded, not fixed)

OHLC anomalies, missing `timeout`, retry mismatch, non-vectorized parsing,
unlocked JSONL writes, Shell test deletion risk, stale assertions. These are
recorded only; this governance pass does not modify source, configuration, or
data.

## Related docs

- `docs/architecture.md`, `docs/data.md`, `docs/operations.md`, `docs/testing.md`
- `README.md` — primary entry point
- `investigation_report.md` — Git/workflow audit confirming `workflow_dispatch`
  only, no cron
- `.kilo/plans/akshare-doc-governance-plan.md` — this governance plan