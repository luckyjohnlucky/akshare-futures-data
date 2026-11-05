# Operations

Status: current
Version: 1.0
Last updated: 2026-11-05

## Running locally

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python fetch_pvc.py
```

Requirements: `akshare>=1.20,<2.0`, `numpy>=2.0,<3.0`, `pandas>=3.0,<4.0`,
`requests>=2.31`. Python 3.9+ (virtual environment uses 3.13).

Execution order: minute bars stream and daily bars stream are independent and run
in parallel. A single stream failure does not affect other streams.

## GitHub Actions

Workflow: `.github/workflows/collect.yml`.

- Trigger: `workflow_dispatch` only (manual). There is **no** `schedule`/`cron`
  and no `repository_dispatch`. Confirmed by static review of the workflow file
  and by `investigation_report.md`.
- Permissions: `contents: write`. Checkout uses
  `token: ${{ secrets.GITHUB_TOKEN }}` with `persist-credentials: true`.
- Concurrency: `group: pvc-collect-nine`, `cancel-in-progress: false`.
- Branch check: only verifies `GITHUB_REF_TYPE == branch`; no longer restricted
  to a specific branch name.
- Steps: checkout → setup-python → cache pip → install deps → configure git →
  branch check → `python fetch_pvc.py` → commit CSVs → push.
- Commit step builds the CSV list dynamically from files that exist at run time
  (9 commodity symbols × 2 streams, plus any H11061 files present). It is not
  hard-coded to a fixed file list.
- Push: a single `git push origin "HEAD:refs/heads/${GITHUB_REF_NAME}"` after commit. The workflow does not run `git fetch` or `git rebase`, and has no push retry loop.

### Confirmed vs. unverified

- Confirmed: trigger type, permissions, concurrency group, single push, dynamic
  file list, branch check — all read directly from `collect.yml`.
- Unverified: whether `persist-credentials: true` + `contents: write` is the
  minimum required for the automatic push to work (audit items S-1/S-2, U-6).

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| Request hangs indefinitely | AKShare functions have no exposed `timeout`; underlying `requests.get` can block. Recorded as P0-4 (V2.3.2). |
| Some symbols missing from output | A task failed silently — task exceptions are only logged, not propagated. Recorded as P0-2 (V2.3.2). |
| `minute_data_quality.jsonl` absent | Either no future-timestamp anomalies were produced, or the log was cleared. Absence does not prove the filter never ran (U-4). |
| `output/H11061_daily_bars.csv` no longer exists | The legacy generic-schema file was removed from Git tracking; the replacement is `output/H11061_index_daily.csv`. |
| Workflow pushes to an unexpected branch | Push target is `${GITHUB_REF_NAME}`, i.e. the branch that triggered the run. Branch scope is only `GITHUB_REF_TYPE == branch` (P2-4). |

## Maintenance notes

- No data retention policy exists; daily/minute CSVs grow indefinitely (audit
  item S-7, README Known Limitations).
- `merge_v0_data.py` is a one-off tool, not part of the collection flow. It reads
  `origin/main` data and merges with remote priority; its remote-override
  semantics are a design risk, not a confirmed bug (P2-7).
- Backups are preserved in `backup/` and `.kilo/phase4_backup/`. Do not delete
  without explicit approval.