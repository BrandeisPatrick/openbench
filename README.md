<div align="center">
<h1>OpenBench</h1>

<b>How did coding agents change between model generations? A behavioral comparison harness.</b>

<p>
<a href="#"><img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python 3.12+"></a>
<a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License"></a>
<a href="#status"><img src="https://img.shields.io/badge/status-research%20preview-yellow.svg" alt="Status"></a>
</p>

<p>
<a href="#what-openbench-measures">What it measures</a> ·
<a href="#methods">Methods</a> ·
<a href="#how-to-self-run">Self-run</a> ·
<a href="#citation">Cite</a>
</p>
</div>

---

## What OpenBench measures

OpenBench replays *real GitHub pull requests* as agentic coding tasks (the SWE-bench way:
network-isolated Docker per task, FAIL_TO_PASS / PASS_TO_PASS grading) and reads the agent's
full trace — every edit, test run, retry, and command — to characterize **how agent behavior
differs between model generations** within the same lab:

- **DeepSeek:** `deepseek-chat-v3-0324` (old) → `deepseek-v4` (new)
- **OpenAI:** `gpt-4.1` (old) → `gpt-5.5` (new)

Solve rate is one column, not the story. The study compares behavioral profiles across four
axes, each computed deterministically from the normalized trace:

1. **Verification & testing** — does the model run tests, reproduce before editing, iterate
   failing suites to green, and end on a verified state?
2. **Persistence & recovery** — recovery from failing tests, verbatim retries, giving up on
   red, grinding to the turn/cost cap, early stopping.
3. **Exploration & context use** — search-before-edit discipline, exploration share of the
   action budget, breadth of codebase contact, re-reading behavior.
4. **Efficiency & scope** — turns/tokens/cost to completion, diff size vs the human gold
   patch, out-of-scope edits, edit churn.

Plus failure modes as first-class results: confabulated completion (declares done having
never seen a green test), malformed protocol actions, crash rates.

Comparisons are **within-lab, task-paired**: each (old, new) pair runs the same tasks on the
same wire protocol, so scaffold effects cancel inside a pair. Statistics are honest for small
n — Cliff's delta with task-clustered bootstrap CIs and per-task sign agreement, stratified
by contamination (pre-cutoff SWE-bench Verified vs post-cutoff mined tasks).

## Methods

### Task suite

Tasks come from two sources (see [`datasets/tasks/README.md`](datasets/tasks/README.md)):
SWE-bench Verified imports (human-annotated difficulty) and PRs mined from GitHub after
2025-06 (post-training-cutoff for the older generation — a clean contamination stratum).
Every task carries a difficulty label on the shared scale (`<15 min` → `>4 hours`), so
behavior can be read across a difficulty spread, not one point.

### Anti-cheat

Every existing/gold test file is SHA-256 pinned. Agent edits to them are **reverted before
grading** (tampering can never raise a score) and recorded as first-class behavioral signals.

### Runners (agent harnesses)

One harness loop with pluggable wire protocols, routed per model family:

| protocol | models | notes |
|---|---|---|
| `tooluse` | any OpenAI-compatible API (DeepSeek, OpenRouter → Qwen/GLM/Kimi, Moonshot) | native function calling, `reasoning_content` capture |
| `gpt-responses` | OpenAI (`gpt-*`) | Responses API, reasoning summaries where available |
| `claude-native` | Anthropic Messages API | structured tool-use + extended thinking |
| `mini-swe` | any | minimal text-fence ReAct loop (legacy baseline) |

The LLM API is called from the host; the task container runs **network-isolated**, so the
agent can't reach the internet and keys never enter the sandbox.

### The pipeline at a glance

```
mine ──▶ build-task ──▶ validate ──▶ build-env ──▶ run ──▶ grade ──▶ behavior ──▶ compare
 │           │             │            │           │        │          │            │
 GraphQL   prompt +      base-fails/  per-task    agent    apply +    per-run     generational
 + filters gold/test     merged-      Docker      harness  anti-cheat behavior    deltas +
 + tiers   split         passes ×3    image       (sandbox)+ F2P/P2P  profile     report
```

### Repository layout

```
src/openbench/
  mining/     GitHub GraphQL mining · long-PR filters · hardness tiers
  tasks/      prompt construction (leakage-stripped) · F2P/P2P split · validation gate
  envs/       per-task Docker images pinned at the base commit
  runners/    AgentRunner protocol · unified harness · protocol routing · sandbox
  grading/    mergeability sequence · anti-cheat
  traces/     normalized TraceEvent stream · per-harness adapters · JSONL + DuckDB store
  behavior/   per-run behavior profiles · generational comparison · report
configs/      mining thresholds, hardness weights, grading config
```

## How to self-run

### Install

```bash
git clone https://github.com/BrandeisPatrick/openbench.git
cd openbench
make install      # == uv sync
```

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/)
(`curl -LsSf https://astral.sh/uv/install.sh | sh`). **No keys or Docker needed** to install
or to run the offline test suite.

| What you have | What you can run |
|---|---|
| **nothing** | `make test` — the full offline test suite |
| **+ Docker** | the `golden` / `null` fixtures — the full grade pipeline on a real task, no model key |
| **+ one model key** | run a real agent end-to-end, then profile + compare offline |
| **+ GitHub token** | mine and build your own tasks from any repo |

### Run the generational study

Add credentials for the step you need (`cp .env.example .env`, then fill in what you have):

```bash
uv run openbench build-env  sympy__sympy-22914               # → pinned Docker image
uv run openbench run        sympy__sympy-22914 \
      --runner native --model deepseek-v4-pro --max-turns 100 # → transcript (sandboxed)
uv run openbench grade      <run_id>                          # → resolved? F2P/P2P, anti-cheat
uv run openbench behavior   <run_id>                          # → behavior profile (offline)
uv run openbench compare --pair deepseek --pair gpt           # → generational report (offline)
```

`run-matrix --reps 3` batches (task × model × repetition) cells with per-run isolation.
The profile/compare layer is fully offline — it reads stored traces, no keys or Docker.

### Development

```bash
uv run pytest            # offline tests (no Docker / network)
uv run ruff check        # lint
```

Offline tests cover every pure component (filters, hardness, F2P split, anti-cheat, behavior
metrics, comparison stats, trace adapters). Docker-dependent steps are exercised by the
`golden` / `null` CI fixtures against a real task — `golden` applies the real patch and must
resolve, `null` no-ops and must not — so the grade pipeline is validated without a model key.
Bugs that once produced *wrong results* are pinned by regression guards in
`tests/test_bug_regressions.py`.

## Status

Research preview. Results are descriptive comparisons under a fixed harness, honest about
small n (task-clustered CIs, per-task sign agreement, contamination strata). Some
provider-hosted models may be intermittently unavailable; the analysis layer runs entirely
offline on stored traces.

## Citation

```bibtex
@software{openbench2026,
  title  = {OpenBench: Behavioral Comparison of Coding-Agent Model Generations},
  author = {OpenBench contributors},
  year   = {2026},
  url    = {https://github.com/BrandeisPatrick/openbench}
}
```

## Acknowledgements

Task construction and grading follow the [SWE-bench](https://www.swebench.com/) methodology.
Hardness tiering is inspired by [FrontierCode](https://cognition.ai/blog/frontier-code)-style
stratification.

## License

MIT — see [`LICENSE`](LICENSE).
