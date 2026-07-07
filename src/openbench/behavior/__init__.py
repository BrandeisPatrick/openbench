"""Behavioral comparison of model generations.

profile.py  — per-run BehaviorProfile from the normalized trace (pure, offline)
pipeline.py — runs/ artifacts -> profiles (profile.json + DuckDB)
stats.py    — Cliff's delta, task-clustered bootstrap CIs, solve contrast
compare.py  — GEN_PAIRS registry + old-vs-new PairComparison
figures.py / report.py — markdown report with figures
"""

from openbench.behavior.compare import GEN_PAIRS, GenPair, PairComparison, compare_pair
from openbench.behavior.pipeline import load_profiles, profile_runs
from openbench.behavior.profile import AXES, BehaviorProfile, compute_profile
from openbench.behavior.report import generate_comparison_report

__all__ = [
    "AXES",
    "BehaviorProfile",
    "GEN_PAIRS",
    "GenPair",
    "PairComparison",
    "compare_pair",
    "compute_profile",
    "generate_comparison_report",
    "load_profiles",
    "profile_runs",
]
