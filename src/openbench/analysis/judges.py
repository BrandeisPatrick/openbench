"""LLM-judge metric stubs for hypotheses whose primary signal needs semantics.

These are the *primary* measurements for H8 (literal spec-fidelity vs
unstated-intent inference) and H9 (canonical pattern recall). They are not yet
wired to a live judge — the prompts are specified here and the functions raise
until the judge tier is enabled, so the hypotheses are pre-registered with their
exact operationalization rather than hand-waved. There is NO valid deterministic
proxy for either — a file-overlap heuristic cannot measure inferred intent or
convention recall (IFBench 2025 uses verifiable constraints + purpose-built
probe tasks). H8/H9 therefore have no measurement until this judge tier runs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class JudgeVerdict:
    score: float          # 0..1
    rationale: str
    judge_model: str


# H8 — does the model implement the spec literally, or infer unstated intent?
INTENT_INFERENCE_PROMPT = """\
You compare a coding agent's solution against the task spec and the reference (gold) solution.
Question: did the agent IMPLEMENT THE SPEC LITERALLY, or INFER UNSTATED-BUT-CORRECT intent?

Task spec:
{prompt}

Agent diff:
{agent_patch}

Reference (gold) diff:
{gold_patch}

Identify requirements the gold solution satisfies that are NOT literally stated in the spec
(e.g. an extra fallback, an edge case). For each, did the agent also handle it?
Return JSON: {{"intent_inference_score": <0..1, fraction of unstated requirements the agent
inferred>, "rationale": "<one sentence>"}}. 0 = pure literalist, 1 = inferred all unstated intent.
"""

# H9 — was a niche convention recalled directly, or derived after exploration?
RECALL_VS_DERIVE_PROMPT = """\
You analyze a coding agent's trajectory for a task requiring a niche convention/format.

Task spec:
{prompt}
Convention-bearing output (agent diff):
{agent_patch}
Trajectory summary (tool calls before the convention-bearing edit):
{pre_edit_actions}

Did the agent RECALL the convention directly (emitted it correctly with little/no exploration)
or DERIVE it (explored examples/docs/tests first)?
Return JSON: {{"recall_vs_derive": <0..1, 1 = pure recall, 0 = fully derived>,
"rationale": "<one sentence>"}}.
"""


def intent_inference_score(prompt: str, agent_patch: str, gold_patch: str) -> JudgeVerdict:
    """H8 primary. Pending the judge tier."""
    raise NotImplementedError(
        "H8 intent_inference_score needs the LLM-judge tier; "
        "no valid deterministic proxy exists (a file-overlap heuristic cannot "
        "measure inferred intent); H8 has no measurement until the judge runs."
    )


def recall_vs_derive(prompt: str, agent_patch: str, pre_edit_actions: str) -> JudgeVerdict:
    """H9 primary. Pending the judge tier."""
    raise NotImplementedError(
        "H9 recall_vs_derive needs the LLM-judge tier; "
        "no valid deterministic proxy exists; H9 has no measurement until the judge runs."
    )
