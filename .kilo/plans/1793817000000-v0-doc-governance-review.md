# INDEX.md consistency repair

## Goal

Update `.kilo/plans/INDEX.md` only, to remove stale references to already-deleted tool-test artifacts and to correct the status of the duplicate PVC contract review document.

## Pre-checks

Confirm before editing:

- Current branch is `main`.
- The following files do not exist:
  - `__pycache__/`
  - `.pytest_cache/`
  - `test1.py`
  - `.kilo/plans/write-test.md`
  - `.kilo/plans/write-test-a.md`
  - `.kilo/plans/write-test-b.md`
  - `.kilo/plans/write-test-c.md`
  - `.kilo/plans/planner-coder-collaboration-test.md`
  - `.kilo/plans/planner-tool-test.md`
- `plan/pvc-contract-data-review.md` does not exist in the working tree.
- `.kilo/plans/pvc-contract-data-review.md` exists.
- Record the current `git status --short` output before editing.

## Authorized edit

File to modify:

- `.kilo/plans/INDEX.md`

No other file may be changed.

## Exact changes

### 1. Remove the stale test-artifact section

Remove this entire section:

```markdown
## Test artifacts (candidates for deletion — requires approval)

| File | Note |
|------|------|
| `write-test.md`, `write-test-a.md`, `write-test-b.md`, `write-test-c.md` | tool write-test outputs |
| `planner-coder-collaboration-test.md`, `planner-tool-test.md` | planner tool-test outputs |
```

Keep the following `## Duplicate` section and all later sections unchanged except for the duplicate-status wording below.

### 2. Correct the duplicate-document status

Replace this block:

```markdown
## Duplicate

`plan/pvc-contract-data-review.md` is a near-duplicate of
`.kilo/plans/pvc-contract-data-review.md` (789 diff lines, mostly title,
status header, and Chinese/English translation of the same content).
Consolidation or deletion requires user approval.
```

with:

```markdown
## Duplicate

`plan/pvc-contract-data-review.md` was a near-duplicate of
`.kilo/plans/pvc-contract-data-review.md`. The `plan/` copy has been removed
from the working tree; `.kilo/plans/pvc-contract-data-review.md` is the
retained canonical version. The deletion remains unstaged, and no Git write
operation has been performed.
```

## Validation

After editing, verify:

- `git diff -- .kilo/plans/INDEX.md` contains only the two authorized changes.
- No other file appears as modified, deleted, or untracked because of this task.
- The `## Duplicate` heading and all later sections remain present.
- The `## Backups`, `## Historical baseline note`, `## Root-level non-document files`, and `## Version label note` sections remain unchanged.
- `git diff --cached -- .kilo/plans/INDEX.md` shows no staged change.
- The previously recorded uncommitted working-tree state remains otherwise unchanged.

## Rollback

If validation fails, discard only the INDEX.md edit before any other action. Do not restore `plan/pvc-contract-data-review.md` or any deleted test artifact.
