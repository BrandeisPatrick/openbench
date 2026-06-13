"""P5b rubric judge (stub): secondary LLM scoring of run quality.

Never gates `resolved`; it adds graded dimensions on top of mergeability.

Prompt template sketch
----------------------
System: You are reviewing a code patch produced by an autonomous agent for a
real merged PR. You see the task prompt, the agent's diff, and the gold diff.
Score each dimension 0-4 (0 = severe violation, 4 = exemplary) and give a
short rationale. Do not reward passing tests -- that is graded separately.

Dimensions (from configs/grading.yaml `rubric.dimensions`):
  - scope_discipline: does the diff stay within the task's blast radius?
  - regression_safety: defensive handling, no removed behavior, no API breaks.
  - style_adherence: matches the repo's existing conventions and idioms.
  - completeness: docs/edge cases/error paths the gold patch also covered.

User message contains: <task prompt> / <agent diff> / <gold diff (reference)>.
Sampled `samples` times at `temperature` with `judge_model`; scores averaged.
Output contract: JSON matching RubricScore.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RubricScore(BaseModel):
    """Per-dimension 0-4 scores from the LLM judge, plus rationale."""

    run_id: str
    judge_model: str = ""
    scope_discipline: int = Field(default=0, ge=0, le=4)
    regression_safety: int = Field(default=0, ge=0, le=4)
    style_adherence: int = Field(default=0, ge=0, le=4)
    completeness: int = Field(default=0, ge=0, le=4)
    rationale: str = ""


def judge_run(run_id: str) -> None:
    raise NotImplementedError("P5b: rubric judge")
