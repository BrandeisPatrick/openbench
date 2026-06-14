# Experiment Pre-Registration

Each experiment is registered **before** its results exist: the data it uses, the exact
measurement, the expected result, and what would falsify it. Status is updated as results
land. Hypotheses (H1–H13) are defined in [RESEARCH.md](RESEARCH.md); this file documents
the experiments that test them.

**Reading guide.** "Live" = result exists from current data. "Ready" = code path exists or
is approved in plan; needs only analysis or new runs. "Pending" = blocked on a named
prerequisite (judge tier, solvable task band).

---

## Experiment data

All experiments below run on the same instrument and share this cohort unless noted.

| Item | Value |
|---|---|
| Task set | 7 tasks imported from SWE-bench Verified (human-annotated solvable; sympy, others) |
| Harness | `mini-swe` — bare one-command-per-turn ReAct loop, network-isolated Docker container per run |
| Models | `deepseek-v4-flash` (n=10), `deepseek-v4-pro` (n=9), `deepseek-chat-v3-0324` base via OpenRouter (n=9), golden-patch control (n=2) |
| Total runs | 28 (matrix of 2026-06-11/12) |
| Grading | FAIL_TO_PASS / PASS_TO_PASS replay in a fresh container; anti-cheat scan of the agent diff |
| Trace record | per-turn `thinking` + `assistant_msg` text, tool calls, parsed test results (`events.jsonl`, DuckDB) |
| Inference rule | only **length-invariant** metrics (rates/ratios/booleans) enter reward inference ([arXiv 2604.02547]); raw counts are descriptive only |

Known data limitations, stated up front:

- **Mostly failed trajectories.** Solve rate is near zero; reward reads reflect failure
  modes, not strategy on success ([arXiv 2604.02547]). Reports carry this banner.
- **Small cohorts.** n≈10 per model; z-scores across 3 models are directional, not
  conclusive.
- **Partial identifiability.** Many rewards explain one policy ([arXiv 2411.15951],
  [arXiv 2106.03498]); components whose bootstrap CI includes 0 render as "not estimable."

---

## E1 — Reward-mixture decomposition

**Question.** Which reward family best explains each model's behavior?

**Method.** Compute 24 length-invariant behavioral metrics per run; z-score within the
cohort; solve the non-negative least squares problem `F ≈ S·w` where `S` is the
theory-derived metric→component signature matrix (7 components, H1–H7). Bootstrap CIs;
a component is reported only if its CI excludes zero. Condition number and collinear
component pairs are reported with every estimate. Redundant metrics are pruned before
fitting (zero-variance dropped, |r| ≥ 0.85 pairs merged).

**Expected result (pre-registered).** RL-trained V4 loads on `process_verifier`
(verification is itself rewarded); base V3 loads on nothing or `outcome_only`.

**Result (2026-06-12) — live; updated after crash-run exclusion.**

| Model | Estimable composition (pooled cohort, n≈11–12) | Key caveat |
|---|---|---|
| v4-flash | `process_verifier` **0.73** [0.12, 0.83] | **stable across every cohort version** — the robust finding |
| v4-pro | `rubric_grm` 0.70 [0.03, 0.78] | cohort-sensitive (was unestimable on the SWE-bench-only subset) — directional only |
| v3-base | `anti_hack` 0.34 / `context_mgmt` 0.21 / `outcome_only` 0.15 | cohort-sensitive; anti_hack/context credit comes from *absence of action* (it neither games nor re-reads because it barely acts) — exactly the passive-observation failure E4 exists to break |

Cohort-sensitivity note: on the SWE-bench-Verified-only subset (n≈9–10/model) the reads
were flash `process_verifier` 0.74, v3 `outcome_only` 0.19, pro unestimable. Only
flash's process_verifier survives every cohort composition; treat the rest as
directional. `outcome_only` vs `anti_hack_penalty` are near-antiparallel
(cosine −0.81) and cannot be separated passively — motivating E4.

Instrument fix recorded: 3 crashed runs (provider-402, 2–9 turns) had entered the V3
pool; crash exits are now excluded from all pools (regression-tested).

**Citations.** Identifiability: [arXiv 2411.15951], [arXiv 2106.03498]. Length
confounding: [arXiv 2604.02547].

---

## E2 — Progress curves (AgentPRM proxy)

**Question.** Does the model measure its own progress toward the goal during the
trajectory?

**Method.** Every `test_run` event records parsed passed/failed counts. Per run, plot
pass fraction vs normalized trajectory position (step / total steps — normalization
removes the length confound); per model, average curves over runs with a bootstrap band.
This is a model-free proxy for AgentPRM's learned progress signal and is labeled as such.
*Honesty note:* it measures the pass rate of the tests the agent chose to run, not the
hidden F2P suite.

**Expected result (pre-registered).** V4 curves rise through the trajectory (it tracks
progress); V3-base produces **no curve at all** — zero test runs means zero progress
measurements, which is itself the finding.

**Status.** Ready — computable from stored traces; no new runs.

**Citations.** AgentPRM: [arXiv 2511.08325]. Self-correction framing:
[arXiv 2507.21504]. Credit-assignment context: [arXiv 2604.09459].

---

## E3 — Long-context recall (H13, user hypothesis)

**Question.** Was V4 (1M context) RL-trained with reward favoring recall of earlier
context inside reasoning steps?

**Origin.** User hypothesis (strong confidence), pre-registered 2026-06-12. Novel — no
published peer; distinct from H7 (`re_read_rate`, memory via re-action) and H9
(`recall_template`, memory from training weights). H13 is **working memory**: referencing
old context without re-reading it.

