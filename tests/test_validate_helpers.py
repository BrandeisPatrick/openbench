"""Pure-helper tests for the validation gate (no docker)."""

from __future__ import annotations

from openbench.tasks.validate import _expand_ids


def test_expand_ids_exact_and_parametrized():
    collected = {
        "tests/test_a.py::test_plain",
        "tests/test_a.py::test_param[x]",
        "tests/test_a.py::test_param[y]",
        "tests/test_a.py::test_param_extra",
    }
    out = _expand_ids({"tests/test_a.py::test_plain", "tests/test_a.py::test_param"}, collected)
    assert out == {
        "tests/test_a.py::test_plain",
        "tests/test_a.py::test_param[x]",
        "tests/test_a.py::test_param[y]",
    }


def test_expand_ids_missing_dropped():
    assert _expand_ids({"tests/test_a.py::test_gone"}, {"tests/test_a.py::test_other"}) == set()
