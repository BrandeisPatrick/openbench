# Run corpus — generational behavior study (July 2026)

Frozen snapshot of the complete run corpus behind the chat-lineage
comparison (`deepseek-chat-v3-0324 → deepseek-v4-pro`, `gpt-4.1 → gpt-5.5`):
151 run directories (84 usable model runs — 21 per model — plus crashed
runs kept as audit evidence, and golden-fixture control runs). Total API
spend: ~$114. This README is provenance only — analysis and reports are
intentionally not included. All prior analysis artifacts (per-run
`profile.json`, the `openbench behavior`/`compare` pipeline) were removed
2026-08-28 in an experiment restart; only raw run data and grades remain.

## Contents

- `<task>--<harness>--<model>--<timestamp>/` — one run:
  `run.json` (outcome, cost, tokens), `raw_transcript.jsonl` (every API turn +
  executed command + output), `events.jsonl` (normalized TraceEvents),
  `workspace.patch` (the agent's diff), `grade.json` (F2P/P2P + anti-cheat),
  `runner_error.log` (crashes only).

## Data-quality notes (read before analyzing)

- Exclude `run.json` `exit_reason == "crash"` from any analysis
  (infrastructure failures: an exhausted API key mid-matrix, provider rate
  limits — never model behavior).
- Runs on the three quarantined tasks (`scikit-learn__scikit-learn-32659`,
  `sympy__sympy-29263`, `sympy__sympy-28318`) are audit evidence only —
  their grades measure task defects, not capability
  (see `datasets/quarantine/README.md`). Restrict headline analysis to the
  `source == swebench-verified` stratum.
- One run (`scikit-learn__scikit-learn-32659--tooluse--deepseek-v4-pro--…073854`)
  mined the gold solution from the task image's git history (leak since
  fixed at image level); no SWE-bench-Verified run touched git history —
  verified by transcript scan.
- Grades in this corpus were issued 2026-07-07 on healthy images and
  reproduced exactly in a 2026-08-03 re-grade on rebuilt, golden-gated
  images. Run `openbench golden-gate` before grading anything new.
- Run-time cost accounting billed all input at full price (no cache
  discount) and the price table for some models differed from published
  rates — recompute from token counts if dollars matter.

## Analysis

The experiment was restarted 2026-08-28: no analysis pipeline ships with
this corpus. Analyze the raw artifacts directly; grades derive from
`grade.json` as applies ∧ builds ∧ all F2P pass ∧ no P2P failures.

Caps used for every run: 100 turns, $2.50, 2 h wall clock, `--runner native`
(tooluse protocol for DeepSeek, gpt-responses for OpenAI — identical within
each generation pair).
