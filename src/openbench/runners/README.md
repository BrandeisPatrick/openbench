# OpenBench Harness

A **minimal, sandboxed, multi-vendor coding-agent harness**. It turns *a task +
a model* into *a behavior transcript* — nothing more. It is the measurement
instrument for OpenBench's reward-fingerprint analysis, and is designed so the
harness contributes as little of its own behavior as possible: what you measure
is the model's propensities, not the scaffold's.

> Status: lives inside `openbench` today (`src/openbench/runners/` + `envs/builder.py`,
> `dockerutil.py`, `sandbox.py`). The public contract below is stable; it is intended
> to be promotable to a standalone package/repo that OpenBench cites by version.

---

## Design philosophy

- **Native tool-use, one bash tool.** The agent gets exactly one affordance —
  run one bash command in `/repo` — exposed through each model's *native* tool
  protocol. The API ends the turn at the tool call, so a tool-trained model
  cannot over-generate / fabricate a session (the "dream"). One command per turn.
- **Minimal, not rich.** No planning loops, no multi-tool scaffolds, no long
  system prompts. A rich scaffold injects behavior that isn't the model's reward
  fingerprint; this harness deliberately stays bare.
- **Multi-vendor on one protocol.** Every model runs *minimal native tool-use*;
  only the wire format differs per provider (dispatched automatically).
- **Offline by construction.** The task container runs `network=none`; the LLM API
  is called from the **host**, so the key never enters the container and the agent
  has no internet.
- **One transcript schema for all runners**, so a single downstream adapter
  normalizes every run — only the model's behavior differs, not the parsing.

---

## Runners

`get_runner(name)` (`__init__.py`) returns one of:

| name | what it is | use |
|---|---|---|
| **`native`** | **common harness** — dispatches by model to the right native tool-use transport | **default; use this** |
| `tooluse` | OpenAI-compatible function-calling (`/chat/completions` + `tools`) | DeepSeek / GPT / Qwen / GLM / Kimi, incl. `openrouter/*` |
| `claude-native` | Anthropic Messages API native `tool_use` + extended thinking | Anthropic (`claude*`) |
| `mini-swe` | legacy text-fence (one ```bash block parsed from free text) | baseline / comparison only — OOD for tool-trained models |
| `claude-code` | the real Claude Code CLI (rich scaffold) | optional |
| `golden` / `null` | CI fixtures (apply gold patch / no-op) | grading controls, tests |

`native` routing: `model.startswith("claude")` → `claude-native`; everything else
→ `tooluse`. Both write the same transcript schema; `execute_run` records
`harness="native"` uniformly, so analysis groups runs per model.

---

## The contract

```
INPUT   Task (repo, base_commit, prompt, image_tag) + model + RunLimits + a started container
RUNNER  one bash tool, one command/turn, until DONE marker / cap
OUTPUT  raw_transcript.jsonl  (the schema below)  +  (ExitReason, usage_totals)
```

Every runner implements the `AgentRunner` protocol (`base.py`):

```python
class AgentRunner(Protocol):
    name: str
    needs_network: bool   # harness runners are False (API called host-side)
    def run(self, task: Task, container: str, run_path: Path,
            model: str, limits: RunLimits) -> tuple[ExitReason, dict]: ...
```

`ExitReason` = `completed | timeout | cost_cap | turn_cap | crash`.
`usage` dict keys = `cost_usd, tokens_in, tokens_out, tokens_thinking, num_turns`.

**Producer/consumer seam:** the harness *writes* the transcript and owns its
schema; consumers (grading, analysis) *read* it via their own adapter
(`traces/adapters/transcript.py`). They agree only on the JSONL format below.

---

## Transcript schema (`raw_transcript.jsonl`)

One JSON object per line:

```jsonc
{"type": "meta",  "model": "...", "task_id": "...", "scaffold": "tooluse"}      // first line
{"type": "api_response", "turn": 1, "content": "...", "reasoning_content": "...",
 "usage": {"prompt_tokens": 0, "completion_tokens": 0}}                         // one per model turn
{"type": "exec",  "turn": 1, "command": "...", "exit_code": 0, "output": "..."} // when a command ran
{"type": "final", "exit_reason": "...", "turns": n, "usage_totals": {...}}      // last line
```

- `content` = assistant text; `reasoning_content` = thinking/reasoning text (empty
  if the provider doesn't return it). Output is truncated to a cap.
- A `DONE` turn (`echo OPENBENCH_DONE`) records an `exec` with `output:
  "OPENBENCH_DONE"` and sets `exit_reason: "completed"`.

---

## Sandbox & provider routing

- **Container:** `execute_run` builds a per-task image (`envs/builder.py`,
  `Dockerfile.j2` pins `repo@base_commit`), starts it `network=none`, copies the
  prompt in, runs the agent as the non-root `agent` user, snapshots
  `workspace.patch`, writes `run.json`.
- **Per-task python base:** `Task.base_image` (default `python:3.12-slim`) — set an
  older python for old commits (e.g. `python:3.9-slim` for pre-3.10 code doing
  `from collections import Mapping`), else the lib won't import.
- **Providers** (`common.PROVIDERS`, longest-prefix wins):
  `openrouter/` → OpenRouter · `deepseek` → DeepSeek · `gpt` → OpenAI ·
  `kimi` → Moonshot · `claude` → Anthropic. Keys read from env
  (`OPENROUTER_API_KEY`, `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `MOONSHOT_API_KEY`,
  `ANTHROPIC_API_KEY`).

