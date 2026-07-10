# Run corpus — generational behavior study (July 2026)

Frozen snapshot of the complete run corpus behind the generational comparison
(`deepseek-chat-v3-0324 → deepseek-v4-pro`, `gpt-4.1 → gpt-5.5`): 151 run
directories (84 usable model runs — 21 per model — plus crashed runs kept as
audit evidence, and golden-fixture control runs), with the generated reports
and figures. Total API spend: ~$114.

## Contents

- `<task>--<harness>--<model>--<timestamp>/` — one run:
  `run.json` (outcome, cost, tokens), `raw_transcript.jsonl` (every API turn +
  executed command + output), `events.jsonl` (normalized TraceEvents),
  `workspace.patch` (the agent's diff), `grade.json` (F2P/P2P + anti-cheat),
  `profile.json` (behavioral metrics), `runner_error.log` (crashes only).
- `behavior_report.md` — full-corpus report (all 7 tasks, both strata).
- `behavior_report_verified.md` — **the citable report**: SWE-bench-Verified
  stratum only, after the 3 mined tasks failed a fairness audit
  (see `datasets/quarantine/README.md`).
- `figures/` — the report figures.

## Reading guide

- Exclude `run.json` `exit_reason == "crash"` from any analysis (infrastructure
  failures: an exhausted API key mid-matrix, provider rate limits — never model
  behavior). The reports already do this.
- Runs on the three quarantined tasks (`scikit-learn__scikit-learn-32659`,
  `sympy__sympy-29263`, `sympy__sympy-28318`) are audit evidence only — their
  grades measure task defects, not capability.
- One run (`scikit-learn__scikit-learn-32659--tooluse--deepseek-v4-pro--…073854`)
  mined the gold solution from the task image's git history (the leak since
  fixed at image level); no SWE-bench-Verified run touched git history —
  verified by transcript scan.

## Reproduce the reports

```bash
cp -R data/runs-2026-07-generational-study/* runs/
uv run openbench behavior
uv run openbench compare --pair deepseek --pair gpt --source swebench-verified \
    --out runs/behavior_report_verified.md
```

Caps used for every run: 100 turns, $2.50, 2 h wall clock, `--runner native`
(tooluse protocol for DeepSeek, gpt-responses for OpenAI — identical within
each generation pair).
