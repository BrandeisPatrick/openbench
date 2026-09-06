# Research proposal: reasoning-pattern change across post-training generations — Kimi-first design

Status: proposal for pre-registration, 2026-09-04. Nothing here is a result.
Every number quoted from our corpus is exploratory (4 task clusters) and is
cited only to motivate a hypothesis or a control. Metrics named below are to
be fixed in code before any result is inspected, as `analysis/convergence.py`
and `analysis/verify_findings.py` were.

Background documents: [literature map](literature-map-post-training-signatures.md)
(lab-claimed techniques and detection methods), [reasoning-pattern map](reasoning-pattern-literature-map.md)
(159 verified papers; layered coding scheme in its §4), [findings verification](findings-verification-2026-08.md)
(what survived adversarial checks on the current corpus).

## 1. Research question

**Primary.** Within one lab's lineage of reasoning models, run under one fixed
coding-agent harness, what changes in how the model *reasons* (chain-of-thought
content), *acts* (command trajectory) and *converges* (across repeats) from one
post-training generation to the next — and which of those changes match the
techniques the lab says it added?

**Why Kimi first.** The Kimi lineage — k2-thinking (Nov 2025, reasoning
specialist) → k2.6 (generalist) → k3 (nine in-house teachers, three
reasoning-effort levels, distilled into one model) — is the only lineage where
all three kinds of pattern are measurable: raw chain-of-thought for every
generation, complete command logs, and both solved and failed cells. It carries
our strongest exploratory result (the V-shape: byte-identical patches from
divergent reasoning at k2-thinking, lost at k2.6, partly recovered at k3), it
exposes instruments the other labs do not (an effort knob the lab claims to have
trained in; thinking that can be switched off; open weights for k2-thinking),
and it is cheap enough to expand.

**Replication and port.** DeepSeek r1-0528 → v3.2 → v4-pro is the replication
lineage (raw CoT, same protocol). OpenAI o1 → o3 → gpt-5.5 receives only the
action-side modules at the end, because its reasoning channel is a summary.

## 2. Starting point (verified, exploratory)

| finding | status after verification | role in this proposal |
|---|---|---|
| D1 gains are reliability not capability | demoted: Pass@3 saturated (Kimi 4/4 at every generation) | motivates the expansion |
| D2 task-directed procedure concentration rises with generation | survives a style-vs-task baseline; old models' convergence is mostly generic style | H3 |
| D3 k2-thinking: divergent reasoning → identical patches; k2.6 loses it; k3 partly recovers | strengthened (stochastic serving confirmed); host asterisk on k2-thinking→k2.6 | H3, Phase 0 |
| D4 output compression on solved runs: DeepSeek 3×, OpenAI 4×, Kimi flat | revised to solved-runs-only form | H1 |
| D5 failures scatter, never the same wrong patch | survives exactly | covariate |
| D6 low gold-similarity mixes alternative mechanisms with collateral | demoted to per-task mechanism classification | Layer A code |

Gap this study occupies (confirmed by the pattern map §5a): no published work
follows one lab's models across generations on reasoning-trace content under a
fixed harness.

## 3. Hypotheses

Each hypothesis states a prediction, at least one rival that predicts the
opposite or the same sign for a different reason, and the null that would be
reported as the result if the prediction fails. Signs are stated for the Kimi
lineage; DeepSeek predictions are noted where they differ.

