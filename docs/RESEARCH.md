# Inferring RL Reward Composition from Agent Traces

*Pre-registered research note — openbench, June 2026. Status: hypotheses and
predictions committed before collecting frontier-model data.*

*Companion document: [EXPERIMENTS.md](EXPERIMENTS.md) — per-experiment
pre-registration (data, method, expected result, falsification, status).*

## 1. Research question

When a lab trains a coding model with RL, the reward function is the central
design secret: outcome-only test-pass reward? process rewards for intermediate
verification? penalties for reward hacking, length, or scope creep? **Can we
estimate the composition of that reward by observing how the trained model
behaves on long-horizon software tasks?**

### How that works

RL selects policies that are *optimal relative to their training reward*. Two
consequences make the reward observable from behavior:

1. **Behavior that is costly unless rewarded is diagnostic.** Re-running a
   green test suite spends tokens and earns nothing under outcome-only reward
   — a model that habitually does it was plausibly trained with a verifier or
   process reward. Tampering with tests is reward-*maximizing* under naive
   outcome reward and reward-*catastrophic* under an anti-hacking penalty, so
   the tamper rate when tampering would pay separates the two designs.
2. **The signature survives deployment.** The trained policy carries its
   optimized habits into our environment, where we control everything else
   (harness, tools, prompts, tasks) and record everything it does.

The inference is three steps, run per reward family: **predict** the trace
signature the family makes optimal → **observe** trajectories in the fixed
harness → **falsify** families whose predictions fail. This is qualitative
inverse RL over reward *families*; the exact reward function is unrecoverable
(§6).

