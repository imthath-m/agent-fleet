# Judge check: labelling rubric

Fill the last three columns of `judge_sheet.csv` for every row. Do not open `judge_key.csv`
until you are done (it holds the LLM judge's scores).

- `human_score`: 0, 0.25, 0.5, 0.75 or 1
  - 0 = wrong, unrelated, or harmful
  - 0.25 = mostly wrong; at most one relevant fact
  - 0.5 = partially correct or incomplete; would not resolve the ticket alone
  - 0.75 = correct with minor gaps or noise
  - 1 = fully correct and complete per the reference
- `human_pass`: `y` if the answer correctly resolves the ticket per the reference, else `n`
- `human_notes`: optional free text

Then run `uv run python scripts/judge_agreement.py results/<date>`.
