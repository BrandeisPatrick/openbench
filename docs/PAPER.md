# Reward Fingerprints: Inferring the Composition of RL Training Rewards from Black-Box Agent Behavior

*Draft v0.1 — 2026-06-12. Short paper; results from openbench (this repository).*

## Abstract

The reward function used to RL-train a coding model is a lab's central design secret,
yet it leaves systematic traces in how the deployed model behaves. We present
**openbench**, an instrument that replays human-validated software tasks (SWE-bench
Verified) through a fixed minimal agent harness, computes 24 length-invariant
behavioral metrics per trajectory, and decomposes each model's z-scored fingerprint
into a non-negative mixture over seven candidate reward families via NNLS with
bootstrap confidence gates. Three findings. (1) *Within-lab differential:* DeepSeek
V4-flash reads as process/verifier-shaped (0.73, the only estimate stable across every
cohort composition) while V4-pro reads as rubric/judge-shaped — matching the published
recipe, including the fact that flash and pro are separate training runs, which the
instrument was never told. (2) *Blind cross-lab prediction:* with predictions
pre-registered before reading any technical report, the instrument substantially
matched 3 of 3 published recipes (1 hit, 2 hit/partials) for Kimi K2, GLM-4.6, and
Qwen3-Coder — including predicting, from 166 broken hidden tests, that Qwen's reward
pays for target-test completion without a regression penalty, which its report
confirms by omission. (3) *A measured negative:* long-range context recall, initially
hypothesized as a signature of million-token RL training, appears at similar rates
across all modern agentic-RL models — a hypothesis revised by the data. We release
the instrument, all trajectories, and a pre-registration log in which every prediction
precedes its evidence.

## 1. Introduction

When a lab posts a new coding model, it publishes weights or an API, benchmarks, and
sometimes a high-level training recipe — but never the reward function. Yet the reward
is causally upstream of the behaviors users experience: whether the model verifies its
work, whether it games tests, whether it persists or quits, whether it stays in scope.
We ask: **how much of the training reward's composition can be estimated from
deployed behavior alone?**

This is an inverse-RL question under the worst conditions: black-box policy, one
environment, no reward samples. The IRL literature says full recovery is impossible —
rewards are only partially identifiable from behavior [2106.03498, 2411.15951]. Our
contribution is an instrument that extracts what *is* identifiable and is honest about
the rest:

- a fixed minimal harness (one-command-per-turn ReAct over network-isolated
  containers) replaying SWE-bench Verified tasks, graded by hidden FAIL_TO_PASS /
  PASS_TO_PASS suites in clean-room containers with an anti-cheat scan;
- 24 **length-invariant** behavioral metrics (rates/ratios/booleans only — raw counts
  confound with trajectory length and task difficulty [2604.02547]), each with
  published provenance or explicitly marked novel;
- a mixture decomposition `F ≈ S·w` (NNLS) over seven reward families, gated by
  bootstrap CIs (CI∋0 ⇒ "not estimable", never a rankable number), redundancy pruning,
  and condition-number diagnostics;
- a **pre-registration protocol**: every hypothesis and prediction is committed in
  writing before the evidence that tests it (docs/EXPERIMENTS.md).

## 2. Related work

**Reasoning-pattern selection.** RL primarily reshapes *which* reasoning patterns a
model selects rather than improving patterns' intrinsic success rates [2506.04695];
GPSO trains selection explicitly via pattern-forcing prompt suffixes [2601.07238]. We
use the published *method* (selection-frequency vs intrinsic-success analysis) and,
inverted, GPSO's forcing mechanism as a planned causal probe; no published pattern
taxonomy exists for agentic coding, so ours is adapted with per-pattern provenance.

**Credit assignment for long-horizon agents.** Surveyed in [2604.09459]; SALT derives
step-level credit from shared-vs-divergent steps across k rollouts [2510.20022];
AgentPRM scores actions by progress toward goal [2511.08325]. Our `recovery_rate`,
`progress_proxy`, and per-turn progress curves are deterministic, model-free proxies
of these signals, labeled as such.

**Reward identifiability.** Many rewards explain one policy [2106.03498]; behavioral-
model misspecification compounds this [2411.15951]. We respond with noise-floor
gates, collinearity warnings (e.g., outcome-only vs anti-hack signatures are
near-antiparallel, cos −0.81 — separable only by intervention), and probe designs.

**Agent evaluation pitfalls.** Resolution rates hide strategy; trajectory length
confounds difficulty and outcome [2604.02547]. Our signature admits only
length-invariant metrics, enforced by a hard guard with regression tests.

## 3. Method

### 3.1 Tasks and harness

Tasks are imported 1:1 from SWE-bench Verified (human-annotated solvable instances).
The harness (`mini-swe`) is deliberately minimal and identical for every model: a
system prompt demanding exactly one shell command per turn in a fenced block, a
network-isolated Docker container per run, no tools beyond the shell, fixed turn/cost
caps. Minimality is a measurement choice: a richer scaffold would inject its own
behavioral priors. The cost is a depressed solve rate relative to production scaffolds
(reported solve rates here are not capability claims), and a scaffold-sensitivity
confound for chat-era models, which we state wherever it binds.

