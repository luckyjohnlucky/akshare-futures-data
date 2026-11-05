# Testing

Status: current
Version: 1.0
Last updated: 2026-11-05

## Running tests

```bash
python -m unittest discover -s tests -v
```

## Test inventory

| File | `def test_` count |
|------|-------------------|
| `tests/test_daily_quality.py` | 11 |
| `tests/test_minute_quality.py` | 14 |
| `tests/test_index_daily.py` | 14 |
| `tests/test_json_csv_consistency.py` | 7 |
| `tests/test_failure_safety.py` | 4 |
| **Total Python** | **50** |
| `tests/test_workflow_collect.sh` | 8 scenarios |

> `def test_` is a static count, not a measure of execution. Counting definitions
> does not equal running them.

## Isolation

`tests/conftest.py` redirects all Python tests to
`tempfile.TemporaryDirectory()`. Python tests never touch real network or real
`output/` data.

**Shell tests are not covered by this isolation.** `tests/test_workflow_collect.sh`
contains 8 `rm -rf output` statements. If executed from the project root it can
affect the real `output/` directory. Recorded as audit issue P1-3 (V2.3.2).

## Evidence boundaries

- Confirmed by static review: 50 Python test definitions, 8 Shell scenarios,
  Python fixture isolation via `conftest.py`.
- Not performed in this governance pass: running the test suite, running real
  collection, triggering GitHub Actions, running `merge_v0_data.py`, full data
  quality validation.
- `test1.py` was an AKShare signature probe (14 lines), not part of the test
  suite. It has been deleted from the working tree; this note is retained as
  historical context only.
- Six files under `.kilo/plans/` (`write-test.md`, `write-test-a.md`,
  `write-test-b.md`, `write-test-c.md`,
  `planner-coder-collaboration-test.md`, `planner-tool-test.md`) were historical
  tool-test outputs, not test results. They were deleted from the working tree
  in the first cleanup batch and are no longer present.

## Acceptance principle

A claim of "tests pass" must name the exact command run and its output. A test
count is not a test result.