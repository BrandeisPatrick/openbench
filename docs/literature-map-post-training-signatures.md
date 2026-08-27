# Literature map: post-training techniques → inference-observable signatures

Purpose: ground the reasoning-trend analysis in (1) what the model builders
*claim* they added in post-training, from their own technical reports, and
(2) published methods for detecting those techniques from inference behavior.
This document is a reading list and hypothesis map assembled BEFORE any
analysis of our corpus (fresh-start discipline); it states predictions, not
findings. Compiled 2026-08-27 from web search.

## 1. What the labs say they added (technical reports)

| Model (report) | Claimed post-training additions |
|---|---|
| DeepSeek-R1-0528 (R1 paper lineage, 2501.12948) | GRPO with rule-based verifiable rewards; math/code, single-turn heavy; no agentic stage |
| DeepSeek-V3.2 ([2512.02556](https://arxiv.org/abs/2512.02556)) | First integration of thinking directly into tool-use (thinking + tool calls in one trajectory, cold-start unification); ~1,800 synthesized agentic environments / 85k prompts; RL compute > 10% of pre-training |
| DeepSeek-V4 ([2606.19348](https://arxiv.org/abs/2606.19348)) | Replaces mixed RL with two stages: domain specialists (math / coding / agent / IF) trained SFT+GRPO, then **on-policy distillation** from 10+ teachers into one model; **Generative Reward Model** for hard-to-verify tasks |
| Kimi-K3 ([2607.24653](https://arxiv.org/abs/2607.24653)) | 9 in-house teachers = 3 domains (general / agentic / coding) × **3 reasoning-effort levels**, distilled into one unified model; RL emphasis on long-horizon execution |
| GLM-5 ([2602.15763](https://arxiv.org/abs/2602.15763), not yet in corpus) | Sequential pipeline: Reasoning RL → **Agentic RL** → General RL; asynchronous long-horizon agent-RL infrastructure |

Convergent industry pattern in 2026 reports: (a) a dedicated **agentic-RL
stage** on synthesized long-horizon environments; (b) **specialists-then-
distill** replacing monolithic RL (V4 and K3 independently); (c)
**effort/budget conditioning**; (d) generative/soft rewards where
verification fails.

## 2. Detection literature, mapped to each claimed technique

### a. Distillation from teacher ensembles (V4, K3)
- MoE expert-routing signatures as structural fingerprints of distillation —
  [2510.16968](https://www.arxiv.org/pdf/2510.16968)
- Reference-based distillation detection, black-box, per-probe significance
  tests for teacher attribution — [2607.09692](https://arxiv.org/html/2607.09692v1)
- Multi-method audit stack (LLMmap behavioral probes, lineage inference via
  JS-divergence, REEF/CKA representation similarity, stylistic families) —
  [model-audit](https://github.com/liuxiaotong/model-audit)
- Antidistillation fingerprinting — [ICML 2026](https://icml.cc/virtual/2026/poster/63624);
  attention-based differential fingerprinting — [2604.05502](https://arxiv.org/pdf/2604.05502)
- **Predicted signature**: distilled unified models should show *mixture*
  characteristics — task-conditional style switching (specialist modes),
  and high cross-sample determinism within a mode.

### b. RLVR sharpening (all post-R1 models)
- Pass@1 rises while pass@k stagnates/degrades vs base — RLVR reallocates
  probability onto known paths ([limit-of-RLVR](https://limit-of-rlvr.github.io/),
  [OpenReview](https://openreview.net/forum?id=4OsgYD7em5)); counterpoint:
  curriculum RL can exceed the base boundary — [2606.22317](https://arxiv.org/html/2606.22317)
- Entropy collapse under RLVR (measured ~8.4 → ~6.7 bits) and mitigations —
  [2605.11491](https://arxiv.org/pdf/2605.11491), [2606.15455](https://arxiv.org/html/2606.15455v1),
  [2509.07430](https://arxiv.org/pdf/2509.07430)
- **Predicted signature**: cross-seed convergence — later generations should
  produce near-identical trajectories/patches across seeds where earlier
  generations scatter. Directly measurable in a multi-seed corpus without
  logprobs (patch equality, edit-location overlap, command-sequence
  similarity across seeds of the same cell).

### c. Agentic RL on long-horizon environments (V3.2, K3, GLM-5)
- Rollout length *decreases* over agentic-RL training while reward holds —
  [gpt-oss agentic-RL retrospective](https://huggingface.co/blog/LinkedIn/gpt-oss-agentic-rl);
  long-horizon credit assignment methods — [ToolVerse 2607.15660](https://arxiv.org/html/2607.15660),
  [2608.10357](https://arxiv.org/html/2608.10357v1), [SENTINEL 2606.12908](https://arxiv.org/pdf/2606.12908)
- **Predicted signatures**: (i) trajectory compression at constant/better
  outcomes across generations; (ii) tool-call timing/selection becomes
  purposeful ("when/why" not just "which"); (iii) thinking interleaved WITH
  actions (V3.2's claimed unification) vs think-then-act-blindly (R1-era) —
  visible in trace structure as reasoning/action alternation.

### d. Post-training style/alignment attribution (all)
- "Alignment signatures": directional representations of post-training
  style, extractable and ablatable — [PASTA 2605.30526](https://arxiv.org/html/2605.30526v1)
- Stylistic markers as provider-level attribution of the fine-tuning recipe —
  [markdown fingerprint 2603.27006](https://arxiv.org/pdf/2603.27006);
  glyph-level signatures of specific model families (per 2607.09692)
- **Predicted signature**: reasoning-trace prose style clusters by lab and
  generation; distilled models may inherit teacher styles per domain.

### e. Reasoning-trace structure and its limits (analysis toolkit)
- Trace discourse structures — [ReasoningFlow 2606.05402](https://arxiv.org/pdf/2606.05402);
  thinking-pattern typology — [ThinkPatterns-21k 2503.12918](https://arxiv.org/pdf/2503.12918);
  Schoenfeld-style episode coding — [2512.19995](https://arxiv.org/pdf/2512.19995);
  reasoning-paradigm survey — [2606.11470](https://arxiv.org/pdf/2606.11470)
- Over/underthinking and token-efficiency surveys —
  [2503.16419](https://arxiv.org/pdf/2503.16419), [2507.09662](https://arxiv.org/pdf/2507.09662),
  [2508.02120](https://arxiv.org/pdf/2508.02120)
- **Caution (faithfulness)**: CoT is not a transparent readout of
  computation — [2505.05410](https://arxiv.org/abs/2505.05410),
  [2503.08679](https://arxiv.org/abs/2503.08679),
  [FaithCoT-Bench 2510.04040](https://arxiv.org/pdf/2510.04040),
  [2305.04388](https://arxiv.org/abs/2305.04388). Trace-based claims must be
  triangulated against *actions and outcomes*, which our corpus records
  independently of the stated reasoning.

## 3. Testability against our instruments

Testable on the existing corpus (transcripts capture reasoning_content,
every command, output, patch, grade):
1. Cross-seed convergence (2b) — 3 seeds/cell now; more seeds in expansion.
2. Reasoning/action interleaving structure (2c-iii) — R1 vs V3.2 vs V4 arms.
3. Trajectory compression at constant outcome (2c-i) — within-lab pairs.
4. Voluntary tool-emission timing (2c-ii) — tool_choice=auto by design.
5. Trace discourse/style coding (2d, 2e) — reasoning_content per turn.

Requires new instrumentation (flag for the confirmatory design):
6. Token-level entropy/logprobs (2b) — not recorded; capture where APIs
   expose logprobs.
7. Pass@k at k≥5 (2b) — needs more seeds on a task subset.
8. Effort-level conditioning probes for K3 (1) — vary the API effort knob.
9. Distillation probes per 2607.09692 (2a) — dedicated probe prompts, not
   agent tasks.

Next step (separate doc): pre-registered analysis plan picking from these
hypotheses with metrics and decision rules fixed before computation.
