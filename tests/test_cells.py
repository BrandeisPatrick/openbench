"""Cell = (model, harness) unit of analysis: grouping, labelling, degeneracy."""

from __future__ import annotations

from openbench.analysis.cells import (
    cell_is_degenerate,
    cell_key,
    cohort_labels,
    group_cells,
    is_degenerate,
)
from openbench.models import RunMetrics


def _m(model: str, harness: str, **kw) -> RunMetrics:
    return RunMetrics(
        run_id=f"{model}-{harness}-{kw.get('i', 0)}",
        task_id="t",
        harness=harness,
        model=model,
        **{k: v for k, v in kw.items() if k != "i"},
    )


def test_cell_key_and_group():
    runs = [_m("a", "h1", i=0), _m("a", "h1", i=1), _m("a", "h2"), _m("b", "h1")]
    cells = group_cells(runs)
    assert set(cells) == {("a", "h1"), ("a", "h2"), ("b", "h1")}
    assert len(cells[("a", "h1")]) == 2
    assert cell_key(runs[0]) == ("a", "h1")


def test_labels_plain_for_single_harness_split_for_multi():
    labels = cohort_labels([("a", "h1"), ("a", "h2"), ("b", "h1")])
    assert labels[("b", "h1")] == "b"  # single harness -> plain model name
    assert labels[("a", "h1")] == "a · h1"  # multi harness -> split
    assert labels[("a", "h2")] == "a · h2"


def test_is_degenerate_run():
    dreamed = _m("a", "mini-swe", test_run_count=0, file_edit_count=0,
                 confabulated_completion=True)
    real = _m("a", "native", test_run_count=5, file_edit_count=3,
              confabulated_completion=False)
    acted_then_claimed = _m("a", "mini-swe", test_run_count=2, file_edit_count=1,
                            confabulated_completion=True)
    assert is_degenerate(dreamed) is True
    assert is_degenerate(real) is False
    assert is_degenerate(acted_then_claimed) is False  # it acted -> not a dreamed run


def test_cell_is_degenerate_by_majority():
    dreamed = lambda i: _m("a", "mini-swe", i=i, test_run_count=0, file_edit_count=0,  # noqa: E731
                           confabulated_completion=True)
    real = _m("a", "mini-swe", i=9, test_run_count=4, file_edit_count=2)
    assert cell_is_degenerate([dreamed(0), dreamed(1), real]) is True   # 2/3 dreamed
    assert cell_is_degenerate([real]) is False
    assert cell_is_degenerate([]) is False