---

## Limits & cost control

`RunLimits(wall_clock_s, max_turns, max_cost_usd)` — a run stops at whichever cap
it hits first. For matrices, set caps **per model** in `configs/runners/limits.yaml`
(precedence: per-model > `default` block > CLI flags). A turn costs wildly
different amounts per model (context regrows each turn), so cap turns generously
for cheap models and `$` tightly for pricey ones.

---

## Usage

```bash
# single run
openbench run sympy__sympy-23534 --runner native --model claude-opus-4-8

# parallel matrix (per-model caps from configs/runners/limits.yaml)
openbench run-matrix --tasks sympy__sympy-23534,sympy__sympy-22914 \
  --models claude-opus-4-8,deepseek-v4-flash,gpt-4.1 --concurrency 3
```

```python
from openbench.runners import get_runner
from openbench.runners.execute import execute_run
from openbench.models import RunLimits

result = execute_run(task_id="sympy__sympy-23534", runner=get_runner("native"),
                     model="deepseek-v4-flash", limits=RunLimits(max_turns=100, max_cost_usd=1.0))
```

Runners accept an injectable `chat_fn` so the loop is unit-testable offline with
canned responses (no API, no Docker).

---

## Tests

All harness tests are **offline** (API and `docker build`/`exec` are stubbed), so
the suite runs in ~1.5s.

| Test file | # | Covers | Difficulty |
|---|--:|---|---|
| `tests/test_tooluse_runner.py` | 4 | function-calling loop, no-tool-call nudge, tool-result round-trip + OpenRouter cost, cost-cap | Med |
| `tests/test_claude_native.py` | 4 | native tool_use loop, thinking capture, transcript schema, cost cap | Med |
| `tests/test_mini_swe.py` | 4 | text-fence extraction, done loop, turn-cap nudge, adapter | Med |
| `tests/test_protocols.py` | 5 | OpenAI tool-use wire format (request / parse / observation) | Med |
| `tests/test_matrix.py` | 3 | concurrency + per-cell isolation; `load_limits` inheritance; per-cell override | Med |
| `tests/test_builder.py` | 3 | per-task `base_image` resolution (default / per-task / explicit arg) | Low |

```bash
uv run pytest tests/test_tooluse_runner.py tests/test_claude_native.py \
  tests/test_mini_swe.py tests/test_protocols.py tests/test_matrix.py tests/test_builder.py -q
```

---

## Extending: add a runner

1. Implement the `AgentRunner` protocol (set `name`, `needs_network=False`, write
   the transcript schema above).
2. Register it in `get_runner()` (`__init__.py`).
3. If it writes the standard schema, add its `name` to the adapter routing in
   `analysis/pipeline.py` so the `mini_swe` adapter normalizes it.

---

## Known limitations

- **One tool call per turn:** if a model emits parallel tool calls, only the first
  is executed (mirrors `claude-native`); a follow-up tool result for the others is
  not sent.
- **`mini-swe` is OOD** for tool-trained models (the "dream"); it is retained only
  as a legacy baseline, not the common harness.
- **Bare test-name resolution** (e.g. `test_add`) is a *consumer-side* grading
  concern, not a harness one — but worth specific `file.py::test` ids upstream.

---

## What is harness vs benchmark

The harness owns *how agents run* (this directory + `envs/builder`, `dockerutil`,
`sandbox`, the transcript schema). OpenBench owns *what tasks and what to infer*
(mining, task construction/validation, grading, analysis, report). The clean
boundary between them is the `raw_transcript.jsonl` schema above.