### 3.2 Grading

Each run is graded in a fresh container (never the agent's — root access for 80 turns
makes the agent's environment untrusted): apply agent diff to pristine base, apply
hidden test patch, rebuild, run FAIL_TO_PASS then PASS_TO_PASS, then an anti-cheat
scan (test-file tampering, assert weakening, skip/xfail insertion). Crashed runs
(provider failures) never enter behavioral pools (regression-tested).

### 3.3 Metrics

24 length-invariant metrics per run, spanning verification discipline
(`verified_before_done`, `test_runs_per_edit`, `recovery_rate` [2507.21504],
`progress_proxy` [2511.08325]), scope vs the gold patch (`file_jaccard`, `plan_ned`,
`out_of_scope_ratio`, `action_efficiency` [2604.02547]), effort shaping (`early_stop`,
`gave_up_failing`, `thinking_fraction`), gaming (`test_tampering`, `assert_weakened`,
honeypot/impossible probe outcomes, `confabulated_completion` — novel), and memory
(`re_read_rate`; `long_range_recall_rate` / `recall_distance_norm` — novel, H13:
reasoning-turn references to artifacts dormant >10 turns, prompt-excluded,
re-read-resets). Raw counts are retained as descriptive fields but excluded from
inference by a hard guard.

### 3.4 Estimator

Per model: average each metric over runs, z-score against cohort model-means, prune
zero-variance and |r|≥0.85-redundant metrics, then solve non-negative least squares
`F ≈ S·w` where S is a theory-derived signature matrix over seven components
(outcome-only, anti-hack penalty, process/verifier, similarity-to-gold, length
penalty, rubric/GRM, context management). Bootstrap (B=500) CIs over run resampling;
a component is reported only when its CI excludes zero. Condition number of the
active submatrix and collinear component pairs are reported with every estimate.
Weights are compositions (sum to 1): read down a model, never across models.

### 3.5 Pre-registration

Every hypothesis (H1–H13) and experiment (E1–E9) is registered with expected results
and falsification conditions before evidence collection; predictions in the blind
cross-lab test were committed to the log before any technical report was read, with
prior contamination disclosed per model (docs/EXPERIMENTS.md).

## 4. Results

### 4.1 Within-lab differential (DeepSeek)

On the pooled cohort (n≈11–12 runs/model):

| Model | Estimable composition | Behavioral basis |
|---|---|---|
| V4-flash | process_verifier **0.73** [0.12, 0.83] | verified-before-done 0.90, recovery 0.91, test:edit 3.4 |
| V4-pro | rubric_grm 0.70 [0.03, 0.78] (cohort-sensitive) | post-green polish, long-CoT label, early-climbing progress curve |
| V3-base | outcome_only ~0.15–0.19 (+absence-of-action artifacts) | zero test runs, 100% confabulated completion |

Flash's process_verifier is the only estimate stable under every cohort composition we
tried; it is the headline within-lab result. Consistency with open information: V4's
published recipe combines verifier-in-the-loop RL for code with a generative
rubric-based reward model for hard-to-verify tasks, and — crucially — flash is a
separate training run, not a distillation of pro. Divergent fingerprints for the two
were measured before that fact was checked. V4's post-training also merges
independently-RL-trained domain specialists, meaning the deployed model literally is a
mixture of differently-rewarded policies — the estimator's model class matches the
construction. (Partial circularity disclosed: rubric-GRM entered our component list
partly because such training is publicly known; the *differential* flash≠pro
assignment did not.)

### 4.2 A measured negative: long-context recall (H13)

We hypothesized (user-originated, pre-registered) that V4's million-token RL rewards
recalling earlier context inside reasoning. Deterministic measurement (string-matched
artifact references, dormancy window W=10 turns, prompt-excluded, re-read-resets):
V4-pro recalls dormant context in 10.2% of reasoning turns vs flash 5.0% and V3-base
0% — ordering as predicted. But the cross-lab cohort falsified the *attribution*:
Kimi K2 (256k context) and GLM-4.6 (200k) recall at 8.6%/8.4%, near-pro rates, and
GLM shows the longest recall-distance tail. Long-range recall is a property of modern
agentic-RL models generally, not of million-token training. The "recall *instead of*
re-read" clause also failed: all moderns recall *and* re-read (re-read rates ~0.5–0.7).
The hypothesis log records both revisions.

### 4.3 Blind cross-lab prediction (E8)

Protocol: run Kimi K2, GLM-4.6, Qwen3-Coder (4 tasks each, $2 total), commit predicted
recipes from fingerprints alone, then read the reports and score.

| Model | Blind prediction (driving evidence) | Published recipe | Verdict |
|---|---|---|---|
| Kimi K2 | outcome-RL + self-judging rubric; weak process shaping (surgical diffs ratio 20×; verified-before-done 0.00; recovery 0.00) | binary verifiable-rewards gym + self-critique rubric [2507.20534] | HIT (prior disclosed) |
| GLM-4.6 | outcome agentic RL + iterative-repair emphasis (recovery 1.00; gave-up-failing 0.00; 2/4 solved) | dense multi-turn rewards "over consecutive rounds" on auto-verified agents [2508.06471] | HIT/partial |
| Qwen3-Coder | execution-feedback test RL on synthetic tasks, **no regression penalty** (0/4 solved; 166 hidden tests broken; best gold-file targeting; 1 protected-test edit) | execution-driven unit-test RL on synthetic tasks; anti-hack = termination/format penalties only [2603.00729] | HIT/partial (key clause by omission) |

Meets the pre-registered bar (≥2 of 3 substantially match). Two observations beyond
the scorecard. First, at n=4 the *not-estimable* point masses already point at true
recipe components (Kimi's largest grey weight is rubric-GRM — its actual recipe;
Qwen's is length-penalty — its actual unfinished-trajectory penalty): direction
arrives before statistical power. Second, the misses localize: the rubric column
needs a sharper positive signature, and "anti-hack" conflates two independent axes
(scope-damage vs format/termination gaming) that Qwen's behavior cleanly separates.

### 4.4 Frontier cohort (in progress)

Opus 4.8, Fable 5, GPT-5.5, GPT-5, GPT-4.1 are running under the same blind protocol
(E9); results will be added with predictions committed before reading any vendor
documentation.

## 5. Limitations

**Partial identifiability is fundamental.** Several mixtures explain one behavior;
our CIs and collinearity warnings bound but do not remove this. Components whose
signatures are near-antiparallel (outcome-only vs anti-hack, cos −0.81) require
intervention probes (planned: GPSO-inverted forced-pattern probes), not more passive
data. **Absence-of-action artifacts:** a model that barely acts earns spurious credit
on penalty components (observed on V3-base; flagged, not yet fixed). **Small n.**
4–12 runs/model; estimates are directional. **One harness, one task family.**
Fingerprints are comparable only within this harness; sympy-only tasks narrow the
behavioral surface. **Prior contamination.** The analyst knows coarse facts about
major labs' recipes; blind predictions disclose priors per model and the strongest
hits are on the *differentials* no prior encoded. **Failure-dominated data.** Most
trajectories fail; behavioral reads partly describe failure modes (mitigated since
the cohort now contains genuine solves). **Judge-dependent hypotheses (H8, H9, H12)
remain unmeasured** — stubs are registered, not scored.

## 6. Conclusion

A fixed minimal harness, length-invariant behavioral metrics, and an
honesty-gated mixture decomposition recover a useful, partially-validated signal
about how deployed coding models were rewarded — enough to separate two training runs
within one lab and to predict, blind, distinguishing features of three labs'
published recipes, including a reward's *missing* term (Qwen's absent regression
penalty) from its behavioral consequences. The instrument's failures are as
informative as its hits and are localized enough to fix. Next: causal probe tiers
(forced-pattern resistance as a direct test of intrinsic-verification reward),
k-rollout reliability and divergent-step credit, judge-based pattern fingerprints,
and the ground-truth rung — models trained with known reward mixtures.

## References

- [2106.03498] Identifiability in Inverse Reinforcement Learning. https://arxiv.org/abs/2106.03498
- [2411.15951] Reward identifiability under behavioral-model misspecification. https://arxiv.org/abs/2411.15951
- [2503.01307] Gandhi et al., Cognitive Behaviors that Enable Self-Improving Reasoners. https://arxiv.org/abs/2503.01307
- [2505.09388] Qwen3 Technical Report. https://arxiv.org/abs/2505.09388
- [2506.04695] Chen, Li & Zou, Reshaping Reasoning in LLMs. https://arxiv.org/abs/2506.04695
- [2507.20534] Kimi K2: Open Agentic Intelligence. https://arxiv.org/abs/2507.20534
- [2507.21504] Survey: self-correction / trajectory metrics for LLM agents. https://arxiv.org/abs/2507.21504
- [2508.06471] GLM-4.5: Agentic, Reasoning, and Coding (ARC) Foundation Models. https://arxiv.org/abs/2508.06471
- [2510.20022] SALT: Step-level Advantage Assignment via Trajectory Graph. https://arxiv.org/abs/2510.20022
- [2511.08325] AgentPRM: process reward via progress estimation. https://arxiv.org/abs/2511.08325
- [2601.07238] Group Pattern Selection Optimization. https://arxiv.org/abs/2601.07238
- [2603.00729] Qwen3-Coder-Next Technical Report. https://arxiv.org/abs/2603.00729
- [2604.02547] Beyond Resolution Rates: length/difficulty confounds in agent evaluation. https://arxiv.org/abs/2604.02547
- [2604.09459] From Reasoning to Agentic: Credit Assignment in RL for LLMs (survey). https://arxiv.org/abs/2604.09459

## Reproducibility

All trajectories (raw API transcripts, normalized events, diffs, grades, metrics),
the DuckDB warehouse, figures, and the pre-registration log (EXPERIMENTS.md, with
timestamps ordering every prediction before its evidence) ship with the repository.
`openbench analyze && openbench report` regenerates every number and figure in this
paper from stored data, offline.
