"""Generational comparison: old-model vs new-model within one lab.

All contrasts are within-lab (same wire protocol per pair, so scaffold
effects cancel inside the pair); cross-lab numbers are descriptive only.
Crashed runs (exit_reason == "crash") are infrastructure failures, never
behavioral data — excluded from every pool, tallied in the data-quality
section.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from openbench.behavior.profile import AXES, BehaviorProfile
from openbench.behavior.stats import (
    cliffs_delta,
    per_task_deltas,
    sign_agreement,
    solve_rate_contrast,
    task_bootstrap_ci,
)

# |Cliff's delta| >= 0.474 is the conventional "large effect" bar; the report's
# prose highlights only deltas past it whose CI excludes zero.
LARGE_DELTA = 0.474


@dataclass(frozen=True)
class GenPair:
    lab: str
    old_model: str
    new_model: str


GEN_PAIRS: dict[str, GenPair] = {
    "deepseek": GenPair(
        lab="deepseek",
        old_model="openrouter/deepseek/deepseek-chat-v3-0324",
        new_model="deepseek-v4-pro",
    ),
    "gpt": GenPair(lab="openai", old_model="gpt-4.1", new_model="gpt-5.5"),
    # Thinking lineages (July 2026 extension): each lab's reasoning-model line
    # as two consecutive hops, so the 3-point trajectory reads as old->mid and
    # mid->new. OpenAI: o1 (Dec 2024) -> o3 (Apr 2025) -> gpt-5.5. DeepSeek:
    # R1-0528 (May 2025, first agent-capable thinker) -> V3.2 (first hybrid
    # whose thinking mode tool-calls) -> v4-pro.
    "gpt-think-early": GenPair(lab="openai", old_model="o1", new_model="o3"),
    "gpt-think-late": GenPair(lab="openai", old_model="o3", new_model="gpt-5.5"),
    "deepseek-think-early": GenPair(
        lab="deepseek",
        old_model="openrouter/deepseek/deepseek-r1-0528",
        new_model="openrouter/deepseek/deepseek-v3.2",
    ),
    "deepseek-think-late": GenPair(
        lab="deepseek",
        old_model="openrouter/deepseek/deepseek-v3.2",
        new_model="deepseek-v4-pro",
    ),
    # Third lab (July 2026): Moonshot's thinking lineage, both hybrid thinkers
    # served first-party (reasoning_content + native tool calls).
    "kimi-think": GenPair(lab="moonshot", old_model="kimi-k2.6", new_model="kimi-k3"),
}


class MetricDelta(BaseModel):
    metric: str
    axis: str
    old_median: float | None = None
    new_median: float | None = None
    n_old: int = 0
    n_new: int = 0
    cliffs: float | None = None
    ci: tuple[float, float] | None = None
    per_task: dict[str, float] = {}
    sign_agreement: str = ""

    @property
    def large_and_clear(self) -> bool:
        return (
            self.cliffs is not None
            and abs(self.cliffs) >= LARGE_DELTA
            and self.ci is not None
            and (self.ci[0] > 0 or self.ci[1] < 0)
        )


class PairComparison(BaseModel):
    pair: str
    lab: str
    old_model: str
    new_model: str
    n_old: int = 0
    n_new: int = 0
    crashed_old: int = 0
    crashed_new: int = 0
    solve: dict = {}  # overall + per contamination stratum
    outcome_counts: dict[str, dict[str, int]] = {}  # side -> outcome -> n
    deltas: list[MetricDelta] = []


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    vs = sorted(values)
    mid = len(vs) // 2
    return vs[mid] if len(vs) % 2 else (vs[mid - 1] + vs[mid]) / 2


def _values_by_task(
    profiles: list[BehaviorProfile], metric: str
) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for p in profiles:
        v = getattr(p, metric)
        if v is None:
            continue
        out.setdefault(p.task_id, []).append(float(v))
    return out


def _outcome(p: BehaviorProfile) -> str:
    if p.resolved:
        return "resolved"
    if p.confabulated_completion:
        return "confabulated"
    if p.grind_to_cap:
        return "grind_to_cap"
    if p.gave_up_failing:
        return "gave_up_failing"
    return "other_fail"


def compare_pair(profiles: list[BehaviorProfile], name: str) -> PairComparison:
    pair = GEN_PAIRS[name]
    old_all = [p for p in profiles if p.model == pair.old_model]
    new_all = [p for p in profiles if p.model == pair.new_model]
    old = [p for p in old_all if p.exit_reason != "crash"]
    new = [p for p in new_all if p.exit_reason != "crash"]

    comp = PairComparison(
        pair=name,
        lab=pair.lab,
        old_model=pair.old_model,
        new_model=pair.new_model,
        n_old=len(old),
        n_new=len(new),
        crashed_old=len(old_all) - len(old),
        crashed_new=len(new_all) - len(new),
    )

    # Solve-rate contrast, overall + stratified by task provenance. The strata
    # answer "do new models solve more only because they trained on these PRs?"
    # — Verified PRs predate every cohort model; mined PRs postdate the old gen.
    def solved_by_task(side: list[BehaviorProfile], stratum: str | None) -> dict:
        out: dict[str, list[bool]] = {}
        for p in side:
            if p.resolved is None or (stratum and p.source != stratum):
                continue
            out.setdefault(p.task_id, []).append(bool(p.resolved))
        return out

    comp.solve = {"overall": solve_rate_contrast(solved_by_task(old, None), solved_by_task(new, None))}
    for stratum in ("swebench-verified", "mined"):
        s = solve_rate_contrast(solved_by_task(old, stratum), solved_by_task(new, stratum))
        if s["old_n"] or s["new_n"]:
            comp.solve[stratum] = s

    for side, key in ((old, "old"), (new, "new")):
        counts: dict[str, int] = {}
        for p in side:
            counts[_outcome(p)] = counts.get(_outcome(p), 0) + 1
        comp.outcome_counts[key] = counts

    for axis, metrics in AXES.items():
        for metric in metrics:
            o = _values_by_task(old, metric)
            nw = _values_by_task(new, metric)
            o_flat = [v for vs in o.values() for v in vs]
            n_flat = [v for vs in nw.values() for v in vs]
            deltas = per_task_deltas(o, nw)
            comp.deltas.append(
                MetricDelta(
                    metric=metric,
                    axis=axis,
                    old_median=_median(o_flat),
                    new_median=_median(n_flat),
                    n_old=len(o_flat),
                    n_new=len(n_flat),
                    cliffs=cliffs_delta(o_flat, n_flat),
                    ci=task_bootstrap_ci(o, nw),
                    per_task=deltas,
                    sign_agreement=sign_agreement(deltas),
                )
            )
    return comp
