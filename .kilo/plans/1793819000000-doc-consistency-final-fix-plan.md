# Final documentation consistency repair plan

Plan file: `.kilo/plans/1793819000000-doc-consistency-final-fix-plan.md`

## Goal

Apply the smallest possible documentation-only corrections to four files:

1. `docs/testing.md`
2. `docs/audit-history.md`
3. `.kilo/plans/INDEX.md`
4. `.kilo/plans/akshare-doc-governance-plan.md`

No source code, CSV, workflow, test, backup, or other documentation file may be changed.

## Pre-checks (read-only)

Record before editing:

- Branch and HEAD: `main`, `fb97907fcb2678450abdd33d85ac32c3f19e2264`
- `git status --short`
- SHA-256 of the four target files
- `wc -l README.md` = 191
- `test1.py` absent from the working tree
- Six deleted tool-test files absent:
  - `write-test.md`
  - `write-test-a.md`
  - `write-test-b.md`
  - `write-test-c.md`
  - `planner-coder-collaboration-test.md`
  - `planner-tool-test.md`
- Six governance follow-up files present and individually verified by reading
  their titles/content:
  - `1793810425413-doc-governance-review-fixes.md` — review fixes
  - `1793812557469-h11061-daily-bars-deletion-investigation.md` — investigation
  - `1793813500000-v0-ohlc-anomaly-verification.md` — verification
  - `1793814557469-v0-ohlc-fix-execution.md` — execution record
  - `1793816000000-v0-downstream-governance-plan.md` — plan
  - `1793817000000-v0-doc-governance-review.md` — plan (INDEX consistency repair)
- `.kilo/plans/1793814557469-v0-ohlc-fix-execution.md` contains the V0 OHLC correction evidence.

If any target file state differs from the expected state above, stop and report before editing.

## Authorized edits

### 1. `docs/testing.md`

Current lines 45-47:

```markdown
- `test1.py` is an AKShare signature probe, not part of the test suite.
- Test artifacts `write-test*.md` and `planner-*-test.md` in `.kilo/plans/` are
  tool-test outputs, not test results.
```

Replace with:

```markdown
- `test1.py` was an AKShare signature probe (14 lines), not part of the test
  suite. It has been deleted from the working tree; this note is retained as
  historical context only.
- Six files under `.kilo/plans/` (`write-test.md`, `write-test-a.md`,
  `write-test-b.md`, `write-test-c.md`,
  `planner-coder-collaboration-test.md`, `planner-tool-test.md`) were historical
  tool-test outputs, not test results. They were deleted from the working tree
  in the first cleanup batch and are no longer present.
```

### 2. `docs/audit-history.md`

In `## Issue summary (V2.3.2, current)`, change the P1 row:

From:

```markdown
| P1 | 4 | non-vectorized date parsing; JSONL concurrent write without lock; Shell test `rm -rf output` risk; two V0 OHLC anomalous records marked `valid` |
```

To:

```markdown
| P1 | 4 | non-vectorized date parsing; JSONL concurrent write without lock; Shell test `rm -rf output` risk; two V0 OHLC anomalous records marked `valid` at audit time (corrected to `invalid_ohlc` on 2026-11-05) |
```

After the issue summary table and before `## Unverified items`, insert:

```markdown
## V0 OHLC anomaly status (time-limited)

- Audit V2.3.2 recorded the two V0 daily records (`2011-01-03`,
  `2020-08-06`) with `quality_status = valid` as the audit-time state.
- On 2026-11-05, both records were corrected to `invalid_ohlc` in
  `output/V0_daily_bars.csv`; OHLC values were not changed. Evidence:
  `.kilo/plans/1793814557469-v0-ohlc-fix-execution.md`.
- Historical audit conclusions remain accurate for their audit-time state and
  are not rewritten.
```

### 3. `.kilo/plans/INDEX.md`

#### 3.1 Add scope note

After the introductory paragraph ending with the current audit entry point sentence, insert:

```markdown
Scope: this index curates audit reports, plans, reviews, and governance
follow-up records under `.kilo/plans/`. It is not an exhaustive directory
manifest; `INDEX.md` itself is not listed.
```

