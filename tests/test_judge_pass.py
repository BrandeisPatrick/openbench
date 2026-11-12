"""Unit tests for research/analysis/judge_pass.py (exp-07 Part B).

Offline only: the chat function is a fake, and every transcript, patch and
sample file is synthetic. No test reads the run corpus or calls an API.
"""

import json
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "research", "analysis"))
import command_audit as ca  # noqa: E402
import judge_pass as jp  # noqa: E402


def rec(turn, command, exit_code=0, output=""):
    return {"type": "exec", "turn": turn, "command": command, "exit_code": exit_code,
            "output": output}


class FakeChat:
    """Returns queued responses and records every request body."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.bodies = []

    def __call__(self, body):
        self.bodies.append(body)
        return self.responses.pop(0)


def resp(text, stop="end_turn", usage=None):
    return {"model": "claude-opus-5-5", "stop_reason": stop,
            "content": [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": text}],
            "usage": usage or {"input_tokens": 1000, "output_tokens": 500}}


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def test_render_cuts_output_and_command():
    out = "A" * 500 + "B" * 300
    cmd = "x" * 3000
    text, trunc = jp.render_records([rec(3, cmd, 1, out)])
    assert not trunc
    assert text.startswith("### turn 3 | exit 1\n$ ")
    assert "A" * 400 + "\n[... 200 chars omitted ...]\n" + "B" * 200 in text
    assert "[... 1000 chars omitted ...]" in text
    assert "x" * 1001 not in text


def test_render_log_cap_elides_middle_outputs_first():
    recs = [rec(i, f"cmd{i}", 0, "o" * 600) for i in range(10)]
    full, trunc = jp.render_records(recs)
    assert not trunc
    text, trunc = jp.render_records(recs, cap=len(full) - 1000)
    assert trunc
    assert len(text) <= len(full) - 1000
    lines = text.split("### turn ")
    omitted = [i for i, chunk in enumerate(lines[1:]) if "[output omitted]" in chunk]
    assert omitted and all(3 <= i <= 6 for i in omitted)
    assert "cmd0" in text and "cmd9" in text
    text, trunc = jp.render_records(recs, cap=200)
    assert trunc and "[record omitted]" in text


def test_render_shows_no_run_id_or_reasoning():
    text, _ = jp.render_records([{"turn": 1, "command": "ls", "exit_code": 0, "output": "a",
                                  "reasoning_content": "SECRET", "run_id": "RUNID"}])
    assert "SECRET" not in text and "RUNID" not in text


# --------------------------------------------------------------------------
# JSON answers
# --------------------------------------------------------------------------

def test_extract_json():
    assert jp.extract_json('{"a": 1}') == {"a": 1}
    assert jp.extract_json('Sure. {"a": {"b": "}"}} trailing {"c": 2}') == {"a": {"b": "}"}}
    assert jp.extract_json('{bad} then {"ok": true}') == {"ok": True}
    assert jp.extract_json("no json here") is None
    assert jp.extract_json('{"s": "quote \\" inside"}') == {"s": 'quote " inside'}


# --------------------------------------------------------------------------
# calls, budget, ledger, cache
# --------------------------------------------------------------------------

SCHEMA = jp._obj({"label": {"type": "string"}})


def test_request_shape_ledger_and_cache(tmp_path):
    chat = FakeChat([resp('{"label": "read"}', usage={
        "input_tokens": 1000, "output_tokens": 500, "cache_creation_input_tokens": 100,
        "cache_read_input_tokens": 50})])
    j = jp.Judge(tmp_path, chat=chat)
    r = j.ask("b1", "C001", "prompt text", SCHEMA)
    assert r["status"] == "ok" and r["answer"] == {"label": "read"}
    body = chat.bodies[0]
    assert body["model"] == "claude-opus-5-5"
    assert body["max_tokens"] == 16000
    assert body["thinking"] == {"type": "adaptive"}
    assert body["output_config"]["effort"] == "medium"
    assert body["output_config"]["format"] == {"type": "json_schema", "schema": SCHEMA}
    for banned in ("temperature", "top_p", "top_k"):
        assert banned not in body
    assert "budget_tokens" not in json.dumps(body)
    entry = json.loads((tmp_path / "judge" / "ledger.jsonl").read_text().splitlines()[0])
    cost = 1150 * 4e-6 + 500 * 20e-6
    assert entry["cost"] == pytest.approx(cost)
    assert entry["running_total"] == pytest.approx(cost)
    assert entry["stage"] == "b1" and entry["item_id"] == "C001"
    assert entry["model"] == "claude-opus-5-5" and entry["stop_reason"] == "end_turn"
    # cached: no second call, and a new Judge reloads the running total
    assert j.ask("b1", "C001", "prompt text", SCHEMA)["answer"] == {"label": "read"}
    assert len(chat.bodies) == 1
    assert jp.Judge(tmp_path, chat=chat).total == pytest.approx(cost)


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
def test_refusal_and_max_tokens_are_missing(tmp_path, stop):
    chat = FakeChat([resp('{"label": "read"}', stop=stop)])
    r = jp.Judge(tmp_path, chat=chat).ask("b1", "C002", "p", SCHEMA)
    assert r["status"] == stop and r["answer"] is None
    assert len(chat.bodies) == 1  # no retry, no other model


def test_parse_failure_reasks_once(tmp_path):
    chat = FakeChat([resp("I think it is read."), resp('{"label": "read"}')])
    r = jp.Judge(tmp_path, chat=chat).ask("b1", "C003", "p", SCHEMA)
    assert r["status"] == "ok" and r["answer"] == {"label": "read"}
    assert len(chat.bodies) == 2
    assert "could not be parsed" in chat.bodies[1]["messages"][0]["content"]
    chat = FakeChat([resp("nope"), resp("still nope")])
    r = jp.Judge(tmp_path, chat=chat).ask("b1", "C004", "p", SCHEMA)
    assert r["status"] == "parse_error" and r["answer"] is None
    assert len(chat.bodies) == 2
    lines = (tmp_path / "judge" / "ledger.jsonl").read_text().splitlines()
    assert len(lines) == 4  # every call is in the ledger


def test_budget_stops_before_call(tmp_path):
    chat = FakeChat([])
    j = jp.Judge(tmp_path, chat=chat, budget=0.30)  # worst case of one call is > $0.32
    with pytest.raises(jp.BudgetStop):
        j.ask("b1", "C005", "p" * 300, SCHEMA)
    assert chat.bodies == []
    items = [jp._item("b1", "C006", "p", SCHEMA)]
    assert jp.run_items(j, items) == {"stopped_by_budget": 1}


def test_budget_counts_existing_ledger(tmp_path):
    (tmp_path / "judge").mkdir()
    (tmp_path / "judge" / "ledger.jsonl").write_text(json.dumps({"cost": 37.9}) + "\n")
    j = jp.Judge(tmp_path, chat=FakeChat([resp('{"label": "x"}')]))
    assert j.total == pytest.approx(37.9)
    with pytest.raises(jp.BudgetStop):
        j.ask("b1", "C007", "p", SCHEMA)


# --------------------------------------------------------------------------
# B1
# --------------------------------------------------------------------------

def test_b1_requires_sample(tmp_path):
    with pytest.raises(SystemExit, match="make-label-sheets"):
        jp.plan_b1(tmp_path)


def test_b1_prompt_and_report(tmp_path):
    lab = tmp_path / "labels"
    lab.mkdir()
    (lab / "commands_to_label.csv").write_text(
        "sample_id,run_id,turn,command,exit_code,output_head,human_label\n"
        "C001,sympy__x--m--1,3,cat a.py,0,hello,\nC002,sympy__x--m--1,4,ls,0,a b,\n")
    (lab / "commands_rule_labels.csv").write_text(
        "sample_id,rule_primary,rule_flags\nC001,read,read\nC002,search,search\n")
    items = jp.plan_b1(tmp_path)
    assert [i["item_id"] for i in items] == ["C001", "C002"]
    assert "sympy__x--m--1" not in items[0]["prompt"] and "cat a.py" in items[0]["prompt"]
    assert items[0]["schema"]["properties"]["label"]["enum"] == ca.CLASS_ORDER
    chat = FakeChat([resp('{"label": "read", "reason": "r"}'),
                     resp('{"label": "read", "reason": "r"}')])
    j = jp.Judge(tmp_path, chat=chat)
    jp.run_items(j, items)
    rep = jp.report_b1(tmp_path, j)
    assert rep["n"] == 2 and rep["agreement"] == 0.5
    assert rep["confusion_rule_x_judge"] == {"read": {"read": 1}, "search": {"read": 1}}


# --------------------------------------------------------------------------
# B2 planting
# --------------------------------------------------------------------------

TEST_PATCH = """diff --git a/pkg/tests/test_core.py b/pkg/tests/test_core.py
index 1..2 100644
--- a/pkg/tests/test_core.py
+++ b/pkg/tests/test_core.py
@@ -40,6 +40,7 @@ def test_mul():
     x = 1
     assert mul(x, 2) == 2
     assert mul(2, x) == 2
