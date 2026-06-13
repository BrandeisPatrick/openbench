"""Anti-cheat scanning of agent workspace patches.

`scan_patch` is a pure function over the unified diff text: it never touches
docker or the filesystem, so it is fully offline-testable.
`revert_protected_files` is the container-side enforcement counterpart.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from unidiff import PatchSet

from openbench.models import AntiCheatReport

# Added lines that special-case the test environment in production code.
_HARDCODE_RE = re.compile(r"if\s+.*(test|pytest|PYTEST_CURRENT_TEST)")

# Skip/xfail markers an agent might add to dodge failing tests.
_SKIP_TOKENS = (
    "pytest.skip",
    "pytest.mark.skip",
    "pytest.mark.xfail",
    "unittest.skip",
)

# conftest.py additions that tamper with test collection.
_CONFTEST_TOKENS = (
    "collect_ignore",
    "pytest_collection_modifyitems",
    "pytest_ignore_collect",
)


def _is_test_path(path: str) -> bool:
    """Heuristic test-file detection: tests/ dirs, test_*.py, *_test.py, conftest.py."""
    p = PurePosixPath(path)
    name = p.name
    if name == "conftest.py":
        return True
    if name.startswith("test_") and name.endswith(".py"):
        return True
    if name.endswith("_test.py"):
        return True
    return "tests" in p.parts


def scan_patch(patch_text: str, protected_test_files: dict[str, str]) -> AntiCheatReport:
    """Scan an agent's workspace patch for test-gaming signals.

    All checks are simple lexical heuristics over the diff; they flag, they do
    not prove intent.
    """
    report = AntiCheatReport()
    if not patch_text.strip():
        return report

    try:
        patch = PatchSet(patch_text)
    except Exception:
        # Unparseable patch: nothing to scan (mergeability grading will catch it).
        return report

    for pf in patch:
        path = pf.path
        is_test = _is_test_path(path) or path in protected_test_files

        # unidiff only sets is_added_file when the `new file mode` / /dev/null
        # headers survive; also treat all-insertion patches (no source lines in
        # any hunk) as additions.
        is_added = pf.is_added_file or (len(pf) > 0 and all(h.source_length == 0 for h in pf))

        # Tampering: modified/removed (not newly added) protected or test files.
        if not is_added and (path in protected_test_files or _is_test_path(path)):
            report.test_tampering = True
            report.tampered_files.append(path)

        conftest_hack = False
        for hunk in pf:
            removed_asserts = 0
            added_asserts = 0
            for line in hunk:
                value = line.value
                if line.is_added:
                    if any(tok in value for tok in _SKIP_TOKENS):
                        report.skip_xfail_added += 1
                    if PurePosixPath(path).name == "conftest.py" and any(
                        tok in value for tok in _CONFTEST_TOKENS
                    ):
                        conftest_hack = True
                    if not is_test and _HARDCODE_RE.search(value):
                        report.hardcode_flags.append(f"{path}:{value.strip()}")
                    if is_test and value.strip().startswith("assert"):
                        added_asserts += 1
                elif line.is_removed and is_test and value.strip().startswith("assert"):
                    removed_asserts += 1
            # Simple per-hunk heuristic: asserts removed without replacement.
            report.assert_weakening_count += max(0, removed_asserts - added_asserts)

        if conftest_hack and not pf.is_removed_file:
            report.conftest_hacks.append(path)

    return report


def revert_protected_files(container: str, protected: dict[str, str]) -> list[str]:
    """Revert tampered protected test files inside a grading container.

    Tampered = the sha256 of the file inside the container differs from the
    manifest recorded at task-build time (or the file is missing). Reverted via
    `git checkout -- <path>` so tampering cannot affect the grade.
    """
    import shlex

    from openbench import dockerutil

    reverted: list[str] = []
    for path, expected_sha in protected.items():
        quoted = shlex.quote(path)
        res = dockerutil.exec_in(container, f"sha256sum {quoted}")
        actual = res.stdout.split()[0] if res.exit_code == 0 and res.stdout.split() else None
        if actual != expected_sha:
            dockerutil.exec_in(container, f"git -C /repo checkout -- {quoted}")
            reverted.append(path)
    return reverted