#### 3.2 Change governance plan status

In `## Plans`, change:

From:

```markdown
| `akshare-doc-governance-plan.md` | current (this governance plan) |
```

To:

```markdown
| `akshare-doc-governance-plan.md` | historical (governance baseline plan) |
```

#### 3.3 Correct `test1.py` status

In `## Root-level non-document files (outside this index's scope)`, change:

From:

```markdown
- `test1.py` — AKShare signature probe (14 lines); not part of the test suite.
```

To:

```markdown
- `test1.py` — historical AKShare signature probe (14 lines); not part of the
  test suite. Deleted from the working tree; retained here as historical context.
```

#### 3.4 Correct README baseline

In `## Historical baseline note`, change `the current README.md is 192 lines` to `the current README.md is 191 lines`.

#### 3.5 Add governance follow-up records

Insert before `## Duplicate`:

```markdown
## Governance follow-up records (2026-11-05)

| File | Type | Status |
|------|------|--------|
| `1793810425413-doc-governance-review-fixes.md` | review fixes | historical |
| `1793812557469-h11061-daily-bars-deletion-investigation.md` | investigation | historical |
| `1793813500000-v0-ohlc-anomaly-verification.md` | verification | historical |
| `1793814557469-v0-ohlc-fix-execution.md` | execution record | historical |
| `1793816000000-v0-downstream-governance-plan.md` | plan | historical |
| `1793817000000-v0-doc-governance-review.md` | plan | historical |
```

Keep all other sections unchanged.

### 4. `.kilo/plans/akshare-doc-governance-plan.md`

Insert immediately after the title line:

```markdown
Status: historical
Version: 1.0
Last updated: 2026-11-05

Baseline note: this plan was authored before `docs/` existed and before
`README.md` reached 191 lines. Statements such as "docs/ missing" and
"README.md (180 行)" are historical baselines, not current facts. The plan is
retained as planning history; its recommendations and acceptance criteria are
not rewritten.
```

Do not modify any other content in this file.

## Validation

After editing, verify:

1. `grep -n "tool-test outputs, not test results" docs/testing.md` returns the updated historical wording.
2. `grep -n "V0 OHLC anomaly status (time-limited)" docs/audit-history.md` confirms the new subsection.
3. `grep -n "Governance follow-up records (2026-11-05)" .kilo/plans/INDEX.md` confirms the new section.
4. `grep -n "Status: historical" .kilo/plans/akshare-doc-governance-plan.md` confirms the status header.
5. `grep -n "192 lines" .kilo/plans/INDEX.md` returns no matches.
6. `git status --short` is byte-for-byte identical to the pre-edit recording.
7. `git diff --stat` shows no new tracked-file changes beyond the pre-existing state.
8. A full-file manifest comparison shows no added, deleted, or modified file outside the four targets.
9. SHA-256 comparison shows only the four target files changed.

## Proving other files were not modified

- Record `git status --short` before editing.
- Record SHA-256 hashes of the four target files before editing.
- Create a pre-edit manifest of every file under the repository except `.git/`
  and the four target files, for example:
  `find . -path ./.git -prune -o -type f ! -path './docs/testing.md' ! -path './docs/audit-history.md' ! -path './.kilo/plans/INDEX.md' ! -path './.kilo/plans/akshare-doc-governance-plan.md' -print0 | sort -z | xargs -0 shasum -a 256 > /tmp/pre-manifest.sha256`
- After editing, recreate the same manifest as `/tmp/post-manifest.sha256`.
- Compare the two manifests after removing any target-file lines; they must be
  byte-for-byte identical.
- Compare `git status --short` before and after; it must be byte-for-byte identical.
- Any added, deleted, modified, or renamed file outside the four targets is a
  validation failure.
- Pre-existing tracked and untracked changes must remain unchanged and must not
  be attributed to this task.

## Rollback

If validation fails, do not use `git checkout`, `git restore`, `git reset`, or any
other Git write operation. Restore each of the four target files only from its
exact pre-edit content, using the recorded pre-edit copy or content snapshot.
If exact restoration cannot be guaranteed, stop and report the failure without
attempting rollback. Never restore the files from HEAD or the index.