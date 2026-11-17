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
network-isolated Docker per task, FAIL_TO_PASS / PASS_TO_PASS grading) and keeps the agent's
full transcript: every command, its output, and the model's thinking. It is used to find
**patterns in how coding agents work** and how they move across model generations, effort
settings and model sizes, not to rank models.

Solve rate is one column, not the story. The measures are command habits read from the
transcript by fixed rules: how many commands a run takes, when the first edit comes, how
much of the work is testing, whether a new test is written, how large the patch is and how
many files it touches beyond the fix, and whether "done" follows a passing test. Ordered
comparisons stay within one lab and one request shape, are tested per task with a
pre-registered trend test, and every experiment is written down before it runs.

Round 2 (132 runs: five Opus generations, four effort levels, four model sizes) found that
patch size and extra files grow with newer generation, more effort and larger size alike,
while shorter runs and earlier editing follow the generation only. Experiments, data and
results are in [`research/`](research/README.md).

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
mine ──▶ build-task ──▶ validate ──▶ build-env ──▶ run ──▶ grade ──▶ research/analysis
 │           │             │            │           │        │              │
 GraphQL   prompt +      base-fails/  per-task    agent    apply +       command-habit
 + filters gold/test     merged-      Docker      harness  anti-cheat    measures, trend
 + tiers   split         passes ×3    image       (sandbox)+ F2P/P2P     tests (offline)
```

### Repository layout

```
src/openbench/
  mining/     GitHub GraphQL mining · long-PR filters · hardness tiers
  tasks/      prompt construction (leakage-stripped) · F2P/P2P split · validation gate
  envs/       per-task Docker images pinned at the base commit
  runners/    AgentRunner protocol · unified harness · protocol routing · sandbox ·
              round runner (pre-registered batches under a spending cap)
  grading/    mergeability sequence · anti-cheat
configs/      mining thresholds, hardness weights, grading config
datasets/     tasks (prompt, gold and test patch, task.json) · quarantined tasks
research/     experiments, frozen run corpora, analysis code, results
reports/      literature reports on agent pattern discovery (notes in research_notes/)
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
| **+ one model key** | run a real agent end-to-end and grade it |
| **+ GitHub token** | mine and build your own tasks from any repo |

### Run an agent on a task

Add credentials for the step you need (`cp .env.example .env`, then fill in what you have):

```bash
uv run openbench build-env  sympy__sympy-22914               # → pinned Docker image
uv run openbench run        sympy__sympy-22914 \
      --runner native --model deepseek-v4-pro --max-turns 100 # → transcript (sandboxed)
uv run openbench grade      <run_id>                          # → resolved? F2P/P2P, anti-cheat
```

`run-matrix --reps 3` batches (task × model × repetition) cells with per-run isolation.
`run-round` runs a pre-registered round from its `round.json` under a hard spending cap,
stage by stage or one task at a time (`--task`). The analyses in `research/analysis/` run
offline on stored runs, with no keys or Docker.

### Development

```bash
uv run pytest            # offline tests (no Docker / network)
uv run ruff check        # lint
```

Offline tests cover every pure component (filters, hardness, F2P split, anti-cheat, the
protocols and harness loop, the round runner, the command-audit measures and trend tests,
the judge passes). Docker-dependent steps are exercised by the
`golden` / `null` CI fixtures against a real task — `golden` applies the real patch and must
resolve, `null` no-ops and must not — so the grade pipeline is validated without a model key.
Bugs that once produced *wrong results* are pinned by regression guards in
`tests/test_bug_regressions.py`.

## Status

Research preview. Results are descriptive patterns under one fixed harness, with few tasks
per round, so only strong and consistent effects can pass the tests. The command-coding
rules are not yet checked against hand labels. The analyses run entirely offline on the
stored runs.

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