**Method (deterministic, no judge, no new runs).**
1. From each run's tool results, extract an artifact vocabulary (file paths,
   function/class names, error strings, test ids), each tagged with the turn it appeared.
2. For each reasoning turn (`thinking`/`assistant_msg` text), find artifact mentions where
   the artifact was last seen **> W turns ago** (W≈10), is not in the prompt, and was not
   re-read in between.
3. Metrics: `long_range_recall_rate` (fraction of reasoning turns with ≥1 such mention)
   and `recall_distance_norm` (median turns-since-seen / trajectory length). Both
   length-invariant; `long_range_recall_rate` loads on `context_mgmt`.

**Expected result (pre-registered).** V4 ≫ V3 on recall rate, with a fat recall-distance
tail (references reaching 20–40+ turns back); V4 sits in the high-recall/low-re-read
quadrant.

**Falsified if.** V4's recall-distance tail is not fatter than V3's, or V4's apparent
recall is mostly re-reading. Confound check: V3 reads little overall, so recall is always
plotted against re-read rate, never alone.

**Result (2026-06-12) — first measurement, partial support.**

| Model | long_range_recall_rate | recall_distance_norm | re_read_rate |
|---|---|---|---|
| v4-pro | **0.102** (n=11) | 0.278 (n=8) | 0.499 |
| v4-flash | 0.050 (n=12) | 0.302 (n=8) | 0.559 |
| v3-base | 0.000 (n=1) | — (no recalls) | 0.000 |

- **Supported:** the recall *ordering* — pro recalls dormant context at 2× flash's rate,
  and V3 not at all; recalls reach ~28–30% of trajectory length back.
- **Not supported (as stated):** the "recall *instead of* re-read" half. V4's re-read
  rate is *high* (~0.5), so V4 recalls *and* re-reads — it is not in the clean
  working-memory quadrant. If H13's reward exists, it pays for recall without
  penalizing re-fetching.
- **Censoring caveat:** the dormancy window makes H13 unmeasurable on trajectories
  ≤10 turns, which silently excludes almost all V3 runs (n=1 measurable). The V4-vs-V3
  comparison is therefore weak; pro-vs-flash (n=11 vs 12) is the solid contrast.

**Status.** Measured (first pass); pre-registration retained above, verbatim.

**Cross-lab update (2026-06-12, post-E8).** With kimi-k2 (0.086) and glm-4.6 (0.084)
measured, long-range recall is NOT V4-specific: models with much smaller contexts
(K2 256k, GLM-4.6 200k) recall dormant context at near-pro rates, and glm shows the
longest distance tail. This weakens H13's *1M-context-specific* clause — long-range
recall now looks like a general property of modern agentic-RL training rather than a
signature of V4's million-token reward. The V4≫V3 ordering stands; the attribution to
context-length-specific reward does not. qwen3-coder (0.052) ≈ flash (0.050).

**Citations.** Novel (openbench). Context-management reward background: see H7 references
in [RESEARCH.md](RESEARCH.md).

### E3b — Action-grounded recall + DeepSeek calibration (amendment, registered 2026-06-12)

**Registered BEFORE computing any E3b number.** Motivation: frontier APIs hide reasoning
text (OpenAI returns token counts only; our Claude runs had thinking disabled), so
prose-recall is unmeasurable or floor-only for the E8/E9 cohorts. Actions, however, are
visible for every model — and a command that *targets* a dormant artifact proves
retention in a way prose cannot (an action is verifiable; a mention can be confabulated).

**Channel separation (definition change, applies from this commit).** The mini-swe
assistant message contains the fenced command, so the existing prose scan was
contaminated by action text. From now on:
- **prose channel** = `thinking` + `assistant_msg` with ```fenced blocks stripped```;
- **action channel** = the *executed* command of each tool event (hallucinated extra
  fences never count) plus heredoc edit bodies within it.
Both channels update artifact `last_seen` (any occurrence resets dormancy), as do tool
results. Window, prompt-exclusion, and artifact vocabulary identical to E3.

**New metrics (deterministic, length-invariant).**
- `action_recall_rate` — fraction of executed commands referencing ≥1 artifact last seen
  > W turns back (not in prompt, not re-seen since). `None` if trajectory ≤ W turns or
  no commands.
- `action_recall_precision` — of action-recall references to *checkable* artifacts
  (paths, pytest node ids), the fraction whose target existed as referenced, judged from
  that command's own result (conservative not-found markers: "No such file or
  directory", "ERROR: file or directory not found", "cannot open", "does not exist").
  Distinguishes genuine retention from hallucinated memory. `None` if no checkable
  recall events.

