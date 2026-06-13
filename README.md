<div align="center">
<h1>OpenBench</h1>

<b>A benchmark that infers what reward an LLM was RL-trained on — by watching how it codes.</b>

<p>
<a href="#"><img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python 3.12+"></a>
<a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License"></a>
<a href="#development"><img src="https://img.shields.io/badge/tests-140%20passing-brightgreen.svg" alt="Tests"></a>
<a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff"></a>
<a href="docs/EXPERIMENTS.md"><img src="https://img.shields.io/badge/experiments-pre--registered-orange.svg" alt="Pre-registered"></a>
<a href="#status"><img src="https://img.shields.io/badge/status-research%20preview-yellow.svg" alt="Status"></a>
</p>

<p>
<a href="#overview">Overview</a> ·
<a href="#key-findings">Findings</a> ·
<a href="#installation">Install</a> ·
<a href="#quick-start">Quick start</a> ·
<a href="#how-it-works">Method</a> ·
<a href="docs/EXPERIMENTS.md">Experiments</a> ·
<a href="#citation">Cite</a>
</p>
</div>

---

## Overview

OpenBench replays *real, long, multi-feature GitHub pull requests* as agentic coding tasks, then
reads the agent's full trace — every edit, test run, retry, recall, and thinking token — to estimate
the **reward composition** behind the model's RL training. Two pillars on one pipeline:

1. **Evaluation** — can the agent deliver a *mergeable* PR? Graded the SWE-bench way: the PR's own
   tests must pass (`FAIL_TO_PASS`) and existing tests must not regress (`PASS_TO_PASS`), in a
   per-task Docker image pinned at the base commit.
2. **Reward inference** — the same trace is scored into behavioral metrics and aggregated into a
   per-model **reward fingerprint**: signatures consistent or inconsistent with documented RL reward
   designs (outcome-only RLVR, process/verifier rewards, anti-hacking penalties, length shaping,
   similarity-to-gold, rubric/GRM, context-management).

> **Epistemic stance.** These are *behavioral propensities, not recovered reward functions.*
> Cross-model claims hold only with the harness fixed. The pipeline generates and falsifies
> hypotheses — it does not identify training recipes. Every experiment is
> [pre-registered](docs/EXPERIMENTS.md) with predictions and falsification conditions committed
> before the evidence.

<div align="center">
<img src="docs/figures/e1_fingerprint_heatmap.png" width="85%" alt="Reward fingerprint heatmap across models">
<br><i>Per-model reward fingerprints — z-scored behavioral signatures across the reward-component basis.</i>
</div>

## Key findings

A 13-model, 87-run corpus (DeepSeek V3/V4, Qwen3-Coder, Kimi-K2, GLM-4.6, GPT-4.1/5/5.5, Claude
Opus 4.8) surfaced several robust, reproducible results:

- **The DeepSeek V4↔V3 differential** is the anchor result. Under a fixed harness, V4-flash runs
  tests ~7× per run and verifies before declaring done; V3 confabulates and never verifies — a
  measurable, same-family divergence in what each model was optimized for.
- **Action-grounded recall, calibrated.** A working-memory metric (acting on context dormant >10
  turns) was validated against raw chain-of-thought on the DeepSeek corpus (Spearman **ρ = 0.713**,
  within-model 0.70/0.76) — then deployed to measure recall *floors* for closed models whose
  reasoning is hidden. Long-range recall turns out to be a general property of modern agentic-RL
  models, **not** a million-token-context signature.
- **Cross-lab blind calibration.** Recipe predictions made from fingerprints *alone*, before reading
  any published training docs, scored 3/3 hits on Kimi-K2 / GLM-4.6 / Qwen3-Coder.
- **Harness validity is measurable, not assumed.** A within-model factorial showed Claude Opus's
  apparent "confabulation" under a bare text-fence scaffold is **protocol-induced** — it vanishes
  the moment Opus is given its native tool-use protocol (zero-line dream → real 130-line patches,
  tests actually run). A reminder that a black-box reward probe must control for the scaffold.

See [`docs/EXPERIMENTS.md`](docs/EXPERIMENTS.md) for the full pre-registered record and
[`docs/PAPER.md`](docs/PAPER.md) for the write-up.

