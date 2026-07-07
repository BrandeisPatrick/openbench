"""Offline unit tests for openbench.tasks.tests_split."""

from __future__ import annotations

import random

from unidiff import PatchSet

from openbench.tasks.tests_split import (
    extract_f2p_candidates,
    is_test_path,
    sample_p2p,
    split_patch,
)

SAMPLE_DIFF = """\
diff --git a/pkg/core.py b/pkg/core.py
index 1111111..2222222 100644
--- a/pkg/core.py
+++ b/pkg/core.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
diff --git a/tests/test_core.py b/tests/test_core.py
index 3333333..4444444 100644
--- a/tests/test_core.py
+++ b/tests/test_core.py
@@ -1,3 +1,10 @@
 from pkg.core import add


+def test_add():
+    assert add(1, 2) == 3
+
+
+class TestMath:
+    def test_add_negative(self):
+        assert add(-1, -1) == -2
diff --git a/tests/test_misc.py b/tests/test_misc.py
index 5555555..6666666 100644
--- a/tests/test_misc.py
+++ b/tests/test_misc.py
@@ -10,3 +10,6 @@ class TestMisc:
     def test_old(self):
         assert True

+    def test_new(self):
+        assert 1 + 1 == 2
+
"""


# --- is_test_path ------------------------------------------------------------


def test_is_test_path_positive():
    assert is_test_path("tests/test_core.py")
    assert is_test_path("pkg/tests/helpers.py")  # anything under tests/
    assert is_test_path("pkg/conftest.py")
    assert is_test_path("pkg/core_test.py")
    assert is_test_path("test_standalone.py")


def test_is_test_path_negative():
    assert not is_test_path("pkg/core.py")
    assert not is_test_path("contests/foo.py")  # 'tests' must be a path component
    assert not is_test_path("pkg/testing.py")
    assert not is_test_path("docs/tests.rst")


# --- split_patch --------------------------------------------------------------


def test_split_patch_gold_is_source_only():
    gold, _ = split_patch(SAMPLE_DIFF)
    files = [pf.path for pf in PatchSet(gold)]
    assert "pkg/core.py" in files
    # test files live ONLY in test.patch — a gold that carries them collides
    # with the anti-cheat revert + test.patch injection at grade time
    assert not any(f.startswith("tests/") for f in files)


def test_split_patch_test_subset_only_contains_test_files():
    _, test_only = split_patch(SAMPLE_DIFF)
    files = [pf.path for pf in PatchSet(test_only)]
    assert files == ["tests/test_core.py", "tests/test_misc.py"]
    assert "pkg/core.py" not in test_only
    # the subset is still a parseable, applyable unified diff
    assert test_only.startswith("diff --git a/tests/test_core.py")


# --- extract_f2p_candidates ---------------------------------------------------


def test_extract_f2p_top_level_and_class_method():
    _, test_only = split_patch(SAMPLE_DIFF)
    assert extract_f2p_candidates(test_only) == [
        "tests/test_core.py::TestMath::test_add_negative",
        "tests/test_core.py::test_add",
        "tests/test_misc.py::TestMisc::test_new",
    ]


def test_extract_f2p_class_from_section_header():
    # tests/test_misc.py only sees `class TestMisc` via the @@ section header
    diff = SAMPLE_DIFF.split("diff --git a/tests/test_misc.py")[1]
    diff = "diff --git a/tests/test_misc.py" + diff
    assert extract_f2p_candidates(diff) == ["tests/test_misc.py::TestMisc::test_new"]


def test_extract_f2p_ignores_context_and_removed_defs():
    diff = """\
diff --git a/tests/test_x.py b/tests/test_x.py
index 1111111..2222222 100644
--- a/tests/test_x.py
+++ b/tests/test_x.py
@@ -1,4 +1,4 @@
 def test_existing():
     assert True
-def test_removed():
+def test_renamed():
     assert True
"""
    assert extract_f2p_candidates(diff) == ["tests/test_x.py::test_renamed"]


def test_extract_f2p_class_context_resets_at_module_level():
    diff = """\
diff --git a/tests/test_y.py b/tests/test_y.py
index 1111111..2222222 100644
--- a/tests/test_y.py
+++ b/tests/test_y.py
@@ -1,2 +1,8 @@
 import pytest

+class TestA:
+    def test_in_class(self):
+        assert True
+
+def test_back_at_top():
+    assert True
"""
    assert extract_f2p_candidates(diff) == [
        "tests/test_y.py::TestA::test_in_class",
        "tests/test_y.py::test_back_at_top",
    ]


def test_extract_f2p_empty_patch():
    assert extract_f2p_candidates("") == []
    assert extract_f2p_candidates("   \n") == []


# --- sample_p2p ----------------------------------------------------------------


ALL_PASSING = [
    "docs/test_docs.py::test_d1",
    "other/test_other.py::test_o1",
    "other/test_other.py::test_o2",
    "pkg/test_pkg.py::test_p1",
    "pkg/test_pkg.py::test_p2",
    "zeta/test_zeta.py::test_z1",
]


def test_sample_p2p_prefers_touched_top_level_dirs():
    out = sample_p2p(ALL_PASSING, ["pkg/core.py"], cap=3)
    assert len(out) == 3
    assert "pkg/test_pkg.py::test_p1" in out
    assert "pkg/test_pkg.py::test_p2" in out
    # remainder filled round-robin from sorted other dirs -> docs first
    assert "docs/test_docs.py::test_d1" in out
    assert out == sorted(out)


def test_sample_p2p_round_robin_fill_across_dirs():
    out = sample_p2p(ALL_PASSING, ["pkg/core.py"], cap=5)
    # 2 preferred + one from each of docs/other/zeta before a second from other
    assert set(out) == {
        "pkg/test_pkg.py::test_p1",
        "pkg/test_pkg.py::test_p2",
        "docs/test_docs.py::test_d1",
        "other/test_other.py::test_o1",
        "zeta/test_zeta.py::test_z1",
    }


def test_sample_p2p_cap_and_no_touched():
    assert sample_p2p(ALL_PASSING, [], cap=2) == sorted(sample_p2p(ALL_PASSING, [], cap=2))
    assert len(sample_p2p(ALL_PASSING, [], cap=2)) == 2
    assert sample_p2p(ALL_PASSING, ["pkg/x.py"], cap=100) == sorted(ALL_PASSING)


def test_sample_p2p_deterministic_under_input_shuffle():
    expected = sample_p2p(ALL_PASSING, ["pkg/core.py"], cap=4)
    rng = random.Random(7)
    for _ in range(5):
        shuffled = ALL_PASSING[:]
        rng.shuffle(shuffled)
        assert sample_p2p(shuffled, ["pkg/core.py"], cap=4) == expected