**H1 — Compression is a thinking-vs-doing change located after commitment.**
Define the *commitment prefix* of a run as the first turn at which the final
patch's edit set is fully present in the working tree. Prediction: on solved
runs, the share of turns and reasoning characters spent *after* the commitment
prefix falls from k2-thinking to k3, and tokens-per-action falls while the
number of actions holds. Rival: compression is uniform across the whole run
(pure verbosity change). Null: no generation difference in post-commitment
share once turn-cap and cost-cap runs are excluded. DeepSeek prediction:
strongest g2→g3 effect (v3.2's 100-turn grinds are post-commitment tails).

**H2 — Verification claims and verification actions decouple in the weaker
generation.** Define *claims-per-test* as verification statements in reasoning
(lexicon, dual-scored by regex and a fixed-prompt judge) divided by executed
test commands; define the *unsupported completion rate* on the visible final
message (claims of verification with no corresponding executed test).
Prediction: k2.6 shows a higher claims-per-test ratio and unsupported completion
rate than k2-thinking and k3, tracking its solve-rate dip; all Kimi generations
remain far below r1 (illustrative one-task values: Kimi ≈ 1 claim per test,
r1 8–24). Rival: the ratio tracks reasoning length, not generation (the
length-adjustment gate decides). Null: ratios are indistinguishable across Kimi
generations, i.e. the dip is not a verification failure.

**H3 — Concentration is outcome-space collapse with path diversity, and the
rivals can be told apart.** Per cell, compute *outcome entropy* (distinct
behavioural equivalence classes among solved patches) and *path entropy*
(distinct command-sequence classes), plus the existing within-cell-minus-
cross-task procedure margin. Prediction (RLVR/distillation sharpening):
outcome entropy collapses before path entropy — the k2-thinking profile —
and k3's recovery is procedural (path entropy falls) rather than
outcome-level. Rivals, each with its discriminating observable: memorisation
(converged patch is gold-identical and modal across labs; screened by the
contamination covariates), teacher inheritance (k3's modal patch coincides
with k2-thinking's; note K3's teachers are in-house specialists, so this is
conditional), solvability (concentration merely tracks solve rate; everything
is reported conditional on solved pairs), non-monotonicity (the V-shape is
predicted by the literature's mode-collapse work and is not evidence against
sharpening). Null: outcome and path entropy move together at every generation.

**H4 — Reasoning-content profiles shift across generations beyond length
(Kimi and DeepSeek only).** Using the pattern map's Layer B: operator/episode
histograms per turn, backtracking and verification densities per 10k
characters and per command, and the PUMA-style novelty-decay profile
(converge-then-stop vs loop-past-convergence vs stop-before-convergence).
Prediction is deliberately two-sided: the within-cell vs cross-task profile
margin may rise with generation in step with the action-side margin, or fall
because stronger models verbalise less. Null: profiles are task-invariant
style at every generation (cross-task divergence ≈ within-cell divergence),
in which case reasoning content carries no procedure signal and D2 is
action-only. Distinct sub-prediction for the r1/v3.2 pair: r1 = stop before
convergence with few actions; v3.2 = loop past convergence.

**H5 — Effort conditioning produces discrete modes, not a volume dial
(Kimi instrument).** Run k3 at reasoning_effort low / high / max. Prediction
from the K3 report (three effort levels distilled in): action-side profiles
(Layer A) differ discretely between levels, not just reasoning volume.
Rival (literature): effort acts as a ceiling — equal or worse accuracy in most
settings, with only volume changing. Null: only reasoning tokens change.

**H6 — Necessity control (gate for every CoT claim).** For each task, run
thinking-off (k2.6, k3; DeepSeek non-thinking) and compute the pass-rate gap
versus thinking-on. Reasoning-content claims (H2, H4) are licensed only on
tasks with a material gap; on tasks where thinking does not change outcomes,
the CoT is treated as rationalisation and H2/H4 results are reported as
descriptive only. Expectation: the current four tasks may fail this gate.

## 4. Design

### Phase 0 — lineage hygiene (small spend, first)
- Host-matched rerun: k2.6 and k3 via OpenRouter on the four current tasks,
  K=3 (24 runs), so all three Kimi generations share one host. First-party
  k2.6/k3 runs are retained as a separate condition. Record serving provider,
  sampling defaults where the API reports them, request date and any version
  string per run (version-drift log).
- Pull CoT-shaping covariates from the K2-thinking, K2.6 and K3 reports
  (length penalty? language-consistency reward?) and from DeepSeek's
  (V3.2: both). Documentation, not estimable.

### Phase 1 — zero-spend analysis on the frozen corpus
Layer A and Layer B on the six raw-CoT models (Kimi 3, DeepSeek 3), gates
before lexicons, H1–H4 as an exploratory pass labelled as such. Purpose: fix
metric code, calibrate judges, estimate variance components for Phase 2 sizing.

### Phase 2 — Kimi-targeted expansion (confirmatory)
- Task selection rule, fixed before any run: from the 51 built candidates,
  keep tasks that pass `openbench golden-gate` on freshly built images, carry a
  SWE-bench Verified human difficulty label of 15 min–1 h or 1–4 h, and are
  not among the current four; at most three per repository; target 16–20
  tasks. No pilot-based selection.
- Runs: all three Kimi generations on one host, K=3 everywhere; K=8 on a
  six-task subset for pass@k envelopes, mode accuracy and entropy estimates.
- DeepSeek replication on the same tasks, K=3.
- Caps: token-based, identical across arms.

### Phase 3 — Kimi instruments
- H5: k3 at low / high / max on the K=8 subset (three levels × six tasks × K=3).
- H6: thinking-off runs for k2.6, k3 and DeepSeek on all expansion tasks, K=3.

### Phase 4 — OpenAI port
Layer A, the action-fed Kind-3 tests (H1 on billed tokens, H3, unsupported
completion rate on visible messages), the effort analogue of H5, and the
statistics module — on the existing o1/o3/gpt-5.5 runs and, budget permitting,
on the expansion tasks.

## 5. Measures (to be fixed in code before results)

**Layer A — action channel, all models, deterministic.** X/E/P/V lettering of
each command; composition consistency (Jensen–Shannon divergence over verb
histograms) and ordering consistency (sequence alignment) across repeats, with
the cross-task baseline subtracted; commitment prefix and post-commitment
share; edit→verify transition probability; unsupported completion rate on the
visible final message; tokens-per-action; termination class (submitted /
turn-cap / cost-cap); behavioural equivalence classes of solved patches
(differential-test based where feasible, edit-set identity otherwise);
gold-identity rate and cross-lab modal-patch share (contamination covariates);
mechanism-vs-gold classification per task (D6 code).

**Layer B — raw CoT, Kimi and DeepSeek only.** Gates first: legibility (chunk
level), language mixing (code and paths stripped), classifier sensitivity
(regex vs judge range and per-category agreement; drop categories with
κ < 0.2), length adjustment (every rate per 10k characters as well as raw),
CoT-shaping covariate. Then: verification / backtracking / planning lexicon
densities; claims-per-test; plan-to-next-action agreement; operator or
episode histograms with within-cell vs cross-task divergence; PUMA-style
per-step semantic-novelty profile and its convergence class.

**Layer C — judge coding, second pass, costs spend.** ThinkARM's eight
episodes with Implement grounded to command emission; judge from outside the
lineage under study; human-coded calibration subset (about 20 turns per
lineage) with Cohen's κ, replicates at temperature 0, length-matched check.
Differences below the judge–human agreement floor are not read.

**OpenAI rule.** Presence claims only, and only when the next command
corroborates the summary. No frequencies, rates, or absence claims on
summaries. Volume in billed output tokens.

## 6. Analysis plan and decision rules

- Comparisons are within-lineage only; cross-lab numbers are descriptive.
- Every CoT-side rate is reported beside its action-side twin; a CoT-side
  effect with no action-side counterpart is reported as unsupported.
- Statistics: task-clustered, task-paired standard errors; Beta-Binomial
  outcome model with task random effects and task×generation terms; Beta
  likelihood for similarities, log-normal for tokens; effective task count
  computed by repository cluster; pass@k and pass^k envelopes rather than bare
  pass@1 differences; exact intervals for identity counts and zero counts.
- Pre-set thresholds (mirroring the ≥0.10 margin rule already used): each
  hypothesis carries a minimum effect size in its metric's units and a
  direction; these are written into the analysis code header before Phase 2
  results exist.
- Order of operations: gates → contamination covariates → Layer A → Layer B
  → Layer C. H2/H4 are read only on tasks passing H6.
- Null-tested variables (negative result is the reported alternative):
  reflection density, test-writing rate, backtrack fraction, reasoning
  effort, capability–monitorability, self-correction markers.
- Confirmation criterion for Phase 2: the Phase-1 sign holds on the expansion
  tasks with the pre-set minimum effect and the interval excluding zero under
  the clustered model; anything else is reported as not confirmed.

## 7. Threats to validity and how each is handled

| threat | handling |
|---|---|
| host / sampling-default differences across generations | Phase 0 host matching; provider and date recorded; first-party runs kept as a separate condition |
| served-model version drift within a collection window | per-run date and version string; window span reported per model |
| benchmark contamination (SWE-bench Verified is public) | gold-identity and cross-lab modal-share covariates reported before D2/D3 interpretation; a null is not evidence of no contamination |
| CoT shaping in training (length penalties, language rewards) | documented per model from lab reports; r1→v3.2 verbalisation changes flagged as confounded |
| CoT unfaithfulness | action-twin rule; H6 necessity gate; presence-only rule for summaries |
| judge validity | outside-lineage judge; human calibration subset; κ thresholds; length-matched checks |
| task saturation | expansion selection rule targets interior solve rates; K=8 subset |
| small N | clustered/paired inference; effect sizes with intervals; no significance language on 4 tasks |
| cap asymmetry and cost accounting | token-based uniform caps; cost recomputed from tokens with cache pricing |

## 8. Budget and sequence (rough, from observed per-run costs)

| phase | runs | estimate |
|---|---|---|
| 0 host-matched Kimi rerun | 24 | $10–30 |
| 1 frozen-corpus analysis | 0 | $0 (judge calibration in Layer C: $10–30) |
| 2 Kimi expansion, 3 gens × ~18 tasks × K=3, plus K=8 on 6 tasks | ~250 | $150–350 |
| 2 DeepSeek replication, same tasks, K=3 | ~160 | $150–300 (r1 is slow; wall-clock, not dollars, is the constraint) |
| 3 effort knob (k3, 3 levels × 6 tasks × K=3) + thinking-off (3 models × ~18 × K=3) | ~215 | $100–200 |
| 4 OpenAI port on existing data | 0 | $0; expansion for OpenAI deferred (o1 pricing) |

Total for Phases 0–3: roughly $400–900, spread over several weeks; Phase 2
DeepSeek and Phase 3 can be trimmed independently.

## 9. Deliverables

1. This proposal, revised into a pre-registration with thresholds filled in
   and committed before Phase 2 runs.
2. Analysis code with definitions fixed in headers (`analysis/`), one module
   per layer; the action modules must run unchanged on OpenAI data.
3. A results document per phase in `docs/`, each labelled exploratory or
   confirmatory, with a corrections ledger.
4. The GPT-lineage port as the final chapter, reusing Layer A and the
   statistics module verbatim.

## 10. What this study will not claim

- That any model "has a new reasoning pattern" from CoT text alone.
- Cross-lab rankings on CoT-content metrics (channel observability differs).
- Causal attribution of a trace change to a named training technique; the
  most this design supports is "consistent with the lab's claimed addition,
  and inconsistent with rivals R1…Rn as pre-registered."
- Anything on OpenAI reasoning content beyond corroborated presence.
