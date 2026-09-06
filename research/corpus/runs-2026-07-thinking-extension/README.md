# Run corpus — thinking-lineage extension (July 2026)

Frozen snapshot of the thinking-lineage arms extending
`data/runs-2026-07-generational-study/`: o1, o3, R1-0528, V3.2, kimi-k2.6,
kimi-k3 (84 run dirs, including crashed runs kept as audit evidence and one
2026-08-02 kimi-k3 rerun at raised caps). This README is provenance only —
analysis and reports are intentionally not included. All prior analysis
artifacts (per-run `profile.json`, the `openbench behavior`/`compare`
pipeline) were removed 2026-08-28 in an experiment restart; only raw run
data and grades remain.

## Contents

`<task>--<harness>--<model>--<timestamp>/` — one run: `run.json`,
`raw_transcript.jsonl`, `events.jsonl`, `workspace.patch`, `grade.json`,
`runner_error.log` (crashes only). Where present,
`grade.json.orig*` are superseded grades kept as an audit trail (see
Data-quality notes).

## Data-quality notes (read before analyzing)

- Exclude `run.json` `exit_reason == "crash"` (provider-side failures).
- **Grading**: all grades were re-issued 2026-07-24/2026-08-03 on repaired,
  golden-gated images after a grading-env defect; `grade.json` is current,
  `grade.json.orig*` are the superseded batch grades. A 133-run re-grade
  reproduced current grades exactly. Run `openbench golden-gate` before
  grading anything new.
- **Runtime validity**: the pytest-5262 task image was silently stale for
  batches run on/after 2026-07-12 — inside those runs' workspaces the
  repo's pytest could not start (Python 3.12 `import imp`). Affected runs
  are identifiable by that marker in `raw_transcript.jsonl` exec outputs.
  Decide explicitly how to treat those cells in any analysis; verification
  behavior on that task was unattainable for them.
- **Caps varied by arm** and are NOT in old run.jsons (recorded from
  2026-08-02 on): OpenAI arm $10 / 100 turns / 2 h; DeepSeek and Kimi arms
  $2.50 / 100 turns (4 h wall for R1). Cost accounting for first-party
  runs billed all input at full price (no cache discount) until
  2026-08-02, and the run-time price table differed from published rates
  for some models — recompute from token counts if dollars matter.
- Anticheat flags: check `assert_weakening_count` before interpreting
  `test_tampering` (additive test-writing also flags).

## Analysis

The experiment was restarted 2026-08-28: no analysis pipeline ships with
this corpus. Analyze the raw artifacts directly; grades derive from
`grade.json` as applies ∧ builds ∧ all F2P pass ∧ no P2P failures.