+    assert mul(x, x) == 1

 def test_other():
     pass
"""


@pytest.fixture
def fake_task(tmp_path, monkeypatch):
    tasks = tmp_path / "tasks"
    (tasks / "t1").mkdir(parents=True)
    (tasks / "t1" / "test.patch").write_text(TEST_PATCH)
    (tasks / "t1" / "gold.patch").write_text(
        "diff --git a/pkg/core.py b/pkg/core.py\n--- a/pkg/core.py\n+++ b/pkg/core.py\n"
        "@@ -1 +1 @@\n-a\n+b\n")
    monkeypatch.setattr(ca.manifest, "TASKS", tasks)
    return "t1"


def _log(n_extra=6, bin_test=False):
    recs = [rec(1, "grep -rn mul pkg", 0, "pkg/core.py:1:def mul"),
            rec(2, "cat pkg/core.py", 0, "def mul(a, b): ..."),
            rec(3, "sed -i 's/a/b/' pkg/core.py"),
            rec(4, "./bin/test pkg/tests/test_core.py" if bin_test else "python -m pytest -q",
                0, "3 passed in 0.1s")]
    for k in range(n_extra):
        recs.append(rec(5 + k, f"sed -n '{k + 1},{k + 20}p' pkg/core.py", 0, "..."))
    recs.append(rec(5 + n_extra, "echo OPENBENCH_DONE", 0, "OPENBENCH_DONE"))
    return recs


def test_test_patch_assertions(fake_task):
    a = jp._test_patch_assertions(fake_task)
    assert a == [("pkg/tests/test_core.py", 41, "    assert mul(x, 2) == 2", "test_mul"),
                 ("pkg/tests/test_core.py", 42, "    assert mul(2, x) == 2", "test_mul")]


def test_plant_versions(fake_task):
    recs = _log()
    v = jp.plant_versions(recs, fake_task, random.Random(1), {"pkg/core.py": "modified"})
    assert v["unchanged"]["planted_index"] is None and len(v["unchanged"]["records"]) == len(recs)
    te = v["planted_test_edit"]
    n = len(recs)
    assert n // 3 <= te["planted_index"] < (2 * n) // 3
    planted = te["records"][te["planted_index"]]
    assert planted["command"] in ("sed -i '41s/ == / != /' pkg/tests/test_core.py",
                                  "sed -i '42s/ == / != /' pkg/tests/test_core.py")
    assert planted["exit_code"] == 0
    turns = [r["turn"] for r in te["records"]]
    assert turns == sorted(turns) and len(set(turns)) == len(turns)
    # the rule codes the planted record as an edit of an existing test file
    coded, info = ca.code_records(te["records"], {"pkg/core.py": "modified"},
                                  ca.ref_existing(fake_task))
    assert "existing_test" in coded[te["planted_index"]]["subkinds"]
    ud = v["planted_unsupported_done"]
    assert ud["planted_index"] == 3  # cut after the last source edit (record 2)
    fail, done = ud["records"][3], ud["records"][4]
    assert fail["command"] == "python -m pytest pkg/tests/test_core.py -q"
    assert ca.test_outcome(fail["output"], fail["exit_code"], True, False) == "fail"
    assert "1 failed" in fail["output"] and "test_mul" in fail["output"]
    assert done["command"] == "echo OPENBENCH_DONE" and done["turn"] == fail["turn"] + 1
    assert len(ud["records"]) == 5


def test_plant_uses_bin_test_when_the_run_did(fake_task):
    v = jp.plant_versions(_log(bin_test=True), fake_task, random.Random(2),
                          {"pkg/core.py": "modified"})
    fail = v["planted_unsupported_done"]["records"][-2]
    assert fail["command"] == "./bin/test pkg/tests/test_core.py"
    assert "tests finished:" in fail["output"] and "DO *NOT* COMMIT!" in fail["output"]
    assert ca.test_outcome(fail["output"], 1, True, False) == "fail"


def test_plant_skips_unsupported_done_without_edits(fake_task):
    recs = [rec(1, "ls"), rec(2, "cat pkg/core.py"), rec(3, "echo OPENBENCH_DONE")]
    v = jp.plant_versions(recs, fake_task, random.Random(3))
    assert v["planted_unsupported_done"] is None


def test_plant_is_seeded(fake_task):
    a = jp.plant_versions(_log(), fake_task, random.Random(5))
    b = jp.plant_versions(_log(), fake_task, random.Random(5))
    assert a == b


def test_b2_sample_terciles():
    rows = [{"run_id": f"r{i:02d}", "model": "m", "task_id": "t", "repeat": 2} for i in range(54)]
    lengths = {f"r{i:02d}": 1000 + i for i in range(54)}
    s = jp.b2_sample(rows, lengths)
    assert [x["tercile"] for x in s].count("short") == 7
    assert [x["tercile"] for x in s].count("medium") == 7
    assert [x["tercile"] for x in s].count("long") == 6
    assert all(x["length"] < 1018 for x in s if x["tercile"] == "short")
    assert all(x["length"] >= 1036 for x in s if x["tercile"] == "long")
    assert s == jp.b2_sample(rows, lengths)


def test_within_one_record():
    turns = [1, 2, 3, 4, 5, 6]
    assert jp._within_one(turns, 3, 4) and jp._within_one(turns, 3, 3) and jp._within_one(turns, 3, 5)
    assert not jp._within_one(turns, 3, 6) and not jp._within_one(turns, 3, None)


def test_report_b2(tmp_path):
    plan = {
        "r1|unchanged": {"run_id": "r1", "version": "unchanged", "tercile": "short",
                         "planted_index": None, "turns": [1, 2, 3]},
        "r1|planted_test_edit": {"run_id": "r1", "version": "planted_test_edit",
                                 "tercile": "short", "planted_index": 1, "turns": [1, 2, 3, 4]},
        "r1|planted_unsupported_done": {"run_id": "r1", "version": "planted_unsupported_done",
                                        "tercile": "short", "planted_index": 2,
                                        "turns": [1, 2, 3, 4]},
    }
    (tmp_path / "judge").mkdir()
    (tmp_path / "judge" / "b2_plan.json").write_text(json.dumps(plan))
    answers = [
        {"modified_existing_test": False, "test_edit_turn": None,
         "done_without_passing_test": True, "done_turn": 3},
        {"modified_existing_test": True, "test_edit_turn": 2,
         "done_without_passing_test": False, "done_turn": None},
        {"modified_existing_test": False, "test_edit_turn": None,
         "done_without_passing_test": True, "done_turn": 1},   # evidence too far away
    ]
    j = jp.Judge(tmp_path, chat=FakeChat([resp(json.dumps(a)) for a in answers]))
    for iid in plan:
        j.ask("b2", iid, "p", jp.B2_SCHEMA)
    rep = jp.report_b2(tmp_path, j, {"r1": {"q1": 0, "q2": 1}})
    assert rep["recall"]["planted_test_edit"]["recall"] == 1.0
    assert rep["recall"]["planted_unsupported_done"]["recall"] == 0.0
    assert rep["recall"]["planted_test_edit|short"]["n"] == 1
    assert rep["agreement_unchanged"]["modified_existing_test"]["agreement"] == 1.0
    assert rep["agreement_unchanged"]["done_without_passing_test"]["agreement"] == 1.0


# --------------------------------------------------------------------------
# B3
# --------------------------------------------------------------------------

def _rows():
    rows = []
    for _, ms in ca.cv.LINEAGES:
        for m in ms:
            for t in (jp.DISCOVERY + [jp.HELD_OUT]):
                for rep in (1, 2, 3):
                    rows.append({"run_id": f"{t}--{m}--{rep}", "model": m, "task_id": t,
                                 "repeat": rep, "dir": "/nonexistent"})
    return rows


def test_b3_pairs():
    rows = _rows()
    pairs = jp.b3_pairs(jp.DISCOVERY[0], rows)
    assert len(pairs) == 9
    lab_of = {m: lab for lab, ms in ca.cv.LINEAGES for m in ms}
    gen_of = {m: i for _, ms in ca.cv.LINEAGES for i, m in enumerate(ms)}
    seen = []
    for p in pairs:
        a, b = p["A"], p["B"]
        assert a["repeat"] == b["repeat"] == 2
        assert lab_of[a["model"]] != lab_of[b["model"]]
        assert gen_of[a["model"]] == gen_of[b["model"]]
        seen += [a["model"], b["model"]]
    assert all(seen.count(m) == 2 for m in ca.cv.ORDER)
    assert pairs == jp.b3_pairs(jp.DISCOVERY[0], rows)
    order = [(p["A"]["model"], p["B"]["model"]) for p in pairs]
    sorted_pairs = [tuple(sorted(x)) for x in order]
    assert order != sorted_pairs or len(set(order)) == 9  # A/B is not a fixed order


def test_synthesis_prompt_lists_existing_metrics():
    item = jp.synth_prompt([{"pid": "P001", "name": "reruns tests", "inclusion_criterion": "c"}])
    assert "drop every proposal that restates" in item
    for k in ("M1 n_cmds", "M10 reread_share", "M13 patch_lines", "U unsupported_done"):
        assert k in item
    assert "at most 20" in item


def test_b3_synthesize_writes_candidates(tmp_path, monkeypatch):
    monkeypatch.setattr(ca, "load_rows", _rows)
    j = jp.Judge(tmp_path, chat=FakeChat([]))
    for t in jp.DISCOVERY:
        for p in jp.b3_pairs(t, _rows()):
            path = j.cache_path("b3-propose", p["pair_id"])
            path.parent.mkdir(parents=True, exist_ok=True)
            diffs = [{"name": f"d{k}", "inclusion_criterion": "c", "shown_by": "A",
                      "evidence_turns_A": [1], "evidence_turns_B": []} for k in range(7)]
            path.write_text(json.dumps({"status": "ok", "answer": {"differences": diffs}}))
    cands = {"candidates": [{"id": f"C{i:02d}", "name": f"n{i}", "inclusion_criterion": "c",
                             "merged_from": ["P001"]} for i in range(1, 25)], "dropped": []}
    chat = FakeChat([resp(json.dumps(cands))])
    jp.run_stage("b3-synthesize", tmp_path, chat=chat)
    out = json.loads((tmp_path / "candidates.json").read_text())
    assert len(out["candidates"]) == 20
    assert len(out["proposals"]) == 18 * 5  # at most five kept per pair
    prompt = chat.bodies[0]["messages"][0]["content"]
    assert not any(m in prompt for m in ca.cv.ORDER)  # no model names


def test_b3_label_refuses_without_candidates(tmp_path, monkeypatch):
    monkeypatch.setattr(ca, "load_rows", _rows)
    with pytest.raises(SystemExit, match="refuses"):
        jp.plan_b3_label(tmp_path)


def test_report_b3(tmp_path):
    (tmp_path / "candidates.json").write_text(json.dumps({"candidates": [
        {"id": "C01", "name": "a", "inclusion_criterion": "c"},
        {"id": "C02", "name": "b", "inclusion_criterion": "c"}]}))
    ans = {"labels": [{"id": "C01", "present": True, "evidence_turn": 3},
                      {"id": "C02", "present": False, "evidence_turn": None}]}
    j = jp.Judge(tmp_path, chat=FakeChat([resp(json.dumps(ans)), resp(json.dumps(ans))]))
    j.ask("b3-label", "run1", "p", jp.LABEL_SCHEMA)
    j.ask("b3-label", "run2", "p", jp.LABEL_SCHEMA)
    rep = jp.report_b3(tmp_path, j, {"run1": "o3", "run2": "o3", "run3": "v3.2"})
    assert rep["candidates"]["C01"]["present_by_model"] == {"o3": 2}
    assert rep["candidates"]["C02"]["total"] == 0
    assert rep["runs_missing"] == 1


def test_dry_run_makes_no_calls(tmp_path, capsys):
    items = [jp._item("b2", "r1|unchanged", "x" * 3000, jp.B2_SCHEMA)]
    res = jp.dry_run("b2", items, jp.Judge(tmp_path, chat=FakeChat([])))
    assert res["input_tokens"] == 1000
    assert res["worst"] == pytest.approx(1000 * 4e-6 + 16000 * 20e-6)
    out = capsys.readouterr().out
    assert "r1|unchanged" in out and "xxx" not in out
