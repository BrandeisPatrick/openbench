# Adversarial verification of the exploratory findings (2026-08-31)

Scope: the six exploratory findings derived 2026-08-28 from the frozen
reasoning-only corpora (9 models, 4 verified tasks, K=3). Finding 1 was
already demoted in review (Pass@3 saturation → censored capability axis;
its real test is the harder-task expansion). This pass attacked findings
2–6 at their weakest joints. Method and decision rules are fixed in
[analysis/verify_findings.py](../analysis/verify_findings.py) (rules
written before results were inspected); everything below derives from the
frozen corpora with zero new API spend.

## Verdicts

### Finding 2 — "procedure converges across generations" — REFINED, core survives

Threat tested: within-cell workflow similarity could be generic *style*
(same commands on any task), not task-level policy concentration.
Baseline: same-model **cross-task** verb-sequence similarity (54 pairs/model)
subtracted from within-cell similarity (12 pairs/model).

- The generational **rise survives**: the task-specificity margin
  (within − cross) rises along every lineage — deepseek +0.014→+0.130→+0.156,
  openai +0.022→+0.037→+0.113, kimi +0.076→+0.103→+0.186.
- But per-model, **old models' apparent procedure convergence is mostly
  style**: r1 (+0.014), o1 (+0.022), and notably o3 (+0.037) fail the
  pre-set margin ≥ 0.10 rule. Task-directed concentration is a property
  that *emerges* at the newest generation (plus v3.2).
- Style rigidity itself also rises with generation (cross-task baseline
  0.30→0.50 deepseek, 0.29→0.51 openai) — two distinct rising components,
  previously conflated.

### Finding 3 — Kimi V-shape / byte-identical patches — SURVIVES, strengthened

Threat tested: k2-thinking's 75% byte-identical patches could be
deterministic serving on OpenRouter, not policy sharpness.

- Full-trajectory divergence probe: **every repeat pair of every model
  forks within the first turn** (k2-thinking: ≤7 shared characters on
  most pairs; no pair anywhere in the corpus is trajectory-identical).
  Decoding was stochastic for all models. An earlier first-reasoning-turn
  heuristic flagged v3.2/k2-thinking/k3 — all three flags traced to short
  stereotyped opener sentences, cleared by the full-trajectory probe.
- Therefore the byte-identical final patches arise from **divergent
  reasoning paths that reconverge on the same exact edit set** — a
  stronger form of solution-space concentration than the original claim.
- Contamination check: k2-thinking's identical patches on sympy-13757 and
  sympy-22914 are **not** the gold patch (edit-overlap 0.00) — it has its
  own canonical fix, which argues against simple gold memorization.
  sympy-23534's gold-identical patches (also v4-pro, k2.6) are benign:
  the gold fix is a one-line change with essentially one minimal form.
- Standing caveat: the k2-thinking→k2.6 link crosses hosts
  (OpenRouter→Moonshot first-party; sampling defaults unrecorded on both
  sides), so the *left arm* of the V carries a host asterisk. The dip and
  recovery (k2.6→k3) are host-uniform.

### Finding 4 — DeepSeek rollout compression — REVISED

Threat tested: the 174k→72k→28k reasoning-volume gradient could be the
known failures-run-long effect (r1 never solves; v4 always does).

- Conditional on **solved runs only**: v3.2 56,770 → v4-pro 15,882 chars
  (3.6×) — the g2→g3 compression is real within-outcome.
- The g1→g2 step is **not measurable within-outcome** (r1 has zero
  solves); r1's 174k is failure-only volume. Within v3.2, failed runs are
  indeed longer than solved (83k vs 57k), as the literature predicts.
- Censoring differs by model: r1 exited `completed` 12/12 (its volume is
  uncensored — it stops on its own after enormous reasoning and ~10
  commands); v3.2 was turn-capped in 9/12 (its volumes are lower bounds).
  Direction r1 > v3.2 survives; magnitude is uncertain.
- Kimi correction: conditional on success, k2.6→k3 volumes are flat
  (29.0k → 31.1k) — "k3 thinks more" is not supported on solved runs; the
  raw mean was inflated by one 67k failed run and 4 cost-capped runs.

### Finding 5 — failures scatter, never the identical wrong patch — SURVIVES

Direct recount: 31 within-cell failed pairs, **0** identical non-empty
wrong patches, 1 both-empty pair. The negative existential holds exactly.

### Finding 6 — "OpenAI solves orthogonally to gold" — DEMOTED to a refined form

Threat tested: low gold-similarity could be metric artifact rather than a
different fix mechanism. Decomposition (edit vs file overlap with gold) +
reading the patches:

- pytest-5262: gpt-5.5's fix is the **same mechanism as gold** (a `mode`
  property stripping `"b"`, line-for-line equivalent core); low Jaccard
  comes from collateral volume — an added test file, docstrings; o3 adds
  broken-runtime repair shims (`imp`/`pkg_resources` stubs) and quote-style
  churn. Metric artifact.
- sympy-22914: gpt-5.5's fix is a **genuinely different mechanism**
  (`_print_Min`/`_print_Max` printer methods vs gold's `_known_functions`
  dict entries). Real difference.
- Corrected statement: OpenAI never reproduces gold's exact lines, mixing
  genuine alternative implementations with same-mechanism-plus-collateral
  (tests, docs, churn); Kimi/DeepSeek write minimal patches that often
  coincide with gold. The scalar "orthogonal style" overclaims — per-task
  mechanism classification is required before any style attribution.
- Side observation: on sympy-13757 *every* model bypasses gold's
  `_op_priority` one-liner with its own different fix — gold is one of
  several valid mechanisms there.

## Cross-cutting confound (annotates 2–4)

Serving-host map: deepseek r1/v3.2 ran via OpenRouter, v4-pro first-party
(the **g2→g3 link crosses hosts**); kimi k2-thinking via OpenRouter,
k2.6/k3 first-party (**g1→g2 crosses**); openai uniform first-party. No
sampling parameters were sent by the harness and provider-side defaults
are unrecorded, so host-crossing links inherit an unquantifiable
sampling-regime uncertainty. The OpenAI lineage — host-clean end to end —
shows the same qualitative pattern (rising task-specificity margin,
compression on solved runs o3→5.5), which anchors the cross-lab story.

## Status

All findings remain **exploratory** (4 task clusters, no significance
claims). The harder-task expansion (finding 1's test) is the confirmatory
step; these verdicts sharpen what that expansion should pre-register.
