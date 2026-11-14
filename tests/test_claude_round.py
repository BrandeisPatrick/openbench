"""Unit tests for research/analysis/claude_round.py (round 2: exp-08, exp-09, exp-10).

All inputs are synthetic: hand-made transcripts, patches, ledgers and cell
tables. No test reads the run corpus or makes an API call.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "research", "analysis"))
import claude_round as cr  # noqa: E402
import command_audit as ca  # noqa: E402

PATCH = "diff --git a/pkg/a.py b/pkg/a.py\n--- a/pkg/a.py\n+++ b/pkg/a.py\n@@ -1 +1 @@\n-x\n+y\n"


# --------------------------------------------------------------------------
# synthetic runs
# --------------------------------------------------------------------------

def make_tasks(tmp_path, monkeypatch, tasks):
    root = tmp_path / "tasks"
    for t in tasks:
        (root / t).mkdir(parents=True)
        (root / t / "gold.patch").write_text(PATCH)
        (root / t / "test.patch").write_text("")
    monkeypatch.setattr(ca.manifest, "TASKS", root)
    return root


def make_run(root, run_id, model="m", effort="high", task="lib__lib-1", n_search=2,
             exit_reason="completed", test_out="1 passed in 0.1s", tool_calls=(1,),
             thinking=100, resolved=None, with_calls=True, with_usage_raw=True):
    d = root / run_id
    d.mkdir(parents=True)
    lines = [{"type": "meta", "model": model, "task_id": task, "thinking_effort": effort}]
    cmds = [("grep -n x pkg/a.py", "1:x")] * n_search
    cmds = cmds + [("sed -i 's/x/y/' pkg/a.py", ""), ("pytest -q", test_out)]
    if exit_reason == "completed":
        cmds.append(("echo OPENBENCH_DONE", "OPENBENCH_DONE"))
    for i, (c, o) in enumerate(cmds, 1):
        resp = {"type": "api_response", "turn": i, "content": "", "reasoning_content": "t",
                "usage": {"prompt_tokens": 10, "completion_tokens": 50},
                "stop_reason": "tool_use"}
        if with_usage_raw:
            resp["usage_raw"] = {"output_tokens": 50,
                                 "output_tokens_details": {"thinking_tokens": thinking}}
        if with_calls:
            resp["n_tool_calls"] = tool_calls[(i - 1) % len(tool_calls)]
        lines.append(resp)
        lines.append({"type": "exec", "turn": i, "command": c, "exit_code": 0, "output": o})
    lines.append({"type": "final", "exit_reason": exit_reason, "turns": len(cmds),
                  "usage_totals": {"cost_usd": 0.5}})
    (d / "raw_transcript.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    (d / "workspace.patch").write_text(PATCH)
    (d / "run.json").write_text(json.dumps({"run_id": run_id, "exit_reason": exit_reason,
                                            "total_cost_usd": 0.5}))
    if resolved is not None:
        (d / "grade.json").write_text(json.dumps({
            "applies_cleanly": True, "builds": True, "f2p_passed": ["t"] if resolved else [],
            "f2p_failed": [] if resolved else ["t"], "p2p_failed": []}))
    return d


# --------------------------------------------------------------------------
# Page's L
# --------------------------------------------------------------------------

LEVELS5 = ["g1", "g2", "g3", "g4", "g5"]
BLOCKS6 = [f"t{i}" for i in range(6)]


def cells_from(fn, levels=LEVELS5, blocks=BLOCKS6):
    return {(lv, b): fn(i, j) for i, lv in enumerate(levels) for j, b in enumerate(blocks)}


def test_page_perfect_order_gives_max_l_and_min_p():
    draws = 2000
    t = cr.page_trend(LEVELS5, BLOCKS6, cells_from(lambda i, j: i + 0.1 * j), draws=draws)
    assert t["tested"] and t["n_blocks"] == 6
    assert t["L"] == 6 * sum(g * g for g in range(1, 6))       # maximum L = b * sum g^2
    assert t["E0"] == 6 * 5 * 36 / 4
    assert t["direction"] == 1
    assert t["p"] == pytest.approx(1 / (1 + draws))            # smallest attainable p
    assert (t["agree"], t["disagree"], t["no_sign"]) == (6, 0, 0)


def test_page_constant_gives_p_one():
    t = cr.page_trend(LEVELS5, BLOCKS6, cells_from(lambda i, j: 0.3), draws=500)
    assert t["p"] == 1.0 and t["direction"] == 0
    assert (t["agree"], t["disagree"], t["no_sign"]) == (0, 0, 6)    # constant blocks: no sign
    assert cr.decide_trend(t["p"], 1.0, t["agree"], t["disagree"], t["direction"]) == "none"


def test_page_reversed_same_p_opposite_direction():
    up = cr.page_trend(LEVELS5, BLOCKS6, cells_from(lambda i, j: i * (1 + j)), draws=800)
    down = cr.page_trend(LEVELS5, BLOCKS6, cells_from(lambda i, j: -i * (1 + j)), draws=800)
    assert up["p"] == down["p"]
    assert up["direction"] == 1 and down["direction"] == -1
    assert up["L"] - up["E0"] == -(down["L"] - down["E0"])
    # a noisier case: still symmetric
    vals = [[3, 1, 2, 5, 4], [1, 2, 2, 4, 3], [2, 1, 3, 3, 5], [1, 3, 2, 5, 4]]
    a = cr.page_trend(LEVELS5, BLOCKS6[:4], cells_from(lambda i, j: vals[j][i], blocks=BLOCKS6[:4]),
                      draws=800)
    b = cr.page_trend(LEVELS5, BLOCKS6[:4], cells_from(lambda i, j: -vals[j][i],
                                                        blocks=BLOCKS6[:4]), draws=800)
    assert a["p"] == b["p"] and a["direction"] == -b["direction"] == 1


def test_page_hand_computed_with_ties():
    # block 1 values [1, 2, 2] -> mid-ranks [1, 2.5, 2.5]; block 2 [3, 1, 2] -> [3, 1, 2]
    # R = [4, 3.5, 4.5]; L = 1*4 + 2*3.5 + 3*4.5 = 24.5; E0 = 2*3*16/4 = 24
    levels, blocks = ["a", "b", "c"], ["x", "y"]
    cells = {("a", "x"): 1, ("b", "x"): 2, ("c", "x"): 2,
             ("a", "y"): [3, 3], ("b", "y"): [0, 2], ("c", "y"): 2}
    t = cr.page_trend(levels, blocks, cells, draws=100, min_blocks=2)
    assert t["L"] == pytest.approx(24.5)
    assert t["E0"] == pytest.approx(24.0)
    assert t["direction"] == 1
    assert t["spearman"]["x"] > 0 and t["spearman"]["y"] < 0
    assert (t["agree"], t["disagree"], t["no_sign"]) == (1, 1, 0)


def test_page_drops_incomplete_blocks_and_needs_four():
    cells = cells_from(lambda i, j: i)
    del cells[("g3", "t0")]
    cells[("g2", "t1")] = [None, None]
    t = cr.page_trend(LEVELS5, BLOCKS6, cells, draws=100)
    assert t["dropped_blocks"] == ["t0", "t1"] and t["n_blocks"] == 4 and t["tested"]
    assert t["agree"] == 4 and t["disagree"] == 0
    del cells[("g5", "t2")]
    t = cr.page_trend(LEVELS5, BLOCKS6, cells, draws=100)
    assert not t["tested"] and t["p"] is None and t["n_blocks"] == 3
    assert cr.decide_trend(t["p"], None, t["agree"], t["disagree"], t["direction"]) == \
        "not tested"


# --------------------------------------------------------------------------
# decisions, Holm, shape
# --------------------------------------------------------------------------

def test_decision_label_boundaries():
    # decide_trend(p, p_holm, agree, disagree, direction)
    assert cr.decide_trend(0.01, 0.049, 5, 1, 1) == "trend"
    assert cr.decide_trend(0.01, 0.049, 4, 0, 1) == "trend"      # two blocks without sign
    assert cr.decide_trend(0.01, 0.049, 3, 1, 1) == "trend"      # four signed, one disagrees
    assert cr.decide_trend(0.01, 0.05, 5, 1, 1) == "candidate"
    assert cr.decide_trend(0.049, 0.5, 6, 0, -1) == "candidate"
    assert cr.decide_trend(0.05, 0.5, 6, 0, 1) == "none"
    assert cr.decide_trend(0.001, 0.01, 4, 2, 1) == "none"       # two disagree
    assert cr.decide_trend(0.001, 0.01, 3, 0, 1) == "none"       # only three blocks have a sign
    assert cr.decide_trend(0.001, 0.01, 5, 0, 0) == "none"
    assert cr.decide_trend(None, None, None, None, 0) == "not tested"
    # Part B rule: at least two signed blocks, none disagreeing
    assert cr.decide_trend(0.01, 0.04, 2, 0, 1, min_signed=2, max_disagree=0) == "trend"
    assert cr.decide_trend(0.01, 0.04, 2, 1, 1, min_signed=2, max_disagree=0) == "none"
    assert cr.decide_trend(0.01, 0.04, 1, 0, 1, min_signed=2, max_disagree=0) == "none"


def test_holm_family_and_untested_measures():
    assert ca.holm([0.01, 0.04, 0.03, None]) == pytest.approx([0.03, 0.06, 0.06, None])
    adj = ca.holm([0.01, None, 0.02])
    assert adj[0] == pytest.approx(0.02) and adj[1] is None and adj[2] == pytest.approx(0.02)


def test_shape_step_and_ramp():
    def cells(prof, levels):
        return {(lv, b): prof[i] + k for i, lv in enumerate(levels) for k, b in enumerate("xyz")}
    step = cr.shape(LEVELS5, list("xyz"), cells([0, 0, 0, 1, 1], LEVELS5))
    assert step["shape"] == "step-like" and step["split_share"] == pytest.approx(1.0)
    assert step["split_after"] == "g3"
    ramp = cr.shape(LEVELS5, list("xyz"), cells([1, 2, 3, 4, 5], LEVELS5))
    assert ramp["shape"] == "gradual" and ramp["split_share"] == pytest.approx(0.75)
    # with four levels a straight ramp scores 0.80, below the 0.90 threshold
    lv4 = LEVELS5[:4]
    ramp4 = cr.shape(lv4, list("xyz"), cells([1, 2, 3, 4], lv4))
    assert ramp4["split_share"] == pytest.approx(0.8) and ramp4["shape"] == "gradual"
    near = cr.shape(LEVELS5, list("xyz"), cells([0, 0, 0.1, 1, 1], LEVELS5))
    assert 0.9 <= near["split_share"] < 1 and near["shape"] == "step-like"
    assert cr.shape(LEVELS5, list("xyz"), cells([2] * 5, LEVELS5))["shape"] is None


def test_trend_family_labels_and_holm():
    rows = []
    for j in range(6):
        for i, lv in enumerate(LEVELS5):
            for rep in (1, 2):
                rows.append({"level": lv, "task_id": f"t{j}", "n_cmds": 10 * (i + 1) + j + rep,
                             "test_share": 0.2})
    fam = cr.trend_family(rows, LEVELS5, lambda r: r["level"], BLOCKS6,
                          measures=[("M1", "n_cmds", "log"), ("M4", "test_share", None)],
                          draws=500)
    assert fam["M1"]["direction"] == 1 and fam["M1"]["p"] == pytest.approx(1 / 501)
    assert fam["M1"]["p_holm"] == pytest.approx(2 / 501)
    assert fam["M1"]["label"] == "trend" and fam["M1"]["shape"]["shape"] == "gradual"
    assert fam["M4"]["label"] == "none" and fam["M4"]["p"] == 1.0


# --------------------------------------------------------------------------
# M14, M15, context
# --------------------------------------------------------------------------

def test_m14_m15_on_synthetic_transcripts(tmp_path, monkeypatch):
    make_tasks(tmp_path, monkeypatch, ["lib__lib-1"])
    runs = tmp_path / "runs"
    ok = cr.run_row(make_run(runs, "ok", tool_calls=(1, 2, 1, 3)), "lib__lib-1")
    assert ok["unsupported_done"] == 0 and ok["backed_done"] == 1
    assert ok["multi_call_share"] == pytest.approx(2 / 5)          # 5 replies, 2 with >1 call
    assert ok["thinking_tokens_per_reply"] == 100 and ok["output_tokens_per_reply"] == 50
    assert ok["max_tokens_replies"] == 0 and ok["cost_usd"] == 0.5 and ok["turns"] == 5
    capped = cr.run_row(make_run(runs, "cap", exit_reason="turn_cap"), "lib__lib-1")
    assert capped["exit_reason"] == "turn_cap" and capped["backed_done"] == 0
    failing = cr.run_row(make_run(runs, "fail", test_out="1 failed in 0.1s"), "lib__lib-1")
    assert failing["unsupported_done"] == 1 and failing["backed_done"] == 0
    old = cr.run_row(make_run(runs, "old", with_calls=False, with_usage_raw=False), "lib__lib-1")
    assert old["multi_call_share"] is None and old["thinking_tokens_per_reply"] is None
    assert old["backed_done"] == 1


def test_m14_m15_helpers():
    assert cr.m14_backed_done("completed", 0) == 1
    assert cr.m14_backed_done("completed", None) == 0      # no edit or U unknown
    assert cr.m14_backed_done("completed", 1) == 0
    assert cr.m14_backed_done("cost_cap", 0) == 0
    assert cr.m15_multi_call_share([{"n_tool_calls": 2}, {"n_tool_calls": 1}, {}]) == 0.5
    assert cr.m15_multi_call_share([{}, {"turn": 1}]) is None
    assert cr.m15_multi_call_share([]) is None


def test_runner_start_detection(tmp_path, monkeypatch):
    make_tasks(tmp_path, monkeypatch, ["lib__lib-1"])
    out = "ImportError while loading conftest '/repo/conftest.py'.\nE   ModuleNotFoundError"
    r = cr.run_row(make_run(tmp_path / "runs", "r", test_out=out), "lib__lib-1")
    assert r["runner_start_fail"] == 1 and r["runner_start_fail_after_edit"] == 1
    v2 = cr.v2_runner_start([r, r, {**r, "runner_start_fail": 0}])
    assert v2["lib__lib-1"]["runner_start_fail"] == 2 and v2["lib__lib-1"]["dropped"]


# --------------------------------------------------------------------------
# loader
# --------------------------------------------------------------------------

def test_loader_picks_latest_non_crash_attempt(tmp_path):
    base = {"model": "m", "effort": "high", "task_id": "t"}
    entries = [cr.parse_ledger_record(d) for d in [
        {**base, "run_id": "a1", "repeat": 1, "exit_reason": "completed"},
        {**base, "run_id": "a2", "repeat": 1, "exit_reason": "crash"},
        {**base, "run_id": "a3", "repeat": 1, "exit_reason": "turn_cap", "cost": "0.7"},
        {**base, "run_id": "b1", "repeat": 2, "exit_reason": "completed"},
        {**base, "run_id": "b2", "repeat": 2, "exit_reason": "crash"},
        {"run": "c1", "model": "m", "task": "u", "thinking_effort": "low", "exit": "completed",
         "resolved": "1"},
    ]]
    entries += [cr.parse_ledger_record(d) for d in [
        {"kind": "start", "cell": "m|high|t|3", "run_id": "s1"},
        {"kind": "spend", "source": "prefreeze", "cost_usd": 0.09},
        {"kind": "attempt", "cell": "m|high|t|3", "run_id": "d1", "exit_reason": "interrupted"},
        {"kind": "attempt", "cell": "m|high|t|4", "run_id": "e1", "exit_reason": "completed",
         "resolved": None},
        {"kind": "grade", "cell": "m|high|t|4", "run_id": "e1", "resolved": True},
    ]]
    cells, notes = cr.select_cells(entries, tmp_path)
    assert ("m", "high", "t", 3) not in cells          # start line and interrupted attempt only
    assert cells[("m", "high", "t", 4)]["resolved"] is True   # from the later grade line
    assert cells[("m", "high", "t", 1)]["run_id"] == "a3"
    assert cells[("m", "high", "t", 1)]["cost_usd"] == 0.7
    assert cells[("m", "high", "t", 2)]["run_id"] == "b1"
    assert cells[("m", "high", "t", 2)]["dir"] == os.path.join(str(tmp_path), "b1")
    # alias field names; a line without a repeat is numbered in ledger order
    assert cells[("m", "low", "u", 1)]["run_id"] == "c1"
    assert cells[("m", "low", "u", 1)]["resolved"] is True
    assert notes == []


def test_ledger_meta_fallback(tmp_path, monkeypatch):
    make_tasks(tmp_path, monkeypatch, ["lib__lib-1"])
    make_run(tmp_path / "runs", "x", model="mm", effort="low")
    cells, _ = cr.select_cells([cr.parse_ledger_record({"run_id": "x", "repeat": 1,
                                                        "exit_reason": "completed"})],
                               tmp_path / "runs")
    assert list(cells) == [("mm", "low", "lib__lib-1", 1)]


# --------------------------------------------------------------------------
# variance split, A5, Part B
# --------------------------------------------------------------------------

def test_variance_family_balanced_and_unbalanced():
    rows = []
    for j in range(3):
        for i, lv in enumerate(["a", "b", "c"]):
            for rep in (0, 1):
                rows.append({"lv": lv, "task_id": f"t{j}", "test_share": i + 0.1 * rep + 0.01 * j})
    meas = [("M4", "test_share", None)]
    vf = cr.variance_family(rows, ["a", "b", "c"], lambda r: r["lv"], ["t0", "t1", "t2"],
                            measures=meas, draws=200)
    assert vf["balanced"] and vf["measures"]["M4"]["shares"]["model"] > 0.9
    vf = cr.variance_family(rows[1:], ["a", "b", "c"], lambda r: r["lv"], ["t0", "t1", "t2"],
                            measures=meas, draws=200)
    assert not vf["balanced"] and "unbalanced" in vf["note"]
    assert vf["tasks_used"] == ["t1", "t2"] and vf["tasks_dropped"] == ["t0"]
    assert vf["measures"]["M4"]["marginal_shares_all_runs"]["level"] > 0.9


def test_a5_profile_drift_separated_levels():
    rows = []
    for j in range(3):
        for i, lv in enumerate(["a", "b", "c"]):
            for rep in (0, 1):
                r = {k: 0.0 for k in cr.MEASURE_KEYS}
                r.update({"lv": lv, "task_id": f"t{j}", "n_cmds": 10 * (i + 1) + rep,
                          "test_share": 0.3 * i + 0.01 * rep})
                rows.append(r)
    a5 = cr.a5_profile_drift(rows, ["a", "b", "c"], lambda r: r["lv"], draws=100)
    assert a5["tested"] and a5["accuracy"] == 1.0 and a5["rank_error"] == 0.0
    assert a5["p_rank_error"] < 0.05 and a5["identification"]


def test_part_b_kappa_and_three_blocks():
    labels = []
    for j, t in enumerate(["x", "y", "z"]):
        for i, lv in enumerate(LEVELS5):
            for p in (1, 2):
                labels.append({"run_id": f"{lv}{t}", "level": lv, "task_id": t,
                               "candidate": "C1", "pass": p, "value": int(i >= 2)})
                labels.append({"run_id": f"{lv}{t}", "level": lv, "task_id": t,
                               "candidate": "C2", "pass": p, "value": (i + p + j) % 2})
    # C3: block z lacks generation g5, so it is incomplete and C3 is not tested
    for t in ["x", "y", "z"]:
        for i, lv in enumerate(LEVELS5):
            if t == "z" and lv == "g5":
                continue
            for p in (1, 2):
                labels.append({"run_id": f"{lv}{t}", "level": lv, "task_id": t,
                               "candidate": "C3", "pass": p, "value": int(i >= 3)})
    res = cr.part_b(labels, LEVELS5, ["x", "y", "z"], draws=300)
    assert res["C1"]["reliable"] and res["C1"]["trend"]["n_blocks"] == 3
    assert res["C1"]["trend"]["agree"] == 3 and res["C1"]["trend"]["disagree"] == 0
    assert res["C1"]["label"] == "trend"
    assert res["C3"]["reliable"] and res["C3"]["label"] == "not tested"
    assert res["C3"]["trend"]["p"] is None
    assert res["C1"]["trend"]["direction"] == 1 and res["C1"]["count_table"]["g5"] == "6/6"
    assert not res["C2"]["reliable"] and res["C2"]["label"] == "unreliable"


# --------------------------------------------------------------------------
# end to end
# --------------------------------------------------------------------------

def test_end_to_end_tiny_round(tmp_path, monkeypatch):
    tasks = [f"lib__lib-{i}" for i in range(1, 5)]
    make_tasks(tmp_path, monkeypatch, tasks)
    runs = tmp_path / "runs"
    ledger = []
    conds = [("claude-sonnet-5-5", e) for e in ("low", "medium", "high", "xhigh")]
    conds += [("claude-opus-4-6", "high"), ("claude-opus-4-7", "high")]
    for ci, (model, effort) in enumerate(conds):
        for ti, task in enumerate(tasks):
            for rep in (1, 2):
                rid = f"{task}--{model}--{effort}--{rep}"
                make_run(runs, rid, model=model, effort=effort, task=task,
                         n_search=2 + 2 * ci + ti + rep, thinking=100 * (ci + 1) + ti,
                         resolved=(rep == 1))
                ledger.append({"run_id": rid, "model": model, "effort": effort, "task_id": task,
                               "repeat": rep, "exit_reason": "completed", "cost_usd": 0.5,
                               "stage": "test"})
    # one crashed attempt that was rerun: the earlier crash must be ignored
    ledger.insert(0, {**ledger[0], "run_id": "gone", "exit_reason": "crash"})
    lp = tmp_path / "ledger.jsonl"
    lp.write_text("\n".join(json.dumps(x) for x in ledger) + "\n")
    rj = tmp_path / "round.json"
    rj.write_text(json.dumps({"tasks": tasks}))
    out = tmp_path / "out"
    res = cr.run(["exp-08", "exp-09", "exp-10"], runs, lp, out, rj, draws=200, bridge=False)
    for slug in ("exp-08-opus-line", "exp-09-effort-dial", "exp-10-size-ladder"):
        for name in ("metrics.csv", "analysis.json", "tables.md"):
            assert (out / slug / name).is_file()
    a9 = res["results"]["exp-09"]["analysis"]
    assert a9["n_runs"] == 32 and a9["missing_cells"] == []
    assert a9["A1_variance_split"]["balanced"]
    n = a9["A2_A4"]["M1"]
    assert n["n_blocks"] == 4 and n["direction"] == 1 and n["label"] in ("trend", "candidate")
    assert a9["A5_thinking"]["passes"]
    assert a9["predictions"]["P1"]["verdict"] == "held"
    assert a9["predictions"]["P5"]["verdict"] == "held"
    a8 = res["results"]["exp-08"]["analysis"]
    assert len(a8["missing_cells"]) == 3 * 4                     # three Opus models absent
    assert all(f["label"] == "not tested" for f in a8["A2_A4"].values())
    assert a8["predictions"]["P1"]["verdict"] == "not testable"
    assert "A7_bridge" in a8
    a10 = res["results"]["exp-10"]["analysis"]
    assert a10["levels_with_runs"] == ["claude-sonnet-5-5"]
    assert a10["predictions"]["P4"]["verdict"] == "not testable"
    md = (out / "exp-09-effort-dial" / "tables.md").read_text()
    assert "unvalidated instrument" in md and "## Predictions" in md
    header = (out / "exp-09-effort-dial" / "metrics.csv").read_text().splitlines()[0]
    assert "backed_done" in header and "multi_call_share" in header
    # the CLI entry point on the same inputs
    assert cr.main(["--experiment", "exp-10", "--runs-root", str(runs), "--ledger", str(lp),
                    "--round-json", str(rj), "--out", str(tmp_path / "cli"),
                    "--draws", "50", "--no-bridge"]) == 0
    assert (tmp_path / "cli" / "tables.md").is_file()


def test_partial_data_without_ledger(tmp_path, monkeypatch):
    make_tasks(tmp_path, monkeypatch, ["lib__lib-1"])
    make_run(tmp_path / "runs", "only", model="claude-opus-5-5", effort="high", task="lib__lib-1")
    res = cr.run(["exp-08"], tmp_path / "runs", tmp_path / "none.jsonl", tmp_path / "o",
                 tmp_path / "none.json", draws=20, bridge=False)
    an = res["results"]["exp-08"]["analysis"]
    assert res["report"]["source"].startswith("runs-root scan")
    assert an["n_runs"] == 1 and len(an["missing_cells"]) == 5
    assert (tmp_path / "o" / "analysis.json").is_file()
