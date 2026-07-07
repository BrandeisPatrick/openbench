"""Pure diff-splitting and test-selection helpers (no network, no docker).

Everything here is deterministic and unit-testable offline; construct.py and
validate.py compose these functions.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import PurePosixPath

from unidiff import PatchSet

_CLASS_RE = re.compile(r"^class\s+([A-Za-z_]\w*)")
_DEF_RE = re.compile(r"^(\s*)(?:async\s+def|def)\s+(test_\w+)")


def is_test_path(path: str) -> bool:
    """True for files under a tests/ directory or with pytest-style names."""
    parts = PurePosixPath(path).parts
    if not parts:
        return False
    if "tests" in parts[:-1]:
        return True
    name = parts[-1]
    return (
        name == "conftest.py"
        or (name.startswith("test_") and name.endswith(".py"))
        or name.endswith("_test.py")
    )


def split_patch(diff_text: str) -> tuple[str, str]:
    """Split a unified diff into (gold_source_only, test_only) — SWE-bench style.

    gold.patch must NOT contain test files: grading applies the solution patch,
    reverts protected-test-file edits (anti-cheat), then injects test.patch. A
    gold patch that also carries the test changes collides with that flow —
    test files the PR *created* aren't in the protected map, so they survive
    the revert and test.patch then fails to apply (every F2P marked failed).
    """
    patch = PatchSet(diff_text)
    gold_parts = [str(pf) for pf in patch if not is_test_path(pf.path)]
    test_parts = [str(pf) for pf in patch if is_test_path(pf.path)]
    return "".join(gold_parts), "".join(test_parts)


def extract_f2p_candidates(test_patch_text: str) -> list[str]:
    """Static extraction of pytest node ids for added/modified test functions.

    Walks the hunks of the test-only patch and records every ADDED
    ``def test_*`` line as ``file::test_name``. Class methods are mapped to
    ``file::TestX::test_y`` by tracking ``class`` context lines inside each
    hunk (plus the hunk section header) — best effort, validated dynamically
    later by validate_task.
    """
    if not test_patch_text.strip():
        return []
    node_ids: set[str] = set()
    for pf in PatchSet(test_patch_text):
        if pf.is_removed_file:
            continue
        path = pf.path
        for hunk in pf:
            current_class: str | None = None
            header_match = _CLASS_RE.match(hunk.section_header or "")
            if header_match:
                current_class = header_match.group(1)
            for line in hunk:
                if line.is_removed:
                    continue
                text = line.value.rstrip("\n")
                class_match = _CLASS_RE.match(text)
                if class_match:
                    current_class = class_match.group(1)
                    continue
                def_match = _DEF_RE.match(text)
                if def_match:
                    indent, name = def_match.groups()
                    if not indent:
                        current_class = None  # back at module level
                        if line.is_added:
                            node_ids.add(f"{path}::{name}")
                    elif line.is_added:
                        if current_class:
                            node_ids.add(f"{path}::{current_class}::{name}")
                        else:
                            node_ids.add(f"{path}::{name}")
                    continue
                # Any other top-level statement means we left the class body.
                if text and not text[0].isspace() and not text.startswith("#"):
                    current_class = None
    return sorted(node_ids)


def _top_level_dir(node_id: str) -> str:
    return node_id.split("::", 1)[0].split("/", 1)[0]


def sample_p2p(all_passing: list[str], touched_modules: list[str], cap: int = 500) -> list[str]:
    """Deterministically sample PASS_TO_PASS node ids up to ``cap``.

    Tests sharing a top-level directory with the touched modules are taken
    first (sorted); the remainder is filled round-robin across the other
    top-level directories (sorted), so the sample is stable across runs and
    input orderings. No randomness.
    """
    touched_dirs = {m.split("/", 1)[0] for m in touched_modules}
    unique = sorted(set(all_passing))
    preferred = [t for t in unique if _top_level_dir(t) in touched_dirs]
    rest = [t for t in unique if _top_level_dir(t) not in touched_dirs]

    selected = preferred[:cap]
    if len(selected) < cap and rest:
        buckets: dict[str, list[str]] = defaultdict(list)
        for t in rest:
            buckets[_top_level_dir(t)].append(t)
        keys = sorted(buckets)
        while len(selected) < cap and any(buckets.values()):
            for key in keys:
                if buckets[key]:
                    selected.append(buckets[key].pop(0))
                    if len(selected) >= cap:
                        break
    return sorted(selected)
