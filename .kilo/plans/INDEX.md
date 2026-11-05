# .kilo/plans Index

Status: current
Version: 1.0
Last updated: 2026-11-05

This directory holds audit reports, plans, reviews, and governance
follow-up records under `.kilo/plans/`. It is **not** an exhaustive directory
manifest; `INDEX.md` itself is not listed.

## Audit reports (newest first)

| File | Label | Status |
|------|-------|--------|
| `1793796003000-final-audit-report-v2.3.2.md` | V2.3.2 (file) / V2.3.1 (internal H1) | current (latest audit report) |
| `1793796003000-final-audit-report-v2.3.1.md` | V2.3.1 | historical |
| `1793796003000-final-audit-report-v2.3.md` | V2.3 | historical |
| `1793796003000-final-audit-report-v2.2.md` | V2.2 | historical |
| `1793796003000-final-audit-report-v2.1.md` | V2.1 | historical |
| `1793796003000-final-audit-report-v2.md` | V2 | historical |
| `1793796003000-final-audit-report.md` | V1 | historical (complete report, 406 lines) |
| `1793794755058-final-audit-report.md` | — | historical (skeleton/draft, 70 lines) |

## Plans

| File | Status |
|------|--------|
| `akshare-doc-governance-plan.md` | historical (governance baseline plan) |
| `1793780657325-h11061-index-daily-revised-plan.md` | historical |
| `1793711576733-h11061-index-daily-plan.md` | historical — contains outdated Git baselines (local `9b94b5e`, remote `2fa46b7`); not a current fact |
| `pvc-phase1-implementation-plan.md` | historical |
| `1793819000000-doc-consistency-final-fix-plan.md` | current (documentation consistency repair) |

## Reviews

| File | Status |
|------|--------|
| `pvc-final-review.md` | historical — reports 25/25 tests and V0 4230/2058 rows; the minute count 2058 conflicts with the measured 2396 |
| `pvc-contract-data-review.md` | historical — AKShare 1.20.0 contract availability review |

## Governance follow-up records (2026-11-05)

| File | Type | Status |
|------|------|--------|
| `1793810425413-doc-governance-review-fixes.md` | review fixes | historical |
| `1793812557469-h11061-daily-bars-deletion-investigation.md` | investigation | historical |
| `1793813500000-v0-ohlc-anomaly-verification.md` | verification | historical |
| `1793814557469-v0-ohlc-fix-execution.md` | execution record | historical |
| `1793816000000-v0-downstream-governance-plan.md` | plan | historical |
| `1793817000000-v0-doc-governance-review.md` | plan | historical |

## Duplicate

`plan/pvc-contract-data-review.md` was a near-duplicate of
`.kilo/plans/pvc-contract-data-review.md`. The `plan/` copy has been removed
from the working tree; `.kilo/plans/pvc-contract-data-review.md` is the
retained canonical version. The deletion remains unstaged, and no Git write
operation has been performed.

## Stale reference

`.github/workflows/collect.yml.bak` is a historical backup of the older
workflow version (H11061 collected inside the symbol loop). The current
`collect.yml` pulls H11061 out. Retain this backup; do not modify or delete
it without explicit approval.

## Backups (preserved, not modified)

- `backup/` — `collect.yml`, `fetch_pvc.py`, `README.md`
- `.kilo/phase4_backup/` — V0 pre_merge + V2701/2705/2709 data

## Historical baseline note

`.kilo/plans/akshare-doc-governance-plan.md` §2.1 records `README.md` as "180 行".
That figure is the baseline at plan authoring time (2026-11-05); the current
`README.md` is 191 lines. The plan is retained as a historical record; its
line-count baseline is not updated retroactively.

## Root-level non-document files (outside this index's scope)

- `test1.py` — historical AKShare signature probe (14 lines); not part of the
  test suite. Deleted from the working tree; retained here as historical context.
  Listed as a cleanup candidate in `akshare-doc-governance-plan.md` §2.1/§5.2.
  It lived at the repository root, not in `.kilo/plans/`, so it is not indexed
  above.

## Version label note

`1793796003000-final-audit-report-v2.3.2.md` carries the file name V2.3.2 while
its internal H1 heading reads V2.3.1. This is a preserved revision-scope artifact
from the V2.3.1 revision pass; it is one report, not two separate versions.

## Deleted test artifacts

- `write-test.md`
- `write-test-a.md`
- `write-test-b.md`
- `write-test-c.md`
- `planner-coder-collaboration-test.md`
- `planner-tool-test.md`

These six files were historical tool-test outputs, not test results. They were
deleted during the cleanup process and are no longer present.

---

**Verification limitation note:** The existence, titles and classifications of the
investigation/verification records were checked, but their complete substantive
evidence was not re-reviewed in this reconstruction pass.