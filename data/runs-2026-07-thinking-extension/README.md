# Run corpus — thinking-lineage extension (July 2026, grades corrected 2026-08-02)

Frozen snapshot of the thinking-lineage arms extending the generational study
(`data/runs-2026-07-generational-study/`): both labs' reasoning lineages plus a
third lab, as five within-lab pairs. Old/new sides drawn from these runs plus
the already-frozen gpt-5.5 / deepseek-v4-pro runs of the July study.

## Corrected results (SWE-bench-Verified stratum, 12 usable runs per model)

| pair | old → new | solve |
|---|---|---|
| gpt-think-early | o1 → o3 | 1/12 → 9/12 |
| gpt-think-late | o3 → gpt-5.5 | 9/12 → 12/12 |
| deepseek-think-early | R1-0528 → V3.2 | 0/12 → 5/12 |
| deepseek-think-late | V3.2 → v4-pro | 5/12 → 12/12 |
| kimi-think | kimi-k2.6 → kimi-k3 | 8/12 → 11/12 |

`behavior_report_thinking_verified.md` is generated from these corrected
grades.

## The grading-env incident (why grades were corrected)

The original July-12/19 grading batches ran against a silently restored stale
docker image for `pytest-dev__pytest-5262` (a colima VM recreation restored a
June-18 image export, reverting the per-task-Python fix): Python 3.12 cannot
run 2019-era pytest (`import imp`), so pytest crashed before collection and
every expected test id was counted failed — including for the GOLD patch.
A second latent defect (history truncation deleted ancestor tags →
setuptools_scm versioned pytest as `0.1.dev*` → its own minversion check
aborted the suite) broke fresh rebuilds the same way; both were fixed
2026-07-24 (see commits `5394117` and the incident notes in the repo memory).

On the repaired image, all 32 pytest-5262 runs were re-graded: every
trustworthy pre-incident grade reproduced identically, and 8 artifact-era
grades flipped to resolved — kimi-k3 ×3 (its three "failed" patches are the
gold fix verbatim), kimi-k2.6 ×3, o1 ×1, V3.2 ×1. Each affected run dir keeps
the superseded grade as `grade.json.orig*` (audit trail); `grade.json` is the
corrected verdict and records the `image_id` it was graded against.

## Reading guide

- Exclude `run.json` `exit_reason == "crash"` (infrastructure, never model
  behavior). Kimi's two crashes predate the tooluse dangling-tool_call_id fix.
