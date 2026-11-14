# results/

Live-model eval runs only (`python -m triage.eval --live`), one dated folder per run: `summary.json` plus one `<suite>.jsonl` per suite.
These are never compared to `baselines/`; the fake-model baselines that CI gates on live in `baselines/`.
Existing folders are never overwritten (a rerun on the same UTC date gets a `-2`, `-3`... suffix).