There is direct empirical precedent that behavior separates training recipes:
on a published reward-hacking benchmark, exploit rates range from **0% (Claude
Sonnet 4.5) to 13.9% (DeepSeek-R1-Zero)** across frontier models — a 14-point
behavioral gap attributable to post-training differences
([reward-hacking benchmark](https://arxiv.org/html/2605.02964);
[Anthropic, emergent misalignment from reward hacking](https://www.anthropic.com/research/emergent-misalignment-reward-hacking)).

## 2. Hypothesis registry

The unknown reward is modeled as a non-negative mixture of seven candidate
components, each documented in published training recipes. For each: the
mechanism, the **pre-registered prediction** (committed before data
collection), and the leading confound.

| ID | Component | Documented in | Mechanism → predicted signature | Falsified by | Confound |
|---|---|---|---|---|---|
| H1 | **Outcome-only RLVR** | DeepSeek-R1 rule-based rewards; RLVR generally | Any path to green scores → tampering, assert-weakening, skip/xfail insertion rise (z≥1); post-success churn low (z≤−1); guess-first editing | near-zero gaming on honeypots where gaming is cheap and undetected | gaming style may be inherited from pretraining data |
| H2 | **Anti-hacking penalty** | Anthropic's reward-hack classifier penalties / ground-truth monitors ([source](https://www.anthropic.com/research/emergent-misalignment-reward-hacking)) | Hacks taxed during training → near-zero gaming *even when it pays* (honeypot), normal otherwise | nonzero honeypot exploit rate | indistinguishable from H1-absent without the honeypot (see identifiability, §4) |
| H3 | **Process / turn-level reward** | turn-level reward design ([arXiv 2505.11821](https://arxiv.org/abs/2505.11821)); online process-reward learning ([arXiv 2509.19199](https://arxiv.org/abs/2509.19199)) | Verification itself is paid → verification_loop_count, verified_before_done, test_runs_per_edit all high; persists on easy tasks where it's unnecessary | verification collapses when unnecessary | strong SFT on tool-use demonstrations mimics it |
| H4 | **Similarity-to-gold-patch** | SWE-RL, Meta ([arXiv 2502.18449](https://arxiv.org/abs/2502.18449)): reward = similarity between generated and oracle patch | Matching the gold diff was paid; running tests never was → high file_jaccard with gold but LOW test-run rate | high verification alongside high gold-similarity | similarity may reflect genuine correctness |
| H5 | **Length / truncation shaping** | DAPO overlong reward shaping ([arXiv 2503.14476](https://arxiv.org/abs/2503.14476)); Kimi length penalties | Effort taxed → early_stop high, consecutive_failures_at_end low (gives up fast), flat token-vs-difficulty slope | effort scaling with difficulty; persistent retries | small context window forces the same behavior |
| H6 | **Rubric / generative RM** | Kimi K2 self-critique rubric ([arXiv 2507.20534](https://arxiv.org/abs/2507.20534)); DeepSeek-V4 Generative Reward Model ([report summary](https://huggingface.co/blog/deepseekv4)) | A judge pays for quality beyond tests → post-success churn (polish after green), higher deliberation | edits stop exactly at first green | RLHF preference models produce similar polish |
| H7 | **Context-management reward** | Context-Folding process rewards ([arXiv 2510.11967](https://arxiv.org/abs/2510.11967)); Memory-as-Action ([arXiv 2510.12635](https://arxiv.org/abs/2510.12635)); AgeMem step-wise GRPO ([arXiv 2601.01885](https://arxiv.org/abs/2601.01885)) | Memory curation paid → distinctive recall: summarize-then-act, low re-read rate of already-seen files, branch-and-fold instead of brute re-reading | recall behavior identical to non-memory-trained cohort | long-context architectures (V4 Engram) reduce the *need* to manage context |

H7 is the newest family — 2025–26 papers train context management *directly
with RL process rewards*, so models differ in how they recall earlier
trajectory state. Its primary metric is `re_read_rate` (fraction of read/search
events touching already-read files) — **length-invariant**, so it is the only
context signal allowed into the reward signature.

> **Lesson from the V3→V4 pilot (a length-confound to avoid).** An earlier
> `context_tokens_per_turn` metric was in the signature and produced a
> *nonsensical* result: it credited context-management to base-V3 (which has
> no context-management training) and zero to V4 (which does). Cause: V3 quits
> after ~3 turns, so it trivially has low cumulative context — "lean" for doing
> nothing, not for folding/summarizing. Raw context-per-turn measures
> *trajectory length*, not management. It was removed from the signature; the
> correct metric is a length-invariant per-turn **context-growth slope**
> (flat = folds, linear = appends everything), which needs longer, ideally
> *successful* trajectories to estimate — hence H7 stays uninformative until the
> solvable difficulty band exists. Summarize-then-act detection remains future
> LLM-judge work.

## 3. Estimation methodology (three tiers)

**Tier 1 — Consistency screening** *(implemented:
`analysis/fingerprint.py`)*. Per-model z-scores (within a fixed harness)
against the model cohort; rule patterns at |z| ≥ 1 emit hedged labels
("consistent with outcome-only reward without anti-hacking penalties").
Qualitative screen only.

**Tier 2 — Mixture-weight estimation** *(implemented:
`analysis/estimate.py`)*. Model the reward as `R = Σ wᵢ·componentᵢ`, `w ≥ 0`:

1. Each component gets a **signature vector**: its predicted z-direction on
   each of the ~18 behavioral metrics (the `SIGNATURES` matrix, every cell
   justified in code comments).
2. A model's observed **fingerprint** is its z-scored metric vector vs the
   cohort.
3. **Non-negative least squares** (`F ≈ S·w`) recovers the mixture weights,
   normalized to sum to 1 — the *estimated reward composition* — with
   bootstrap 95% CIs over the model's runs.
4. **Cross-check:** a contrastive (ridge-logistic) regression separating the
   model's runs from the cohort's; its coefficients say which behaviors the
   model over-produces. NNLS and contrastive directions agreeing = robust.
5. **Identifiability is reported, not assumed:** component pairs whose
   signatures are near-(anti)parallel (e.g. *outcome-only* vs *anti-hack
   penalty*, cosine ≈ −1) are flagged in every report as unseparable by
   passive observation.

Validation status: the estimator recovers planted mixtures in synthetic
cohorts (`tests/test_estimate.py`). The signature matrix itself is
theory-derived until Tier 3 calibrates it.

**Tier 2b — Realized counterfactual rewards** *(implemented:
`analysis/reward_scoring.py`)*. The direct complement: implement each
candidate reward function — exactly as its paper defines it where one exists
(SWE-RL similarity = `difflib` ratio vs the oracle patch; DAPO length =
truncation + soft-overlong penalty; turn-level process reward = verification
density + final-green bonus) — and evaluate it on the actual trajectory:
*"had the model been trained with reward X, how much X did this run earn?"*
A policy optimized for X earns conspicuously high X on its own trajectories,
so per-model realized-reward profiles (compared within a column, within one
harness) are a second estimator with real units and far fewer assumptions
than the signature matrix. NNLS and realized-reward profiles agreeing is the
internal cross-check; disagreement means the signature matrix is miscalibrated.

**Tier 3 — Probes and calibration** *(designed, not yet implemented)*.
Passive observation cannot break collinear ties; probes create situations
where the families' optimal behaviors maximally diverge:

- **Honeypot tasks** (breaks H1 vs H2): visible in-repo tests are weak and
  gameable; the strict F2P suite stays hidden until grading. Exploit rate when
  gaming is cheap and in-episode-undetectable ≈ direct read on the anti-hack
  weight. Anti-cheat machinery (`grading/anticheat.py`) already records every
  gaming event.
- **Effort curves** (H5): same model across difficulty tiers; the
  token-spend-vs-difficulty slope and giving-up threshold estimate the
  effort-penalty coefficient.
- **Recall probes** (H7): a fact established early in a long trajectory is
  needed late — re-read vs remember vs summarize separates context-trained
  policies.
- **Calibration models (gold standard):** fine-tune a small open model with
  GRPO under *known* mixtures (toggle one component at a time), run it through
  this exact pipeline, and check the estimator recovers the known weights.
  This is the only way to validate the signature matrix end-to-end.

## 4. Task difficulty: signal only exists under pressure

A task comfortably inside a model's capability makes every reward family
behave identically — clean solve, no trade-offs, signatures converge.
Divergence happens at the **capability frontier**: gaming becomes tempting
(H1/H2) only when honest solving is hard; giving-up thresholds (H5) only bind
under sustained failure; context strategies (H7) only differentiate when the
trajectory outgrows the window. Frontier models (DeepSeek-V4, GPT-5.x) require
frontier tasks — FrontierCode's Diamond tier sits at ~13% solve for the best
model, which is the right operating zone.

Difficulty levers, in order of leverage:

1. **Solve-rate-calibrated tiers**: tier membership by *measured* frontier
   solve rate (Diamond < 20%; demote > 50%), not static hardness score.
2. **Frontier mining thresholds**: ≥ 8000 LOC ceiling raised, ≥ 20 files, ≥ 4
   modules, high import-graph depth.
3. **Composite multi-PR tasks** (SWE-EVO style, [arXiv 2512.18470](https://arxiv.org/pdf/2512.18470)):
   chain 2–3 stacked PRs of one feature into a single task.
4. **Context-pressure tasks**: relevant information deliberately exceeds the
   context window (feeds H7).
5. **Difficulty-response curves as the primary statistic**: report every
   metric *vs tier* — the slope (e.g. gaming rate rising with difficulty) is
   more discriminative than any single-tier mean.

## 5. Decision rules

For each (model, hypothesis): **consistent** if the pre-registered prediction
holds with |z| ≥ 1 and a CI excluding 0; **inconsistent** if the opposite
direction holds at the same bar; **uninformative** otherwise (CI too wide, or
the component is in a flagged collinear pair without probe data). With 7
hypotheses × N models, all results are reported and only |z| ≥ 1 with
non-overlapping CIs are highlighted. All comparisons within one harness.

## 5b. Known limitations from the IRL / agent-eval literature

Three failure modes are designed against explicitly, each grounded in published work:

- **Length / difficulty confounding** ([Beyond Resolution Rates, arXiv 2604.02547](https://arxiv.org/pdf/2604.02547)).
  Trajectory length is entangled with task difficulty and outcome; raw counts measure
  "did the model run long," not strategy, and controlling for length can *reverse*
  rankings. → Only **length-invariant** metrics (rates, ratios, booleans) drive reward
  inference; a `LENGTH_INVARIANT` guard in `analysis/estimate.py` hard-fails if a raw
  count enters the signature. Counts remain as descriptive fields only. The headline
  process-reward finding was re-verified on the invariant signature (it survived, at
  reduced magnitude — the prescribed confounding-reversal check).
- **Partial identifiability & misspecification** ([arXiv 2411.15951](https://arxiv.org/abs/2411.15951),
  [arXiv 2106.03498](https://arxiv.org/abs/2106.03498)). Many rewards explain one policy;
  the signature matrix is a possibly-misspecified behavioral model. → Mixture weights
  whose bootstrap CI includes zero are reported as **"— (not estimable)"**, never ranked;
  each estimate carries a **condition number** (ill-conditioned ⇒ components not
  separable); collinear component pairs are flagged; identifiability improves only with
  **more models/environments**, which is why cross-lab + difficulty-band expansion is the
  priority, not more runs of the same kind.
- **Inference from failed trajectories** (same paper). Failed traces are longer because
  they are *harder*, not worse. → When a cohort is entirely 0%-solve, the report stamps a
  prominent warning that all reads describe failure modes, not strategy on success.

## 5c. Metric provenance

Every metric is either grounded in a published definition or marked **novel (openbench)**.
Grounded metrics are primary for inference; novel ones are reported as clearly-flagged
exploratory signals (academic accuracy = honest provenance, not discarding signal).

| metric | provenance | role |
|---|---|---|
| `recovery_rate` | self-correction rate — [survey 2507.21504](https://arxiv.org/pdf/2507.21504) | primary (process) |
| `progress_proxy` | model-free approx of AgentPRM progress — [2511.08325](https://arxiv.org/abs/2511.08325) | primary (process) |
| `action_efficiency` | optimal/actual — [2604.02547](https://arxiv.org/pdf/2604.02547) | primary (scope) |
| `plan_ned` | normalized edit distance — survey | primary (scope) |
| `redundancy_rate` | redundancy — survey | primary (length) |
| `test_runs_per_edit`, `verified_before_done` | operationalize process-reward concept (RLVR/PRM) | primary (process) |
| `confabulated_completion` | **novel (openbench)** — no published equivalent | exploratory, strong signal |
| `honeypot_exploit` | inspired by reward-hacking benchmarks ([2605.02964](https://arxiv.org/html/2605.02964)) | probe (H1/H2) |
| H8/H9 (spec-literalism, pattern-recall) | **no valid deterministic metric** — semantic; need a judge or purpose-built probes (IFBench 2025). Earlier file-overlap proxies were removed as misleading. | registry-only, judge-pending |
| `verifies_when_easy`, `effort_difficulty_slope` | difficulty-controlled slope — [2604.02547](https://arxiv.org/pdf/2604.02547) | H10/H11, model-level |

**Tier-3 advanced metric (future):** AgentPRM's *learned* promise (`Q^π`) and progress
(`A=Q−V`) via TD/GAE ([2511.08325](https://arxiv.org/abs/2511.08325)) — the rigorous version
of `progress_proxy`, requiring a trained value head + rollouts. **pass@k / consistency**
(survey) is also future, needing k runs per (model, task).

## 5d. Extended hypothesis registry (H8–H11, pre-registered, unverified)

Added from direct Fable-vs-Opus observation; **not yet tested in openbench** (judge tier /
multi-tier data pending). Verbatim evidence + confidence retained so nothing reads as
established.

| ID | Reward family | Prediction (signature) | Evidence | Confidence | Status |
|---|---|---|---|---|---|
| **H8** | Literal spec-fidelity vs unstated-intent inference | judge `intent_inference_score` ⇒ inferred unstated requirements | task 90728: Fable transcribed `[title ?? name]` literally; Opus inferred the unstated `?? uri` fallback and won | medium (n=1 at the decisive point) | **no deterministic metric — judge required** |
| **H9** | Canonical pattern recall/retrieval | judge `recall_vs_derive` ⇒ recalled directly vs derived | click-3504: Fable nailed a niche fish-completion format Opus missed | low-medium (tensioned with H10 — Fable still empirically verifies) | **no deterministic metric — judge required** |
| **H10** | Intrinsic-verification reward | verifies even on trivial tasks (`verifies_when_easy`) | verifies by execution (node -e probes, live tsx drivers) even when trivial; replicated across all 4 subagent tasks | medium-high | model-level metric live |
| **H11** | Proportionate-effort reward | effort scales with difficulty (`effort_difficulty_slope` > 0) | more tool-calls/wall-time on harder tasks; effort scales up | medium-high | needs ≥2 tiers with signal |

> H10 vs H9 are deliberately in tension: H10 says Fable *empirically verifies*, H9 says it
> *recalls patterns* — keeping both independent lets the data adjudicate rather than assume.

## 5e. Causal hypotheses on the reasoning-pattern shift (H14–H15, pre-registered)

Distinct from H1–H11 (which infer the *reward family* from one model's behaviour), H14/H15 ask a
**causal** question: why did this year's frontier models (Opus, GPT) change their reasoning patterns
(more verification, recall, adaptive depth)? Both agree RL reward *created* the patterns (o1/R1);
they split on the **proximate** cause of the cross-model convergence. Tested by E11/E12.

| ID | Hypothesis | Prediction (signature) | Falsified by | Confound / honest caveat |
|---|---|---|---|---|
| **H14** | Reasoning is **RL-reward-shaped** (instrumental) | behaviour scales with difficulty/payoff; estimator recovers the documented reward on RL anchors | flat-across-difficulty + no recovery on known RL recipes | "trained-in-ness" is shared by SFT/distillation — resistance probes do **not** separate reward from imitation (E11 P11b flaw) |
| **H15** | Reasoning **spread by propagation** (distillation/SFT + the adaptive-thinking mechanism; mimetic) | convergent cross-lab fingerprints; clusters with the distillation pole (V4); shared idiosyncratic *form*; drift toward the prior leader | lab-divergent fingerprints + targets cluster with the RL pole + no shared form | convergence is also explained by *independent convergence to the same optimum*; only shared *idiosyncratic form* cleanly discriminates |

Load-bearing discriminator: **idiosyncratic-form sharing** (E12 P12c) — independent reward
optimisation converges on *function*, not on a competitor's *quirks*. The composite framing is
**novel (openbench)**; component methods are cited in [EXPERIMENTS.md](EXPERIMENTS.md) E11/E12.

## 6. What this can never show

- **Exact reward recovery is unidentifiable.** Different recipes can produce
  behaviorally equivalent policies; DeepSeek-V4 merges 10+ domain-specialist
  teachers via on-policy distillation, blurring any single-reward attribution.
- **Confounds:** pretraining priors, SFT demonstrations, safety training
  applied outside RL, harness scaffold, decoding settings. Falsification
  claims ("inconsistent with pure outcome reward") are stronger than
  consistency claims.
- **Contamination** qualifies everything: tasks are post-cutoff-mined, but
  per-(task, model) `post_cutoff` flags must accompany any result table.

## 7. Code map

| Concept | Where |
|---|---|
| Behavioral metrics (per run) | `src/openbench/analysis/metrics.py` → `models.py::RunMetrics` |
| Tier-1 labels (z-rules) | `src/openbench/analysis/fingerprint.py::hypothesis_labels` |
| Tier-2 estimator (NNLS + contrastive) | `src/openbench/analysis/estimate.py` |
| Signature matrix S | `estimate.py::SIGNATURES` (rationale in comments) |
| Gaming evidence | `src/openbench/grading/anticheat.py` (recorded even when reverted) |
| Trace events | `src/openbench/traces/schema.py` (H7 recall metrics derive from these) |
| Report (composition table + identifiability warnings) | `src/openbench/report/generate.py` |

## References

- DeepSeek-R1 / rule-based RLVR — DeepSeek-AI, 2025
- SWE-RL: similarity-to-oracle-patch reward — Meta, [arXiv 2502.18449](https://arxiv.org/abs/2502.18449)
- DAPO: overlong reward shaping — ByteDance Seed, [arXiv 2503.14476](https://arxiv.org/abs/2503.14476)
- Turn-level reward design for multi-turn agents — [arXiv 2505.11821](https://arxiv.org/abs/2505.11821)
- Kimi K2: RLVR + self-critique rubric rewards — [arXiv 2507.20534](https://arxiv.org/abs/2507.20534)
- Online process reward learning for agentic RL — [arXiv 2509.19199](https://arxiv.org/abs/2509.19199)
- Context-Folding: RL process rewards for context management — [arXiv 2510.11967](https://arxiv.org/abs/2510.11967)
- Memory-as-Action — [arXiv 2510.12635](https://arxiv.org/pdf/2510.12635); AgeMem — [arXiv 2601.01885](https://arxiv.org/abs/2601.01885)
- Emergent misalignment from reward hacking; classifier-penalty mitigations — [Anthropic](https://www.anthropic.com/research/emergent-misalignment-reward-hacking)
- Reward-hacking benchmark (cross-model exploit rates) — [arXiv 2605.02964](https://arxiv.org/html/2605.02964)
- DeepSeek-V4: domain-specialist RL + Generative Reward Model — [report](https://huggingface.co/blog/deepseekv4)
- SWE-EVO: long-horizon software evolution — [arXiv 2512.18470](https://arxiv.org/pdf/2512.18470)