<div align="center">
<img src="docs/figures/e1_composition.png" width="49%" alt="Estimated reward composition per model">
<img src="docs/figures/e3_recall.png" width="49%" alt="Context-recall fingerprint">
</div>

## Why long PRs, and why difficulty matters

Reward signatures only diverge at the **capability frontier** — where gaming a test becomes
tempting, giving up actually binds, and context outgrows the window. A task a model solves
comfortably makes every reward design look identical. So tasks are mined for size and stratified by
hardness (**Extended / Main / Diamond** tiers), and the primary statistic is each metric's *slope
across difficulty*, not any single number.

## Installation

```bash
git clone https://github.com/BrandeisPatrick/openbench.git
cd openbench
make install      # == uv sync
```

That's the whole install. Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/)
(`curl -LsSf https://astral.sh/uv/install.sh | sh`). **No keys or Docker needed** for the demo and
the test suite below — those are only required to run *new* live agents (see
[Run your own experiments](#run-your-own-experiments)).

## Try it in 60 seconds — no credentials

The whole analysis layer runs offline on stored traces, so you can see real per-model reward
fingerprints immediately, against a bundled example corpus (33 runs across 11 models):

```bash
make demo         # == uv run openbench demo   → writes examples/report.md
make test         # == uv run pytest           → 140 offline tests, no Docker/network
```

`make demo` produces a full cross-model reward-fingerprint report — composition weights, z-scored
signatures, hypothesis labels, figures — with **zero setup**. Re-run the analysis on the same
traces yourself:

```bash
OPENBENCH_ROOT=examples uv run openbench analyze   # recompute metrics from the example transcripts
```

| What you have | What you can run |
|---|---|
| **nothing** | `make demo`, `make test`, `openbench analyze` on the example corpus |
| **+ Docker** | the `golden` / `null` fixtures — the full grade pipeline on a real task, no model key |
| **+ one model key** | run a real agent end-to-end (`openbench run … --model …`) |
| **+ GitHub token** | mine and build your own tasks from any repo |

## Run your own experiments

Add credentials only for the step you need (`cp .env.example .env`, then fill in what you have —
a GitHub token to mine, and/or one model API key to run an agent):

```bash
uv run openbench mine                                           # → candidates, hardness tiers
uv run openbench build-task --repo sympy/sympy --pr 28109       # → prompt, gold/test patches, F2P
uv run openbench build-env  sympy__sympy-28109                  # → pinned Docker image
uv run openbench validate   sympy__sympy-28109                  # → base-fails / merged-passes gate
uv run openbench run        sympy__sympy-28109 \
      --runner mini-swe --model deepseek-v4-pro --max-turns 150 # → transcript (sandboxed)
uv run openbench grade      <run_id>                            # → resolved? F2P/P2P, anti-cheat
uv run openbench analyze                                        # → metrics, reward scores → DuckDB
uv run openbench report                                         # → cross-model markdown report
```

The pipeline at a glance:

```
mine ──▶ build-task ──▶ validate ──▶ build-env ──▶ run ──▶ grade ──▶ analyze ──▶ report
 │           │             │            │           │        │          │           │
 GraphQL   prompt +      base-fails/  per-task    agent    apply +    behavioral  fingerprints
 + filters gold/test     merged-      Docker      harness  anti-cheat metrics +   + reward
 + tiers   split         passes ×3    image       (sandbox)+ F2P/P2P  reward score estimates
```

## Runners (agent harnesses)

| runner | models | notes |
|---|---|---|
| `mini-swe` | **any** OpenAI-compatible API (DeepSeek, OpenRouter → Qwen/Llama/GLM, OpenAI, Moonshot) | minimal one-command-per-turn ReAct loop; the **cross-model** harness |
| `claude-native` | Anthropic Messages API | native structured tool-use + extended thinking; the **correct scaffold for Claude** ([scaffold experiment](docs/EXPERIMENTS.md)) |
| `claude-code` | Anthropic only | rich scaffold (`claude -p` headless); a separate "scaffold strength" axis |
| `golden` / `null` | — | CI fixtures: golden applies the real patch (must resolve), null no-ops (must not) |

The LLM API is called from the host; the task container runs **network-isolated**, so the agent
can't reach the internet and keys never enter the sandbox.

## How it works

### Reward estimation, three tiers

1. **Consistency labels** — z-scored metrics cross a threshold → hedged "consistent with X" labels
   (`analysis/fingerprint.py`).
2. **Mixture estimation** — model the reward as `R = Σ wᵢ·componentᵢ`; recover `w ≥ 0` via
   non-negative least squares against a signature matrix, with bootstrap CIs and collinearity
   (identifiability) warnings (`analysis/estimate.py`). A second, assumption-light estimator scores
   each *realized* counterfactual reward on the actual trajectory (`analysis/reward_scoring.py`) as a
   cross-check.
3. **Probes & calibration** — honeypot/impossible probes break collinear ties; the signature matrix
   is validated against models run with *known* rewards (designed).

### Length-invariance

Only rates, ratios, and booleans enter the fingerprint — never raw counts — so a verbose model and a
terse one are scored on the same footing. A guard (`_assert_length_invariant`) fails fast if a
non-invariant metric is ever added to the signature matrix.

### Probes

Passive observation can't separate every reward family ("never games" vs "penalized for gaming" look
identical). Probes manufacture the divergence:

- **Honeypot** — weak *visible* smoke tests, strict *hidden* grading. Exploiting the cheap bar ⇒
  outcome-reward without an anti-hacking penalty. Tampering with the bait is detected and reverted.
- **Impossible** — a self-contradictory spec. Pushing back vs comply-and-fake measures
  sycophancy-to-spec.
- **Scaffold factorial** — the same model under text-fence vs native tool-use, thinking on vs off, to
  separate reward signatures from harness artifacts.

### Anti-cheat

Every existing/gold test file is SHA-256 pinned. Agent edits to them are **reverted before grading**
(tampering can never raise a score) and recorded as first-class gaming signals for the reward
analysis.

## Repository layout

```
src/openbench/
  mining/     GitHub GraphQL mining · super-long-PR filters · hardness tiers
  tasks/      prompt construction (leakage-stripped) · F2P/P2P split · validation gate
              · honeypot & impossible probe generators
  envs/       per-task Docker images pinned at the base commit
  runners/    AgentRunner protocol · mini-swe (multi-provider) · claude-native · claude-code · fixtures · sandbox
  grading/    mergeability sequence · anti-cheat · rubric judge
  traces/     normalized TraceEvent stream · per-harness adapters · JSONL + DuckDB store
  analysis/   behavioral metrics · reward-mixture estimator · realized reward scoring · stats
  report/     markdown + figure generation
docs/
  RESEARCH.md       hypotheses · reward-estimation method · probe designs · references
  EXPERIMENTS.md    pre-registered experiments — data · method · expected result · status
  PAPER.md          short paper write-up
configs/            mining thresholds, hardness weights, grading & rubric config
```

## Development

```bash
uv run pytest            # 140 offline tests (no Docker / network)
uv run ruff check        # lint
```

Offline tests cover every pure component (filters, hardness, F2P split, anti-cheat, metrics,
estimator, probes, trace adapters, recall calibration); Docker-dependent steps are exercised by the
golden/null fixtures against a real task. Bugs that once produced *wrong results* are pinned by
regression guards in `tests/test_bug_regressions.py`.

## Status

Research preview. The method is a hypothesis-generating instrument pending a known-reward
ground-truth calibration; results are honest about their confounds (small *n*, single-repo task
family, hand-designed signature matrix, scaffold sensitivity). See the limitations sections in
[`docs/PAPER.md`](docs/PAPER.md) and [`docs/EXPERIMENTS.md`](docs/EXPERIMENTS.md). Some
provider-hosted models may be intermittently unavailable; the analysis pipeline runs entirely
offline on stored traces.

## Citation

```bibtex
@software{openbench2026,
  title  = {OpenBench: Inferring RL Reward Composition from Black-Box Agent Behavior},
  author = {OpenBench contributors},
  year   = {2026},
  url    = {https://github.com/BrandeisPatrick/openbench}
}
```

## Acknowledgements

Task construction and grading follow the [SWE-bench](https://www.swebench.com/) methodology.
Hardness tiering is inspired by FrontierCode-style stratification. See
[`docs/RESEARCH.md`](docs/RESEARCH.md) for the full reference list behind each hypothesis.

## License

MIT — see [`LICENSE`](LICENSE).
