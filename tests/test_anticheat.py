"""Offline tests for grading.anticheat.scan_patch over synthetic patches."""

from __future__ import annotations

from openbench.grading.anticheat import scan_patch

MODIFY_TEST = """\
diff --git a/tests/test_core.py b/tests/test_core.py
--- a/tests/test_core.py
+++ b/tests/test_core.py
@@ -1,3 +1,2 @@
 import pytest
-assert compute() == 5
-assert other() == 2
+pass
"""

ADD_NEW_TEST = """\
diff --git a/tests/test_new.py b/tests/test_new.py
new file mode 100644
--- /dev/null
+++ b/tests/test_new.py
@@ -0,0 +1,2 @@
+def test_x():
+    assert x() == 1
"""

SKIP_XFAIL = """\
diff --git a/tests/test_skip.py b/tests/test_skip.py
--- a/tests/test_skip.py
+++ b/tests/test_skip.py
@@ -1,2 +1,4 @@
 import pytest
+@pytest.mark.skip(reason="later")
+@pytest.mark.xfail
 def test_a():
"""

CONFTEST_HACK = """\
diff --git a/conftest.py b/conftest.py
--- a/conftest.py
+++ b/conftest.py
@@ -1,1 +1,2 @@
 import os
+collect_ignore = ["tests/test_hard.py"]
"""

HARDCODE = """\
diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,4 @@
 import os
+if os.environ.get("PYTEST_CURRENT_TEST"):
+    return True
 def run():
"""

MODIFY_PROTECTED = """\
diff --git a/src/checks.py b/src/checks.py
--- a/src/checks.py
+++ b/src/checks.py
@@ -1,2 +1,2 @@
 import os
-X = 1
+X = 2
"""

CLEAN = """\
diff --git a/src/core.py b/src/core.py
--- a/src/core.py
+++ b/src/core.py
@@ -1,2 +1,2 @@
 import os
-VALUE = 1
+VALUE = 2
"""


def test_empty_patch_is_clean() -> None:
    report = scan_patch("", {})
    assert not report.test_tampering
    assert report.tampered_files == []
    assert report.skip_xfail_added == 0
    assert report.assert_weakening_count == 0


def test_clean_patch() -> None:
    report = scan_patch(CLEAN, {})
    assert not report.test_tampering
    assert report.hardcode_flags == []
    assert report.assert_weakening_count == 0


def test_modified_test_file_is_tampering_and_weakening() -> None:
    report = scan_patch(MODIFY_TEST, {})
    assert report.test_tampering
    assert report.tampered_files == ["tests/test_core.py"]
    # 2 removed asserts, 0 added in the hunk.
    assert report.assert_weakening_count == 2


def test_added_test_file_is_not_tampering() -> None:
    report = scan_patch(ADD_NEW_TEST, {})
    assert not report.test_tampering
    assert report.tampered_files == []
    assert report.assert_weakening_count == 0


def test_skip_xfail_counting() -> None:
    report = scan_patch(SKIP_XFAIL, {})
    assert report.skip_xfail_added == 2


def test_conftest_hack_detected() -> None:
    report = scan_patch(CONFTEST_HACK, {})
    assert report.conftest_hacks == ["conftest.py"]
    assert report.test_tampering  # conftest.py is a test path


def test_hardcode_flag_in_non_test_file() -> None:
    report = scan_patch(HARDCODE, {})
    assert len(report.hardcode_flags) == 1
    assert report.hardcode_flags[0].startswith("src/app.py:")
    assert "PYTEST_CURRENT_TEST" in report.hardcode_flags[0]
    assert not report.test_tampering


def test_protected_file_modification_is_tampering() -> None:
    protected = {"src/checks.py": "deadbeef"}
    report = scan_patch(MODIFY_PROTECTED, protected)
    assert report.test_tampering
    assert report.tampered_files == ["src/checks.py"]
    # Same patch without protection: not a test path, so clean.
    assert not scan_patch(MODIFY_PROTECTED, {}).test_tampering


def test_multi_file_patch_combines_signals() -> None:
    patch = MODIFY_TEST + HARDCODE + CONFTEST_HACK
    report = scan_patch(patch, {})
    assert report.test_tampering
    assert set(report.tampered_files) == {"tests/test_core.py", "conftest.py"}
    assert report.assert_weakening_count == 2
    assert report.conftest_hacks == ["conftest.py"]
    assert len(report.hardcode_flags) == 1