- **Cap asymmetry**: the OpenAI thinking arm ran at $10 / 100 turns / 2 h;
  DeepSeek and Kimi arms at $2.50 / 100 turns (4 h wall for R1's slow hosts).
  kimi-k3 is priced at $3/$15 per Mtok, so its $2.50 cap ≈ 40 turns: its one
  remaining Verified failure (sympy-13757, seed 224457) is a cost_cap kill,
  and cost was computed billing every input token at full price although
  Moonshot discounts cached prefix to $0.30/M — treat k3's 11/12 as a floor.
  **Symmetric-budget footnote**: rerun 2026-08-02 at the o-series caps
  ($10 / 100 turns), that cell RESOLVES (run `…kimi-k3--20260802-194913`,
  turn 81, $2.31 cache-aware — Moonshot reported 97.5% of input as cache
  hits, so the July accounting had overbilled this trajectory ~5x). The
  banked 12-run cells are unchanged; under budget parity kimi-k3 is 12/12.
- **Run-time prices**: `cost_usd` in these runs used the July price table
  (o1 15/60, o3 2/8, kimi-k2.6 0.95/4, kimi-k3 3/15 — all verified correct;
  OpenRouter runs carry provider-exact `usage.cost`). Note for cross-study
  comparisons: the July study priced gpt-5.5 at 3/15 and v4-pro at 1.2/4.8;
  published rates as of 2026-08-02 are 5/30 and 0.435/0.87 — recompute from
  token counts if absolute dollars matter.
- R1-0528 is the only model in the corpus that weakens tests (128 asserts on
  sympy-22914); kimi tampering flags are all *additive* tests — check
  `anticheat.assert_weakening_count` before citing `test_tampering`.

## Reproduce the report

```bash
cp -R data/runs-2026-07-thinking-extension/* runs/
uv run openbench behavior
uv run openbench compare --pair gpt-think-early --pair gpt-think-late \
    --pair deepseek-think-early --pair deepseek-think-late --pair kimi-think \
    --source swebench-verified --out runs/behavior_report_thinking_verified.md
```

Before grading anything, run `uv run openbench golden-gate` — the incident
above is exactly the failure class it catches.

## Round-2 robustness audit (2026-08-03)

Five independent checks on the corrected table:

1. **Reproducibility**: all 133 usable verified-stratum runs (both corpora)
   re-graded from scratch on golden-gated images — 132/132 model runs
   reproduce exactly (verdict AND per-test counts); the single flip is a
   sympy-13757 golden fixture banked during the broken early-July-7 grading
   window, healing to resolved.
2. **False-solve audit**: all 73 resolved runs pass anticheat (no assert
   weakening), touch non-test source, and show no gold-mining in transcripts
   (`git log --all` sightings hit single-commit re-initialized repos).
3. **Runtime-env validity**: transcript scan for the Python-3.12 `import imp`
   crash shows every post-July-12 batch RAN pytest-5262 in a broken workspace
   (the stale-image swap happened mid-matrix on July 12). Solves stand — o3
   3/3 and kimi-k3 3/3 solved it without runnable tests; o1 even stubbed the
   `imp` module and solved. Broken-env FAILURES are uninterpretable and drop
   from denominators: **o1 1/11, R1-0528 0/10, V3.2 5/10** (others unchanged).
   Behavioral verification metrics (green_observed etc.) for those arms on
   this task reflect the broken env — treat 5262 cells of the July-12/19
   arms as handicapped when citing behavior, or rerun them on the repaired
   image for clean trajectories.
4. **Crash exclusions**: every excluded crash is provider-side (402/429/dead
   key, pre-heal Moonshot 400s); all crashed cells were re-run to 12 usable.
5. **Sensitivity**: independent recount matches the report; leave-one-task-out
   never changes any pair delta sign. Caveat: the o3→gpt-5.5 SOLVE delta
   (9→12) comes entirely from sympy-13757 — cite that pair on its efficiency
   deltas, which are task-general.

## Are the zeros real? (0/12-class results, audited 2026-08-03)

Each zero fails in a distinct, model-shaped way — none is protocol-shaped:

- **V3-0324 (0/12)**: bimodal — half its runs emit ~100% malformed actions
  (chat-style text instead of tool calls), the rest act but grind to cap.
  NUANCE: its one crashed run (excluded as infra per convention) had ALREADY
  solved pytest-5262 when the OpenRouter 400 killed it — the model can solve;
  the usable seeds didn't. Read 0/12 as "capability exists but is unreliable",
  with a 95% binomial upper bound of ~25% on this task mix.
- **R1-0528 (0/10)**: malformed rate ~0.1 — its tool calls parse fine and it
  edits files (median ~5), then declares completion falsely in 12/12 usable
  runs (and weakens 128 asserts on 22914). The pipe works; the model quits.
- **o1 (1/11)**: malformed 0.0 in every run, 10+ edits/run, one genuine
  resolve — fails by destructive rewrites + confabulation, not protocol.

Every zero model has a same-wire-format sibling that solves (V3.2/V4 on
tooluse, o3 on gpt-responses), so each protocol path is proven end-to-end.
These are measurements of AUTONOMOUS agentic reliability on a deliberately
minimal harness (single bash tool, tool_choice=auto) — they are consistent
with, not contradicted by, higher public SWE-bench numbers that measure
model+heavyweight scaffold.
