"""Super-long-PR threshold filters and exclusion rules (configs/mining.yaml `filters:`)."""

from __future__ import annotations

from openbench.models import PRCandidate

_LOCKFILE_SUFFIXES = (".lock", ".min.js", "_pb2.py")
_LOCKFILE_NAMES = frozenset({"package-lock.json"})
_DOC_SUFFIXES = (".md", ".rst")


def is_lockfile(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return name in _LOCKFILE_NAMES or name.endswith(_LOCKFILE_SUFFIXES)


def is_docs(path: str) -> bool:
    return path.startswith("docs/") or "/docs/" in path or path.endswith(_DOC_SUFFIXES)


def passes_filters(
    c: PRCandidate,
    cfg: dict,
    files: list[str] | None = None,
    test_loc_fraction: float | None = None,
) -> tuple[bool, list[str]]:
    """Check every mining threshold; returns (ok, reasons_failed).

    `files` is the full changed-filename list (PRCandidate does not carry it);
    when omitted, the lockfile/docs exclusions are skipped. `test_loc_fraction`
    is test-file LOC / total LOC; tasks hide and protect test files, so a PR
    that is mostly test changes leaves nothing for the agent to implement.
    """
    f = cfg["filters"]
    reasons: list[str] = []

    loc = c.additions + c.deletions
    if loc < f["min_loc_changed"]:
        reasons.append("min_loc_changed")
    if loc > f["max_loc_changed"]:
        reasons.append("max_loc_changed")
    if c.changed_files < f["min_changed_files"]:
        reasons.append("min_changed_files")
    if c.commits < f["min_commits"]:
        reasons.append("min_commits")
    if len(c.top_level_dirs) < f["min_top_level_dirs"]:
        reasons.append("min_top_level_dirs")
    if len(c.test_files_changed) < f["min_test_files"]:
        reasons.append("min_test_files")
    if c.test_functions_changed < f["min_test_functions"]:
        reasons.append("min_test_functions")
    if c.review_comments < f["min_review_comments"]:
        reasons.append("min_review_comments")
    if not c.linked_issues and len(c.body) < f["min_body_chars"]:
        reasons.append("min_body_chars")
    if (
        test_loc_fraction is not None
        and "max_test_loc_fraction" in f
        and test_loc_fraction > f["max_test_loc_fraction"]
    ):
        reasons.append("max_test_loc_fraction")

    if files:
        lockfiles = sum(1 for p in files if is_lockfile(p))
        if lockfiles / len(files) > 0.5:
            reasons.append("lockfile_dominated")
        if all(is_docs(p) for p in files):
            reasons.append("docs_only")
    # rename-dominated exclusion needs rename detection from the unified diff,
    # which is not available from the files-list metadata here; skipped.

    return (not reasons, reasons)
