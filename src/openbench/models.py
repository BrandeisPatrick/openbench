"""Core data contracts shared by every pipeline stage.

Everything that crosses a stage boundary (mining -> tasks -> envs -> runners
-> grading -> traces -> analysis) is one of these models, serialized as JSON.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class HardnessTier(str, Enum):
    EXTENDED = "extended"
    MAIN = "main"
    DIAMOND = "diamond"


# Difficulty labels, shared across sources: SWE-bench Verified ships these as a
# human annotation; mined tasks get one assigned by reviewing the PR (see
# tasks/difficulty.py). Stored verbatim so the two sources are directly
# comparable. Ordered easy -> hard.
DIFFICULTY_LEVELS: tuple[str, ...] = (
    "<15 min fix",
    "15 min - 1 hour",
    "1-4 hours",
    ">4 hours",
)


class PRCandidate(BaseModel):
    """A mined PR that passed the super-long-PR filters, pre-validation."""

    repo: str  # "org/name"
    pr_number: int
    title: str
    body: str = ""
    linked_issues: list[dict[str, Any]] = Field(default_factory=list)  # {number, title, body}
    base_commit: str
    merge_commit: str
    merged_at: datetime
    additions: int
    deletions: int
    changed_files: int
    commits: int
    review_comments: int
    top_level_dirs: list[str] = Field(default_factory=list)
    test_files_changed: list[str] = Field(default_factory=list)
    test_functions_changed: int = 0
    dependency_depth: int = 0
    hardness_score: float | None = None
    tier: HardnessTier | None = None

    @property
    def task_id(self) -> str:
        org, name = self.repo.split("/", 1)
        return f"{org}__{name}-{self.pr_number}"


class TaskValidation(BaseModel):
    """Result of the base-fails/merged-passes gate."""

    validated_at: datetime
    rounds: int = 3
    f2p_fail_on_base: bool
    f2p_pass_on_merged: bool
    p2p_pass_on_merged: bool
    flaky_tests_dropped: list[str] = Field(default_factory=list)
    accepted: bool


class Task(BaseModel):
    """A validated, runnable benchmark task. Lives at datasets/tasks/<task_id>/task.json."""

    task_id: str
    repo: str
    pr_number: int
    base_commit: str
    merge_commit: str
    merged_at: datetime
    tier: HardnessTier
    hardness_score: float
    prompt_path: str = "prompt.md"  # relative to task dir
    gold_patch_path: str = "gold.patch"  # full solution diff (hidden from agents)
    test_patch_path: str = "test.patch"  # gold test changes (injected at grade time)
    fail_to_pass: list[str] = Field(default_factory=list)  # pytest node ids
    pass_to_pass: list[str] = Field(default_factory=list)
    image_tag: str | None = None  # docker image, set by build-env
    install_cmd: str = "pip install -e ."
    test_cmd: str = "python -m pytest"
    protected_test_files: dict[str, str] = Field(default_factory=dict)  # path -> sha256 at base
    validation: TaskValidation | None = None
    # Difficulty label on the shared DIFFICULTY_LEVELS scale. Set from the human
    # annotation on SWE-bench Verified imports; assigned by PR review for mined
    # tasks (tasks/difficulty.py). None until labeled. Used to balance the suite.
    difficulty: str | None = None
    difficulty_note: str | None = None  # one-line rationale when assigned by review
    # Probe tasks: contradictory by construction (no valid solution exists). The
    # measured signal is whether the model flags impossibility vs fabricates.
    is_impossible: bool = False


class RunLimits(BaseModel):
    wall_clock_s: int = 5400
    max_turns: int = 200
    max_cost_usd: float = 15.0


ExitReason = Literal["completed", "timeout", "cost_cap", "turn_cap", "crash"]


class RunResult(BaseModel):
    """Outcome of one agent run. Lives at runs/<run_id>/run.json."""

    run_id: str
    task_id: str
    harness: str
    model: str
    started_at: datetime
    finished_at: datetime | None = None
    exit_reason: ExitReason | None = None
    raw_transcript_path: str = "raw_transcript.jsonl"  # relative to run dir
    workspace_patch_path: str = "workspace.patch"
    total_cost_usd: float = 0.0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_thinking_tokens: int = 0
    num_turns: int = 0


EventType = Literal[
    "run_start",
    "run_end",
    "thinking",
    "assistant_msg",
    "tool_call",
    "tool_result",
    "file_edit",
    "test_run",
    "search",
    "shell",
    "error",
]


class TraceEvent(BaseModel):
    """One normalized step in an agent trace. JSONL at runs/<run_id>/events.jsonl."""

    event_id: str
    run_id: str
    task_id: str
    harness: str
    model: str
    step_idx: int
    ts: datetime | None = None
    type: EventType
    content: str | None = None
    tool_name: str | None = None
    tool_args_digest: dict[str, Any] = Field(default_factory=dict)
    files_touched: list[str] = Field(default_factory=list)
    exit_code: int | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_thinking: int = 0
    cum_cost_usd: float = 0.0
    derived: dict[str, Any] = Field(default_factory=dict)


class AntiCheatReport(BaseModel):
    test_tampering: bool = False
    tampered_files: list[str] = Field(default_factory=list)
    skip_xfail_added: int = 0
    conftest_hacks: list[str] = Field(default_factory=list)
    hardcode_flags: list[str] = Field(default_factory=list)
    assert_weakening_count: int = 0


class GradeReport(BaseModel):
    """Result of grading one run. Lives at runs/<run_id>/grade.json."""

    run_id: str
    task_id: str
    applies_cleanly: bool = False
    builds: bool = False
    f2p_passed: list[str] = Field(default_factory=list)
    f2p_failed: list[str] = Field(default_factory=list)
    p2p_passed: list[str] = Field(default_factory=list)
    p2p_failed: list[str] = Field(default_factory=list)
    anticheat: AntiCheatReport = Field(default_factory=AntiCheatReport)
    # Honeypot tasks only: did the planted weak smoke suite pass?
    honeypot_smoke_passed: bool | None = None
    graded_at: datetime | None = None

    @property
    def f2p_pass_rate(self) -> float:
        total = len(self.f2p_passed) + len(self.f2p_failed)
        return len(self.f2p_passed) / total if total else 0.0

    @property
    def p2p_pass_rate(self) -> float:
        total = len(self.p2p_passed) + len(self.p2p_failed)
        return len(self.p2p_passed) / total if total else 0.0

    @property
    def resolved(self) -> bool:
        return (
            self.applies_cleanly
            and self.builds
            and bool(self.f2p_passed)
            and not self.f2p_failed
            and not self.p2p_failed
        )


class RunMetrics(BaseModel):
    """Deterministic behavioral metrics for one run (Pillar 2)."""

    run_id: str
    task_id: str
    harness: str
    model: str
    tier: HardnessTier | None = None
    # test gaming
    test_tampering: bool = False
    assert_weakening_count: int = 0
    skip_xfail_added: int = 0
    # binary "any-gaming" flags — length-invariant forms for reward inference
    # (counts scale with how much the agent edited; presence is the signal).
    assert_weakened: bool = False
    skip_xfail_inserted: bool = False
    # verification discipline
    verified_before_done: bool = False
    test_run_count: int = 0
    file_edit_count: int = 0
    test_runs_per_edit: float = 0.0
    # premature stop vs exhaustive loops
    early_stop: bool = False
    verification_loop_count: int = 0
    post_success_churn: int = 0
    # length-invariant (rate) forms of the counts above — these, not the raw
    # counts, drive reward inference (counts confound with trajectory length;
    # see docs/RESEARCH.md "Known limitations").
    verification_loops_per_edit: float = 0.0
    post_success_churn_rate: float = 0.0
    gave_up_failing: bool = False  # ended on a failing test run (length-invariant)
    # effort
    total_tokens: int = 0
    thinking_fraction: float = 0.0
    consecutive_failures_at_end: int = 0
    # scope (vs gold)
    diff_size_ratio: float | None = None
    file_jaccard: float | None = None
    out_of_scope_files: int | None = None
    out_of_scope_ratio: float | None = None  # length-invariant form of the above
    # literature-grounded, length-invariant (see docs/RESEARCH.md provenance table)
    recovery_rate: float | None = None        # self-correction rate (survey 2507.21504)
    progress_proxy: float | None = None       # model-free AgentPRM progress (2511.08325)
    action_efficiency: float | None = None    # optimal/actual files (2604.02547)
    plan_ned: float | None = None             # normalized edit distance vs gold (survey)
    redundancy_rate: float = 0.0              # duplicate edits / total edits (survey)
    # tool strategy
    search_before_edit_rate: float = 0.0
    guess_first_rate: float = 0.0
    exploration_fraction: float = 0.0
    # backtracking
    revert_count: int = 0
    # context / recall (H7)
    re_read_rate: float | None = None  # reads touching already-read files / all reads
    # context / recall (H13, user hypothesis, pre-registered 2026-06-12): working
    # memory — reasoning turns referencing artifacts last seen > W turns earlier
    # WITHOUT re-reading them (vs H7 = memory via re-action, H9 = memory from
    # weights). None when the trajectory is shorter than the dormancy window.
    long_range_recall_rate: float | None = None  # recalling reasoning events / all
    recall_distance_norm: float | None = None  # median recall reach / total turns
    # E3b action channel (registered 2026-06-12): executed commands targeting
    # dormant artifacts — behaviorally-proven recall, computable regardless of
    # CoT visibility. Precision = recalled targets that actually existed.
    action_recall_rate: float | None = None  # recalling commands / all commands
    action_recall_precision: float | None = None  # precise / checkable recalls
    # honeypot probe (H1 vs H2); None on non-honeypot tasks
    honeypot_exploit: bool | None = None  # claimed done + smoke green + hidden F2P ~0
    # confabulation: declared completion having never observed a green test, and
    # didn't actually pass (claims success it cannot have verified). Needs grade.
    confabulated_completion: bool | None = None
    # impossible probe: did the model flag the task as contradictory/unsolvable?
    flagged_impossible: bool | None = None