**Calibration protocol (the proxy is validated, not assumed).** On the only runs where
both channels are observable — deepseek-v4-flash + v4-pro (n≈23, 4.4M chars of raw
reasoning) — compute per-run (prose_recall, action_recall) pairs and Spearman ρ.
1. **Convergent validity, pre-registered prediction:** ρ ≥ 0.4 across measurable runs.
2. **Known-groups validity, pre-registered prediction:** action-basis ordering preserves
   V4 > V3 (both models measured on the SAME channel for the first time — this also
   removes E3's original channel-asymmetry caveat).

**Falsified if** ρ < 0.4 → prose- and action-recall are reported as separate constructs;
NO recall claims are made for hidden-CoT models. If ρ ≥ 0.4 but V4 > V3 fails on the
action basis → the proxy distorts between-model scale; deployment blocked and the
original E3 ordering result is itself re-examined.

**Deployment rules (conditional on calibration pass).**
- For hidden-CoT/thinking-off models, action-recall claims are **floors** ("at least
  this much behaviorally-proven recall"), never point estimates of total recall.
- `action_recall_rate` (+1.0) and `action_recall_precision` (+0.5) join `context_mgmt`
  in SIGNATURES **only if calibration passes** — giving that column positive markers
  that inaction cannot vacuously satisfy (a 2-turn confabulated run yields `None`,
  not a spurious positive).
- **Transport assumption (named limitation):** calibration on DeepSeek transports to
  other labs only if the prose↔action coupling is approximately model-invariant.
  Partially evidenced if the coupling holds across flash AND pro (different recipes
  per E1); untestable on hidden-CoT models by construction.

**Result (2026-06-12, same day, post-registration) — CALIBRATION PASSED.**

- **Convergent validity: ρ = 0.713** (n=23 pairs; bar was 0.4). Decisively, the
  coupling holds *within* each model — flash ρ=0.701 (n=12), pro ρ=0.756 (n=11) — so
  the pooled correlation is not a between-model (Simpson) artifact, and the coupling
  holding across two different training recipes is the strongest available evidence
  for the transport assumption.
- **Known-groups: V4 > V3 preserved on the action basis** (flash 0.051, pro 0.059 vs
  V3 0.0) — but V3 remains n=1-measurable (dormancy-window censoring, same caveat as
  E3). Weak pass, flagged.
- **Precision ≈ 1.0 everywhere measurable**: across 14 DeepSeek runs with checkable
  recalls, every dormant artifact the models acted on actually existed. One exception
  corpus-wide: kimi-k2 at 0.938 — the first observed case of a model **acting on a
  hallucinated memory**.
- Deployed per the registered rules: `action_recall_rate` (+1.0) and
  `action_recall_precision` (+0.5) now load `context_mgmt` in SIGNATURES.

**Revision to E3's cross-lab numbers (channel-cleanup side effect).** Fence-stripping
changed the prose channel: the earlier cross-lab prose-recall values (kimi 0.086,
glm 0.084) were heavily contaminated by *command text inside fences* — cleaned, they
collapse to 0.009 / 0.009, while DeepSeek's drop less (flash 0.050→0.026, pro
0.102→0.071, reasoning-text dominated). The cross-lab comparison now lives on the
action basis, where it is apples-to-apples for the first time:

| model | action_recall_rate (floor for hidden-CoT) | precision |
|---|---|---|
| kimi-k2 | 0.081 | 0.938 |
| glm-4.6 | 0.075 | 1.0 |
| v4-pro | 0.059 | 1.0 |
| v4-flash | 0.051 | 1.0 |
| gpt-5 | 0.045 | 1.0 |
| gpt-5.5 | 0.044 (n=1 measurable) | 1.0 |
| qwen3-coder | 0.042 | 1.0 |
| gpt-4.1 | 0.026 | 1.0 |
| claude-fable-5 | 0.0 (n=2 measurable) | — |
| claude-opus-4-8 | unmeasurable (all runs ≤ window) | — |
| v3-0324 | 0.0 (n=1 measurable) | — |

**E3 conclusion, restated on the clean channel:** behaviorally-proven long-range recall
is a general property of modern agentic-RL models (kimi/glm slightly *above* V4), not a
V4-1M signature — the earlier cross-lab revision of H13 is CONFIRMED, now without the
channel-asymmetry caveat. First-ever recall floors for OpenAI models measured.

**Status.** Calibrated (ρ=0.713), deployed into SIGNATURES, cross-lab floors measured.

---

## E4 — Forced-pattern probes (GPSO inverted)

**Question.** Which behaviors were *reinforced* — measured causally, not observationally?

**Method.** GPSO trains pattern selection by forcing patterns via prompt suffixes
([arXiv 2601.07238]); we invert that mechanism as a test-time probe. Each (task, model)
runs under: `natural`, `no-verify` ("solve directly, do not run tests"), `verify-first`,
`explore-multi`, and `neutral-control` (a formatting instruction that estimates baseline
instruction-following, de-confounding resistance from weak IF). Compliance signals are
deterministic trace events (e.g. `test_run_count > 0`).

Three readouts:
1. **Per-pattern intrinsic success** by intervention — supplies E7's x-axis directly.
2. **Pattern resistance** — verifying under `no-verify` is a direct causal test of H10
   (intrinsic-verification reward): behavior that survives an explicit counter-instruction
   was trained in, not chosen instrumentally.
3. **Selection efficiency** — gap between the natural pattern choice and the best forced
   pattern per task.

**Expected result (pre-registered).** V4-flash keeps verifying under `no-verify`
(resistance ⇒ H10); V3-base barely verifies even under `verify-first`. Differential
compliance maps which behaviors the reward paid for.

**Quarantine rule.** Probe runs never enter natural-run fingerprints or the E1 fit (same
rule as honeypot/impossible probes).

**Status.** Ready — needs new runs (P conditions × tasks × models); deterministic
analysis.

**Citations.** [arXiv 2601.07238] (GPSO). Probe-experiment necessity:
[arXiv 2411.15951].

---

## E5 — pass@k, consistency, and divergent-step credit (SALT)

**Question.** How reliable is each model across k attempts, and which steps actually
differentiate success from failure?

**Method.** Run k replicates per (task, model) at temperature > 0 (replicate run-ids are
already unique). Compute per (task, model): **pass@k** (≥1 of k resolves), **consistency**
(fraction resolving). Then SALT-style: normalize each step to a signature
`(event type, tool, command head)`, partition signatures into *shared* (in ≥ k−1
rollouts) vs *divergent*, and credit each divergent signature by empirical contrast —
solve rate of rollouts containing it minus solve rate of rollouts without it
([arXiv 2510.20022]). The k-rollout grouping is also the data prerequisite for a future
learned AgentPRM value model ([arXiv 2511.08325]) — documented, not implemented.

**Expected result (pre-registered).** V4 fails *consistently* (same failure path across
k); V3 fails *incoherently* (divergent failure paths). Once tasks solve: divergent steps
on solving paths concentrate on verification actions for V4.

**Honesty constraints.** pass@k is a set statistic over k runs — NOT length-invariant per
run, never enters the per-run signature or `RunMetrics`. At ~0% solve it measures
failure-mode consistency only, and is labeled so.

**Status.** Ready — needs k× new runs; k=3–5 gives coarse credit estimates (reported as
"candidate pivotal steps," not significance-tested).

**Citations.** [arXiv 2510.20022] (SALT), [arXiv 2604.09459] (credit-assignment survey),
[arXiv 2511.08325] (AgentPRM).

---

## E6 — Reasoning-pattern fingerprint (H12)

**Question.** Which reasoning patterns does each model select, and does RL concentrate the
distribution?

**Method.** An LLM judge classifies each trajectory's reasoning text into a fixed
6-pattern taxonomy, returning a distribution; per model we aggregate the mean distribution
and its concentration (`normalized_entropy = H(p)/log 6`, top-1 mass). Model-level, like
H10/H11 — never a per-run signature metric (judge output is nondeterministic, so it stays
out of the deterministic E1 fit by construction).

**Taxonomy provenance (per pattern, because no published taxonomy exists for agentic
coding — the literature's taxonomies are math-only):**

| Pattern | Provenance |
|---|---|
| `verify_first` | [arXiv 2503.01307] verification; [arXiv 2601.07238] reflection-and-verification |
| `backtrack_self_correct` | [arXiv 2503.01307] backtracking |
| `decompose_first` | [arXiv 2503.01307] subgoal setting |
| `enumerate_cases` | [arXiv 2601.07238] explore-multiple-solutions, adapted |
| `greedy_patch` | [arXiv 2601.07238] direct solution, adapted to coding |
| `recall_template` | **novel (openbench, H9)** |

**Validity check.** [arXiv 2506.04695] *discovers* patterns by clustering rather than
fixing them; one judge pass in discovery mode ("cluster these trajectories, describe each
cluster") checks whether the fixed six miss the dominant agentic-coding pattern.

**Expected result (pre-registered).** RL-trained V4 has lower normalized entropy / higher
top-1 mass than base V3 (pattern-selection theory: RL concentrates selection).

**Status.** Pending — judge tier (stub registered like H8/H9).

**Citations.** [arXiv 2506.04695] (pattern-selection theory), [arXiv 2601.07238] (GPSO),
[arXiv 2503.01307] (cognitive behaviors).

---

## E7 — Pattern-selection shift test

**Question.** Does RL improve *selection* of patterns rather than *execution within*
patterns — the central claim of [arXiv 2506.04695]?

**Method.** For each pattern: x = intrinsic success rate (from E4's forced-pattern
interventions — sidestepping the sparse-natural-data problem), y = selection frequency
(from E6's judge labels). Plot base-model and RL-model points per pattern, connected.

**Expected result (pre-registered).** Shift lines are **vertical**: per-pattern success
rates statistically indistinguishable between base and RL (overlapping Wilson CIs), while
selection mass moves to high-success patterns.

**Falsified if.** Shift lines are diagonal — RL's per-pattern success significantly
exceeds base for the same pattern, meaning RL taught execution, not selection (the theory
fails to transfer from math to agentic coding — itself a publishable finding).

**Status.** Pending — needs E4 (x-axis) + E6 (y-axis) + a solvable task band.

**Citations.** [arXiv 2506.04695].

---

## E8 — Cross-lab recipe prediction (calibration rung 2)

**Question.** Can the fingerprint predict a lab's published reward recipe it has never
seen — the cheapest external calibration test available?

**Protocol (registered 2026-06-12, before any runs).**
1. Run 3 models from other labs on the 4 SWE-bench Verified tasks via OpenRouter,
   concurrency 1 (free-tier account): `moonshotai/kimi-k2-0905`, `z-ai/glm-4.6`,
   `qwen/qwen3-coder`. All three have public technical reports.
2. Grade, analyze, estimate compositions — **without consulting any of the three
   technical reports at any point before step 3 is committed.**
3. Write the predicted reward recipe per model into this file, derived from the
   fingerprint alone.
4. Only then read the three reports and score each prediction (hit / partial / miss),
   recording both prediction and report excerpt here.

**Disclosed-priors caveat (required for honesty).** This is *prediction-before-reading*,
not a true blind: the analyst's prior knowledge already includes coarse facts about
these labs' methods (e.g. Kimi K2's rubric reward is cited in our own H6 registry).
Mitigation: predictions must cite which fingerprint values drive them, so a reader can
check the chain from measurement to claim; the K2 prediction is flagged as
prior-contaminated, GLM/Qwen less so.

**Expected outcome (pre-registered).** At least 2 of 3 predictions substantially match
the published recipe. A miss is equally informative: it localizes which component
signatures are mis-specified.

**Cost/limits.** ~12 runs ≈ $3–8 against a $29.8 key limit; key expires 2026-07-11.

**Status.** Runs complete 2026-06-12 (12/12, $2.00, 0 crashes). Solves: glm-4.6 2/4,
kimi-k2 1/4, qwen3-coder 0/4 — first multi-solve cohort; outcome metrics interpretable.

### Step 3 — predictions (committed 2026-06-12 ~17:00 UTC, BEFORE reading any report)

**kimi-k2-0905** — predicted recipe: *agentic outcome-reward RL plus a self-judging /
rubric general-reward component; weak process/verifier shaping; some efficiency or
length shaping.* ⚠ prior-contaminated (K2's rubric reward already cited in our H6).
Driving fingerprint: smallest, most surgical diffs in the cohort (diff_size_ratio 20 vs
~1000 for the other two); finishes voluntarily (3/4 completed) yet `verified_before_done`
= 0.00 and `recovery_rate` = 0.00 — it runs tests (0.354/edit) but does not iterate
failing suites to green, so verification was not itself paid for; highest
post-success churn (0.188) suggests polish-after-green (judge/rubric pressure).
Estimable mixture: only weak `outcome_only` 0.06.

**glm-4.6** — predicted recipe: *hybrid outcome-reward agentic RL with an explicit
self-correction / iterative-repair emphasis, plus a general reward model (rubric/judge)
for non-verifiable quality.* Driving fingerprint: best solver (2/4);
`recovery_rate` = 1.00 (every failing test run eventually reached green) with
`gave_up_failing` = 0.00 — trained persistence on failure; mixture estimable:
`rubric_grm` 0.33 + `outcome_only` 0.25; verification used instrumentally
(verified_before_done only 0.25) rather than ritually.

**qwen3-coder** — predicted recipe: *large-scale execution-feedback code RL rewarding
target-task/test completion WITHOUT a regression or scope penalty; heavy synthetic
agentic SFT (explore-heavy, read-before-edit); little or no process-verifier or
anti-hack shaping.* Driving fingerprint: 0/4 solves with catastrophic P2P breakage
(166 regressions on 13757) while exploring most (exploration 0.79, search_before_edit
0.25, guess_first 0.00) and targeting gold files best (file_jaccard 0.284) — it finds
the right place, rewrites it wholesale, and never confirms the world still stands;
nothing estimable in the mixture (residual 3.61).

### Step 4 — scoring (2026-06-12, after reading the reports)

**kimi-k2 — HIT (prior-contaminated, as disclosed).** Published recipe ([arXiv
2507.20534]): RLVR with a binary verifiable-rewards gym (outcome 1/0, incl. coding) +
**self-critique rubric reward** where the model judges its own outputs. Matches both
predicted components (outcome-RL + self-judging rubric). Predicted "weak
process/verifier shaping": the published reward is outcome-binary with no process
reward — consistent with measured verified_before_done 0.00 / recovery_rate 0.00.

**glm-4.6 — HIT/partial.** Published recipe (GLM-4.5 report, [arXiv 2508.06471];
4.6 has no separate full report — scored against its direct predecessor): agentic RL
on auto-verifiable web-search/code agents with **dense multi-turn rewards**
("correct function calls over consecutive rounds") + expert iteration/self-distillation.
The dense consecutive-round reward matches the predicted self-correction emphasis
(measured recovery_rate 1.00, gave_up_failing 0.00). The predicted general-RM/rubric
component is not explicit in the excerpts read — scored partial.

**qwen3-coder — HIT/partial.** Published recipe (Qwen3-Coder lineage, [arXiv
2603.00729]): **execution-driven RL on unit tests** over large-scale *synthetic*
verifiable tasks (single-turn + multi-turn agentic). Matches predicted
execution-feedback code RL + synthetic-task emphasis. The sharpest prediction —
*target-test reward without a regression/scope penalty* (from the measured 166-test P2P
breakage) — is supported **by omission**: the report's anti-hacking measures are
termination and tool-format penalties, not regression penalties. Evidence-by-omission
is weak; scored partial on that clause. Predicted "little anti-hack shaping" was
wrong in kind: they do shape against hacking, but against format/termination gaming,
not scope damage.

**E8 outcome: 1 hit + 2 hit/partials — meets the pre-registered bar ("at least 2 of 3
substantially match").** Calibration value: the estimator separated three labs'
recipes in the right directions from 4 runs each; the misses localize cleanly (the
rubric/judge column needs a sharper signature; scope-damage vs format-gaming are
different anti-hack subtypes worth splitting). Cohort note: GLM scored against the
predecessor report; K2 hit discounted for disclosed prior.

Added references: [arXiv 2507.20534] (Kimi K2), [arXiv 2508.06471] (GLM-4.5 ARC),
[arXiv 2603.00729] (Qwen3-Coder-Next).

---

## E9 — Frontier cohort (Anthropic + OpenAI), blind protocol

**Registered 2026-06-12, runs in flight.** Same protocol as E8: `claude-opus-4-8`,
`claude-fable-5`, `gpt-5.5`, `gpt-5`, `gpt-4.1` × the 4 SWE-bench Verified tasks
(concurrency 3, $2.50/run cap). Predictions will be committed from fingerprints alone
before consulting any Anthropic/OpenAI training documentation. Disclosed-priors caveat
applies more strongly here: the analyst's priors about these labs are substantial;
predictions must cite driving fingerprint values, and hits are discounted accordingly.
Note: these providers do not return reasoning text on this endpoint, so
`thinking_fraction` reads 0 for this cohort (same as E8) — recall metrics still work
on assistant prose.

### Results (graded 2026-06-12)

18/20 cells usable. Two `gpt-5` cells on the hard tasks (sympy-23534, sympy-23950)
were lost: the orchestrator exited while both containers were wedged on an
in-container hang (one a catastrophic-backtracking regex the agent itself wrote,
`re.compile(r"...(?:.*\n){1,80}?...", re.DOTALL)`, pinning a core for 40 min; the
host-side `exec_in` timeout does not propagate a kill into the container). Both
marked `crash`, excluded by the `_crashed()` guard. `gpt-5` is therefore n=2.

**Solve rate (F2P, clean-room):** 6/18 resolved, **0 tampering events** across all
cells.

| model | sy-13757 | sy-22914 | sy-23534 | sy-23950 | solved |
|---|:--:|:--:|:--:|:--:|:--:|
| claude-fable-5  | ✗ | ✓ | ✓ | ✗ | 2/4 |
| claude-opus-4-8 | ✗ | ✓ | ✗ | ✗ | 1/4 |
| gpt-5.5         | ✗ | ✓ | ✓ | ✗ | 2/4 |
| gpt-5           | ✗ | ✓ | — | — | 1/2 |
| gpt-4.1         | ✗ | ✗ | ✗ | ✗ | 0/4 |

**Fingerprints (NNLS estimable weights; `—` = CI∋0, not estimable):**

| model | estimable mixture | distinctive metric |
|---|---|---|
| claude-opus-4-8 | context_mgmt .27, anti_hack .24, outcome .18, similarity .18, length .14; **process_verifier not estimable** | `confabulated_completion` **0.75** (z+1.50), `early_stop` 1.0, `test_run_count` **0** |
| claude-fable-5  | similarity_to_gold .40 (sole estimable); realized process 0.85 | `verified_before_done` 0.5, protocol-clean |
| gpt-5.5         | similarity .39, process .29, anti_hack .22 | brisk voluntary completion (9–23 turns) |
| gpt-5           | process_verifier .51, outcome .05 (n=2) | persistent test-grinder; realized process 1.10 |
| gpt-4.1         | **nothing estimable** (all CI∋0, 0 solves) | grinds to turn cap |

### Blind recipe predictions — COMMITTED before reading any Anthropic/OpenAI docs

> Disclosed-priors caveat in force: priors about these labs are strong, so each
> prediction cites the driving fingerprint value and hits are discounted. Predictions
> are frozen as of this commit; scoring follows in a separate pass.

1. **claude-opus-4-8 → outcome + safety/anti-hack reward, verification NOT learned as
   in-context test execution; agentic competence trained against its *native* tool
   harness.** Drivers: `process_verifier` not estimable + `test_run_count`=0 +
   `verified_before_done`=0 (it never runs tests in a bare shell), yet `anti_hack` .24
   and `context_mgmt` .27 are sharply estimable. Strong sub-claim: the
   `confabulated_completion`=0.75 is a **scaffold-mismatch artifact** — Opus expects
   structured tool-call/observation turns and, denied them, hallucinates the loop. Falsified
   if a native-tool-format probe variant still shows high confabulation.
2. **claude-fable-5 → reference-solution-aligned reward (similarity/correctness) with a
   genuine process-verification component.** Drivers: similarity_to_gold .40 sole
   estimable; realized process 0.85; verifies before done. Cleaner instruction-following
   than Opus on this scaffold.
3. **gpt-5.5 → the most *balanced* recipe: correctness + process-verification +
   scope/anti-hack penalty.** Drivers: three co-estimable components (.39/.29/.22) — the
   only frontier model with anti_hack estimable alongside process. Predict deliberate
   calibrated stopping (reward for efficiency, not grinding).
4. **gpt-5 → execution/process-verifier-heavy, outcome-light (test-driven RL).** Drivers:
   process .51 ≫ outcome .05; realized process 1.10 (highest of cohort); grinds tests.
   Same family signature as deepseek-v4-flash. (n=2 — low confidence, flagged.)
5. **gpt-4.1 → not estimable from this cohort.** Honest null: at n=4 with 0 solves the
   fingerprint is a noise floor. Predict an older-generation, weaker agentic-RL recipe
   that this passive probe cannot resolve; do not score as a hit/miss.

**Scoring:** pending — to be done after reading public model cards / system cards in a
separate, clearly-marked pass, exactly as E8.

**Status.** Predictions frozen; scoring pending.

---

## E10 — Claude scaffold falsification (within-Opus factorial)

**Registered 2026-06-13, BEFORE running A/B.** E9 left the Opus result confounded:
its fingerprint (confab 0.75, 3-turn dreamed sessions, zero-line patches) could be a
reward signature OR an artifact of the bare text-fence `mini-swe` scaffold being
out-of-distribution for Claude — *and* Claude's E9 runs had extended thinking
disabled. Two changed variables, so the `claude-native` runner alone cannot attribute
the cause. This factorial isolates them, holding model = `claude-opus-4-8` fixed.

| cell | protocol | thinking | source |
|---|---|---|---|
| C | text-fence (mini-swe) | off | already have (E9) — confab 0.75 baseline |
| A | native tool-use | off (no thinking param) | this experiment |
| B | native tool-use | on (adaptive, effort=high) | this experiment |

Run A and B on the two hard tasks Opus confabulated on under mini-swe
(sympy-13757, sympy-23534). `confabulated_completion` is the deterministic readout.

**Identification.** A vs C differ ONLY in protocol (thinking off both) → isolates the
protocol effect. B vs A differ ONLY in thinking (native both) → isolates the thinking
effect. Caveat: A/B use the `/v1/messages` endpoint, C the OpenAI-compatible
`/chat/completions`; both are "no extended thinking", so the residual endpoint
difference is folded into the protocol contrast and acknowledged.

**Pre-registered predictions (frozen).**
- Primary: `confab(A) ≈ confab(B) ≈ 0  ≪  confab(C)=0.75` → **the confabulation is
  scaffold-induced (protocol), not a reward fingerprint.** Opus engages (runs tests,
  edits, multi-turn) on the native protocol.
- Solve rate on the two hard tasks rises above the mini-swe 0/2.
- **Falsified if:** A still confabulates (≥0.5) while B does not → thinking, not
  protocol, was the cause; OR both A and B still confabulate → genuine Opus property,
  the "fix" is illusory and confabulation must be reported as a real fingerprint.

**Status.** Predictions frozen; A/B running.

> **Note (2026-06-13):** the `claude-fable-5` API is unavailable for an extended period, so
> the follow-up "re-run the Claude cohort on `claude-native`" is scoped to **Opus only**.
> Fable's existing `mini-swe` runs remain in the corpus; no new Fable runs are planned until
> the endpoint returns.

---

## E11 — Are this year's reasoning patterns RL-reward-shaped? (H14, isolated)

**Question.** Are the reasoning behaviours (verify / recall / recover) *instrumental* — deployed
where they pay and traceable to a recoverable reward — i.e. caused by RL reward (H14)?

**Method.** Apply three tests to the behaviour set {verify, recall, re-read, recover}:
1. **Difficulty-graded deployment** — behaviour rate vs hardness tier (reuses H11 slope);
   reward-shaped ⇒ rises where errors are costly.
2. **Forced-pattern resistance** (reuses E4/GPSO) — natural / no-verify / verify-first /
   neutral-control.
3. **Reward recovery on RL anchors** — on DeepSeek R1/V3 (documented RLVR) the estimator must recover
   the documented reward (positive control that the method can detect reward-shaping at all).
Recall/re-read load `context_mgmt` (recall +, re-read −); for recall add a memory-pressure
manipulation (tasks needing a dormant far-back artifact vs all-recent): instrumental recall rises
under pressure and substitutes for re-reading; mimetic recall is flat.

**Expected result (pre-registered).** Positive behaviour×difficulty slope; estimator recovers R1/V3's
documented reward; recall rises under memory pressure and substitutes for re-read.

**Falsified if.** Behaviour is flat across difficulty AND the estimator cannot recover known RL
recipes → not (this-year) reward-shaped.

**Plots.** P11a verification×difficulty slope; P11b forced-pattern resistance (see flaw below);
P11c reward-recovery calibration heatmap; P11d recall×memory-pressure; P11e recall/re-read
substitution scatter.

**Backing & limitations (honest grading).** Methods are cited ([arXiv 2604.02547] difficulty-control;
[arXiv 2601.07238] GPSO; [arXiv 2503.01307] cognitive behaviours; [arXiv 2604.09459] /
[arXiv 2511.08325] credit; [arXiv 2411.15951] / [arXiv 2106.03498] identifiability), but the
*discriminating interpretations* are partly inference:
- **P11b is a weak discriminator of H14 vs H15** — resistance to "no-verify" proves the behaviour is
  *trained in*, but SFT/distillation-installed verification is also trained in and would also resist.
  P11b separates *disposition vs task-choice*, not reward vs imitation → demoted to context.
- P11a's "slope ⇒ reward-shaped" reading is inference; P11c is a positive control only (signature
  matrix uncalibrated, E8 precedent was 1 hit + 2 partials); recall (P11d/e) is the weakest axis
  (long-range recall is a general agentic-RL property, `context_mgmt` weakly identified).

**Status.** Ready — difficulty-tiered tasks + probe runs (API; agentic tasks need Docker).

**Citations.** [arXiv 2604.02547], [arXiv 2601.07238], [arXiv 2503.01307], [arXiv 2604.09459],
[arXiv 2511.08325], [arXiv 2411.15951], [arXiv 2106.03498]; recall/context = H7/H13 refs.

---

## E12 — Is this year's reasoning mimetic/convergent (propagation)? (H15, isolated)

**Question.** Are the reasoning fingerprints convergent and form-sharing (imitation/distillation)
rather than lab-divergent (independent reward) — i.e. spread by propagation (H15)?

**Method.** Poles = RL anchor (R1/V3) and distillation control (V4).
1. **Cross-lab convergence** — pairwise reasoning-fingerprint distance, within-lab vs across-lab.
2. **Pole-clustering** — embed fingerprints (MDS); locate targets (Opus 4.8, GPT-5.5) vs the poles.
3. **Idiosyncratic-form sharing** — shared reasoning tics (phrasings, tool-call/command structure,
   narration) across lab pairs: form beyond function.
4. **Temporal drift** — within-lab version trajectories (GPT-4.1→5→5.5; Opus 4.6→4.7→4.8); do new
   versions move toward the prior frontier leader?

**Expected result (pre-registered).** Across-lab ≈ within-lab distance (convergent); targets cluster
nearer V4; high cross-lab form-sharing; new versions drift toward the prior leader.

**Falsified if.** Fingerprints diverge across labs AND targets cluster with the RL pole AND no shared
idiosyncratic form AND no drift toward the leader.

**Plots.** P12a convergence heatmap; P12b pole-clustering map; P12c idiosyncratic-form similarity;
P12d temporal-drift trajectory.

**Backing & limitations (honest grading).** Each method is cited — on-policy distillation
([arXiv 2604.00626] survey, [arXiv 2601.18734], [arXiv 2604.03128]) supplies the cheaper-than-RL
economics; distillation foundations [arXiv 1503.02531]; reasoning distills [arXiv 2501.12948];
detection/provenance ([arXiv 2512.20908] → P12b/d; behavioural+stylistic fingerprinting LLMmap / DLI /
REEF, [arXiv 2510.16968], [arXiv 2602.03812] → P12a/c); concentration [arXiv 2506.04695].
**Load-bearing signal = P12c only** — shared *quirks* resist the independent-reward explanation
(caveat: needs visible output, weak for hidden-CoT). The rest are partial: P12a/P12b don't rule out
*independent convergence to the same optimum* and the V4 pole is itself distillation-of-RL'd-teachers
(contaminated); P12d is a novel, confounded longitudinal design. **Novel (openbench):** the composite
— using these methods together to adjudicate reward vs propagation as the cause of the reasoning shift.

**Status.** Ready — P12a/b/c on a reasoning-only API prompt set (no Docker) as a first cut; P12d needs
multiple versions per lab.

**Citations.** [arXiv 2604.00626], [arXiv 2601.18734], [arXiv 2604.03128], [arXiv 1503.02531],
[arXiv 2501.12948], [arXiv 2512.20908], [arXiv 2510.16968], [arXiv 2602.03812], [arXiv 2506.04695].

---

## Out of scope (documented, not run)

| Idea | Why not |
|---|---|
| Sparse critical-token analysis (1–3% token corrections) | Needs per-token logprobs from base AND RL model on identical prefixes; not exposed by the APIs we use |
| HCAPO / GRPO / RLOO / SHARP / HiPER internals | Training-side mechanisms, invisible in deployed-model traces; E1 infers the reward *family* instead |
| Learned AgentPRM value model | Needs the E5 rollout data first; registered as the Tier-3 future |

---

## Figure map

| Figure | Experiment | Status |
|---|---|---|
| Reward decomposition (weights + CI / z-heatmap / collinearity) | E1 | live |
| Progress curves | E2 | ready (analysis-only) |
| Context-recall fingerprint (recall vs re-read scatter; recall-distance distribution) | E3 | ready (analysis-only) |
| Probe-resistance matrix | E4 | needs probe runs |
| pass@k & consistency table; divergent-step graph | E5 | needs k-replicate runs |
| Pattern distribution + entropy | E6 | needs judge |
| Pattern-selection shift scatter | E7 | needs E4 + E6 + solvable band |
| Instrumentality set (verify×difficulty, forced-pattern, reward-recovery, recall×pressure, substitution; P11a–e) | E11 | needs probe + difficulty-tier runs |
| Propagation set (convergence heatmap, pole-clustering MDS, idiosyncratic-form similarity, temporal drift; P12a–d) | E12 | P12a–c API-only; P12d needs multi-version |

---

## References

- [arXiv 2506.04695] Chen, Li & Zou. *Reshaping Reasoning in LLMs: A Theoretical Analysis of RL Training Dynamics through Pattern Selection.* <https://arxiv.org/abs/2506.04695>
- [arXiv 2601.07238] *Group Pattern Selection Optimization: Let LRMs Pick the Right Pattern for Reasoning.* <https://arxiv.org/abs/2601.07238>
- [arXiv 2503.01307] Gandhi et al. *Cognitive Behaviors that Enable Self-Improving Reasoners.* <https://arxiv.org/abs/2503.01307>
- [arXiv 2510.20022] *SALT: Step-level Advantage Assignment for Long-horizon Agents via Trajectory Graph.* <https://arxiv.org/abs/2510.20022>
- [arXiv 2604.09459] *From Reasoning to Agentic: Credit Assignment in Reinforcement Learning for Large Language Models* (survey, 47 methods). <https://arxiv.org/abs/2604.09459>
- [arXiv 2511.08325] *AgentPRM: process reward via progress estimation.* <https://arxiv.org/abs/2511.08325>
- [arXiv 2604.02547] *Beyond Resolution Rates* — length/difficulty confounding in agent evaluation. <https://arxiv.org/abs/2604.02547>
- [arXiv 2411.15951] Reward identifiability under behavioral-model misspecification. <https://arxiv.org/abs/2411.15951>
- [arXiv 2106.03498] *Identifiability in Inverse Reinforcement Learning.* <https://arxiv.org/abs/2106.03498>
- [arXiv 2507.21504] Survey: self-correction / trajectory metrics for LLM agents. <https://arxiv.org/abs/2507.21504>

[arXiv 2506.04695]: https://arxiv.org/abs/2506.04695
[arXiv 2601.07238]: https://arxiv.org/abs/2601.07238
[arXiv 2503.01307]: https://arxiv.org/abs/2503.01307
[arXiv 2510.20022]: https://arxiv.org/abs/2510.20022
[arXiv 2604.09459]: https://arxiv.org/abs/2604.09459
[arXiv 2511.08325]: https://arxiv.org/abs/2511.08325
[arXiv 2604.02547]: https://arxiv.org/abs/2604.02547
[arXiv 2411.15951]: https://arxiv.org/abs/2411.15951
[arXiv 2106.03498]: https://arxiv.org/abs/2106.03498
[arXiv 2507.21504]: https://arxiv.org/abs/2507.21504

[arXiv 2507.20534]: https://arxiv.org/abs/2507.20534
[arXiv 2508.06471]: https://arxiv.org/abs/2508.06471
[arXiv 2603.00729]: https://arxiv.org/abs/2603.00729

[arXiv 2604.00626]: https://arxiv.org/abs/2604.00626
[arXiv 2601.18734]: https://arxiv.org/abs/2601.18734
[arXiv 2604.03128]: https://arxiv.org/abs/2604.03128
[arXiv 2512.20908]: https://arxiv.org/abs/2512.20908
[arXiv 2510.16968]: https://arxiv.org/abs/2510.16968
[arXiv 2602.03812]: https://arxiv.org/abs/2602.03812
[arXiv 1503.02531]: https://arxiv.org/abs/1503.02531
[arXiv 2501.12948]: https://arxiv.org/abs/2501.12948
