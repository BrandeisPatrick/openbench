# exp-01 — Pass@k boundary test: does distillation expand capability, or does the new generation only sharpen?

Status: proposed. Cost: expansion budget. Depends on: harder-task expansion, host-matched Kimi runs, token caps.

## Claim tested

- Kimi K3 ([2607.24653](https://arxiv.org/abs/2607.24653)): nine in-house
  teachers (3 domains × 3 effort levels) distilled into one model.
- DeepSeek V4 ([2606.19348](https://arxiv.org/abs/2606.19348)): domain
  specialists trained SFT+GRPO, then on-policy distillation from 10+ teachers.
- Contrast lineage: OpenAI o3 → gpt-5.5, no public specialist-distillation
  claim; treated as the RL-dominant link.

## Protocol source

limit-of-RLVR ([Yue et al. 2025](https://limit-of-rlvr.github.io/)): repeated
sampling, pass@k curves for k = 1…K, compared between a base and its
RL-trained version. Findings adopted as predictions: RLVR raises pass@1 but
"as k increases to the tens or hundreds, base models consistently catch up",
and "all reasoning paths in the RLVR model are already present in the base";
whereas "distillation can genuinely introduce new knowledge… distilled models
often exhibit an expanded scope of reasoning capability".

Adaptation: we have no base-model access, so the comparison is between
consecutive generations. The question becomes: does the newer generation's
advantage persist at large k (expansion) or vanish (sharpening)?

## Design

- Tasks: the expansion set, selected by a rule fixed before any run —
  candidates in `datasets/tasks/` that pass `openbench golden-gate` on fresh
  images, carry a SWE-bench Verified difficulty label of 15 min–1 h or 1–4 h,
  are not among the current four, at most three per repository; target 16–20.
  No pilot-based selection. Boundary analysis is pre-specified on the subset
  where the older generation's pass@1 is strictly between 0 and 1.
- Models and links: k2.6 → k3 (distillation link, both via one host);
  v3.2 → v4-pro (distillation link; host-crossing, labelled); o3 → gpt-5.5
  (RL link) on a subset if budget allows.
- Repeats: K = 16 per model per task (K = 32 on a 6-task subset if budget).
- Caps: token-based, identical across arms; provider-default sampling.

## Measures (to be implemented in `analysis/passk.py` before results)

- pass@k, unbiased estimator: 1 − C(n−c, k)/C(n, k) for n samples, c solved.
- Curve per model; gap(k) = pass@k(new) − pass@k(old) at k ∈ {1, 4, 16, (32)}.
- Coverage: tasks solved at least once by each model.
- Task-clustered, task-paired interval on each gap.

## Predictions

- Distillation links (k2.6→k3, v3.2→v4): gap(16) remains ≥ 0.10 with the
  interval excluding zero — boundary expansion.
- RL link (o3→gpt-5.5): gap(1) ≥ 0.10 but gap(16) < 0.05 — sharpening.
- Null: all gaps close by k = 16 (every generation's gain is sharpening on
  this task class, and the distillation claims add no reachable capability).

## Decision rule (fixed)

"Expansion" iff gap(16) ≥ 0.10 and interval excludes 0. "Sharpening" iff
gap(1) ≥ 0.10 and gap(16) < 0.05. Otherwise "indeterminate at this K".

## Cost tiers

| tier | runs | estimate |
|---|---|---|
| minimal: Kimi link only, 12 tasks × K=16 × 2 models | 384 | $150–250 |
| standard: + DeepSeek link, 16 tasks | ~1,000 | $400–600 |
| full: + OpenAI link on 6 tasks | +192 | +$200–400 |

## Caveats

SWE-bench Verified is public; contamination affects both generations of a
lineage and does not change the within-lineage expansion/sharpening reading,
but gold-identity rates are reported as a covariate. Saturated tasks are
uninformative by construction and are reported but excluded from the boundary
statistic per the pre-specified rule.
