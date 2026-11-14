"""Unit tests for research/analysis/claude_round_judge.py (exp-08 Part B judge).

Offline only: the chat function is a fake, the round (round.json, ledger,
transcripts) is synthetic, and git runs in a temporary repository. No test
reads the run corpus, needs credentials or calls an API.
"""

import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "research", "analysis"))
import claude_round as cr  # noqa: E402
import claude_round_judge as crj  # noqa: E402

from openbench.runners import round_runner as rr  # noqa: E402
from openbench.runners.protocols.providers import claude_cost  # noqa: E402

OPUS = ["claude-opus-4-6", "claude-opus-4-7", "claude-opus-4-8", "claude-opus-5",
        "claude-opus-5-5"]
TASKS = [f"lib__lib-{i}" for i in range(1, 7)]
USAGE = {"input_tokens": 1000, "output_tokens": 500}


def round_json(d, reserve=10.0):
    cfg = {"round": "test", "tasks": TASKS, "bridge_task": TASKS[0], "seed": 20261113,
           "ceiling_usd": 125.0, "judge_reserve_usd": reserve, "spend_before_freeze_usd": 0.0,
           "cap_usd_by_family": {"opus": 6.0, "fable": 8.0, "sonnet": 3.0, "haiku": 1.0},
           "max_turns": 100, "wall_clock_s": 3600, "concurrency": 3, "cpus": 2, "memory": "3g",
           "repeats": 2, "pilot_effort": "high", "opus_models": OPUS, "opus_effort": "high",
           "sonnet_model": "claude-sonnet-5-5", "sonnet_efforts": ["low", "medium", "high"],
           "haiku_model": "claude-haiku-5-5", "fable_model": "claude-fable-5-2",
           "ladder_effort": "high", "drops": []}
    d.mkdir(parents=True, exist_ok=True)
    p = d / "round.json"
    p.write_text(json.dumps(cfg))
    return p


def make_run(runs, run_id, model, task, turns=None):
    d = runs / run_id
    d.mkdir(parents=True)
    turns = turns or [("I will search for the bug.", "grep -n x pkg/a.py", 0, "1:x"),
                      ("Now run the tests.", "pytest -q", 0, "1 passed")]
    lines = [{"type": "meta", "model": model, "task_id": task, "thinking_effort": "high"}]
    for i, (think, cmd, rc, out) in enumerate(turns, 1):
        lines.append({"type": "api_response", "turn": i, "content": f"text by {model}",
                      "reasoning_content": think, "usage_raw": {"output_tokens": 5},
                      "stop_reason": "tool_use", "n_tool_calls": 1})
        lines.append({"type": "exec", "turn": i, "command": cmd, "exit_code": rc, "output": out})
    lines.append({"type": "final", "exit_reason": "completed", "turns": len(turns)})
    (d / "raw_transcript.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    return d


def attempt(run_id, model, task, rep, exit_reason="completed"):
    return {"kind": "attempt", "run_id": run_id, "cell": f"{model}|high|{task}|{rep}",
            "exit_reason": exit_reason, "cost_usd": 1.0}


@pytest.fixture
def rnd(tmp_path):
    """A full synthetic exp-08 round: 5 models x 6 tasks x 2 repeats, plus a crashed attempt
    and a superseded attempt on one cell, and some non-exp-08 runs."""
    rdir = tmp_path / "round"
    rj = round_json(rdir)
    runs = tmp_path / "runs"
    entries = []
    for t in TASKS:
        for m in OPUS:
            for rep in (1, 2):
                rid = f"{m}-{t}-r{rep}"
                make_run(runs, rid, m, t)
                entries.append(attempt(rid, m, t, rep))
    # cell (opus-4-6, task 1, rep 1): a later completed attempt, then a crash -> later completed
    make_run(runs, "late", OPUS[0], TASKS[0])
    entries.append(attempt("late", OPUS[0], TASKS[0], 1))
    entries.append(attempt("crashed", OPUS[0], TASKS[0], 1, exit_reason="crash"))
    # other effort / other model: not exp-08 cells
    make_run(runs, "sonnet", "claude-sonnet-5-5", TASKS[0])
    entries.append({**attempt("sonnet", "claude-sonnet-5-5", TASKS[0], 1),
                    "cell": f"claude-sonnet-5-5|high|{TASKS[0]}|1"})
    entries.append({**attempt("lowfx", OPUS[0], TASKS[0], 1),
                    "cell": f"{OPUS[0]}|low|{TASKS[0]}|1"})
    (rdir / "ledger.jsonl").write_text("".join(json.dumps(e) + "\n" for e in entries))
    cfg = crj.load_cfg(rj)
    return {"cfg": cfg, "rj": rj, "runs": runs, "out": tmp_path / "judge",
            "cells": crj.exp08_cells(cfg, runs)}


class FakeChat:
    def __init__(self, reply):
        self.reply = reply          # callable(body) -> text, or a list of texts
        self.bodies = []

    def __call__(self, body):
        self.bodies.append(body)
        if callable(self.reply):
            text = self.reply(body)
        else:
            text = self.reply.pop(0)
        return {"model": crj.MODEL, "stop_reason": "end_turn", "usage": dict(USAGE),
                "content": [{"type": "thinking", "thinking": "..."},
                            {"type": "text", "text": text}]}


def propose_reply(body):
    return json.dumps({"differences": [
        {"name": "runs tests early", "rule": "Does the run execute tests in its first 5 turns?",
         "shown_by": "A", "evidence": "turn 2"},
        {"name": "writes scratch", "rule": "Does the run write a script under /tmp?",
         "shown_by": "B", "evidence": "none"}]})


FREEZE_REPLY = json.dumps({"candidates": [
    {"name": "early tests", "rule": "Tests run in the first 5 turns?", "merged_from": ["P001"]},
    {"name": "scratch script", "rule": "Writes a script under /tmp?", "merged_from": ["P002"]}]})


def label_reply(body):
    prompt = body["messages"][0]["content"]
    return json.dumps({"answers": {"C01": "yes", "C02": "no" if "grep" in prompt else "yes"}})


def judge(rnd, reply):
    chat = FakeChat(reply)
    return crj.Judge(rnd["cfg"], rnd["out"], chat=chat), chat


# --------------------------------------------------------------------------
# run selection
# --------------------------------------------------------------------------

def test_b1_selection_endpoints_both_orders(rnd):
    items, missing = crj.plan_propose(rnd["cfg"], rnd["cells"])
    assert missing == [] and len(items) == 12
    assert {it["meta"]["task_id"] for it in items} == set(TASKS[:3])
    first = [it for it in items if it["item_id"].startswith(f"{TASKS[0]}|r1|")]
    assert [it["meta"]["order"] for it in first] == ["old-first", "new-first"]
    old_first, new_first = first
    assert old_first["meta"]["A"]["model"] == "claude-opus-4-6"
    assert old_first["meta"]["B"]["model"] == "claude-opus-5-5"
    assert new_first["meta"]["A"]["model"] == "claude-opus-5-5"
    # latest non-crash attempt of the cell
    assert old_first["meta"]["A"]["run_id"] == "late"
    assert new_first["meta"]["B"]["run_id"] == "late"
    # the same two logs, swapped
    a1 = old_first["prompt"].split("=== Run A ===")[1].split("=== Run B ===")
    a2 = new_first["prompt"].split("=== Run A ===")[1].split("=== Run B ===")
    assert a1[0].strip() == a2[1].split("\nList at most")[0].strip()


def test_b3_selection_and_missing(rnd):
    cands = [{"id": "C01", "name": "n", "rule": "r?"}]
    items, missing = crj.plan_label(rnd["cfg"], rnd["cells"], cands)
    assert missing == [] and len(items) == 60
    assert {it["meta"]["task_id"] for it in items} == set(TASKS[3:])
    assert {it["meta"]["level"] for it in items} == set(OPUS)
    assert sorted({it["pass"] for it in items}) == [1, 2]
    cells = dict(rnd["cells"])
    del cells[("claude-opus-4-8", TASKS[4], 2)]
    items, missing = crj.plan_label(rnd["cfg"], cells, cands)
    assert len(items) == 58 and missing == [f"claude-opus-4-8 {TASKS[4]} repeat 2"]


def test_select_ignores_other_efforts_and_models(rnd):
    assert all(m in OPUS for m, _, _ in rnd["cells"])
    assert len(rnd["cells"]) == 60


# --------------------------------------------------------------------------
# identity stripping and shortening
# --------------------------------------------------------------------------

def test_identity_stripped_from_prompt(tmp_path, rnd):
    runs = tmp_path / "runs2"
    turns = [("As Claude Opus 4.6, I think; opus-4.6 and Sonnet 5 differ.",
              "echo claude-opus-5-5 && ls /tmp/RUN-xyz", 0,
              "model: claude-opus-5-5\nAnthropic claude_opus 5.5 FABLE-5-2 haiku 4.5"),
             ("fine", "pytest -q", 1, "CLAUDE-OPUS-4-6 failed")]
    make_run(runs, "RUN-xyz", "claude-opus-4-6", TASKS[0], turns)
    text, _ = crj.render_run({"dir": runs / "RUN-xyz", "run_id": "RUN-xyz"})
    low = text.lower()
    for bad in ["claude", "opus", "sonnet", "haiku", "fable", "anthropic", "4-6", "5-5",
                "run-xyz", "thinking_effort", "text by"]:
        assert bad not in low, bad
    assert "[model]" in text and "[run]" in text and "$ pytest -q" in text
    for it in crj.plan_propose(rnd["cfg"], rnd["cells"])[0]:
        assert not any(m in it["prompt"] for m in OPUS)
        assert "late" not in it["prompt"]


def test_shortening_rule():
    long_out = "A" * 500 + "B" * 300
    long_think = "t" * 2000
    text, trunc = crj.render_turns([{"turn": 1, "thinking": long_think, "command": "c" * 3000,
                                     "exit_code": 2, "output": long_out}])
    assert not trunc
    assert "A" * crj.OUT_HEAD + f"\n[... {800 - crj.OUT_HEAD - crj.OUT_TAIL} chars cut ...]\n" \
        + "B" * crj.OUT_TAIL in text
    assert f"[... {2000 - crj.THINK_HEAD - crj.THINK_TAIL} chars cut ...]" in text
    assert f"[... {3000 - crj.CMD_HEAD - crj.CMD_TAIL} chars cut ...]" in text
    assert "[exit 2]" in text
    # per-run cap: middle turns lose thinking and output first, ends kept
    turns = [{"turn": i, "thinking": f"think{i}", "command": f"cmd{i}", "exit_code": 0,
              "output": "o" * 500} for i in range(10)]
    full, trunc = crj.render_turns(turns)
    assert not trunc
    text, trunc = crj.render_turns(turns, cap=len(full) - 1000)
    assert trunc and len(text) <= len(full) - 1000
    chunks = text.split("### turn ")[1:]
    omitted = [i for i, c in enumerate(chunks) if "[thinking and output omitted]" in c]
    assert omitted and all(3 <= i <= 6 for i in omitted)
    assert "think0" in text and "think9" in text and "cmd5" in text
    text, trunc = crj.render_turns(turns, cap=300)
    assert trunc and "[turn omitted]" in text
    # default cap is the module constant, same for every run
    assert crj.render_turns(turns) == crj.render_turns(turns, cap=crj.RUN_CAP)


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------

def test_parse_replies():
    good = crj.parse_propose(json.loads(propose_reply(None)))
    assert [d["shown_by"] for d in good] == ["A", "B"]
    assert crj.parse_propose({"differences": [{"name": "x", "rule": "y", "shown_by": "C"}]}) == []
    assert crj.parse_propose({"diffs": []}) is None and crj.parse_propose(None) is None
    many = {"differences": [{"name": f"n{i}", "rule": "r", "shown_by": "A"} for i in range(20)]}
    assert len(crj.parse_propose(many)) == crj.PROPOSE_MAX
    fr = crj.parse_freeze(json.loads(FREEZE_REPLY))
    assert [c["id"] for c in fr] == ["C01", "C02"]
    big = {"candidates": [{"name": f"n{i}", "rule": "r"} for i in range(20)]}
    assert len(crj.parse_freeze(big)) == 12 and crj.parse_freeze({"candidates": []}) is None
    ids = ["C01", "C02"]
    assert crj.parse_label({"answers": {"C01": "Yes", "C02": "no"}}, ids) == {"C01": 1, "C02": 0}
    assert crj.parse_label({"answers": {"C01": True, "C02": False}}, ids) == {"C01": 1, "C02": 0}
    assert crj.parse_label({"answers": {"C01": "yes"}}, ids) is None
    assert crj.parse_label({"answers": {"C01": "maybe", "C02": "no"}}, ids) is None
    assert crj.parse_label(crj.extract_json("no json at all"), ids) is None


def test_malformed_reply_is_reasked_once(rnd):
    j, chat = judge(rnd, ["I think yes.", '{"answers": {"C01": "no"}}'])
    res = j.ask("label", "item", "prompt", lambda o: crj.parse_label(o, ["C01"]), pass_no=1)
    assert res["status"] == "ok" and res["answer"] == {"C01": 0} and len(chat.bodies) == 2
    assert chat.bodies[1]["messages"][0]["content"].endswith(crj.REASK)
    j, chat = judge(rnd, ["bad", "still bad"])
    res = j.ask("label", "item2", "prompt2", lambda o: crj.parse_label(o, ["C01"]))
    assert res["status"] == "parse_error" and res["answer"] is None and len(chat.bodies) == 2


# --------------------------------------------------------------------------
# request, budget, ledger, cache
# --------------------------------------------------------------------------

def test_request_shape():
    body = crj.request_body("hello")
    assert body == {"model": "claude-sonnet-5-5", "max_tokens": crj.MAX_TOKENS,
                    "thinking": {"type": "adaptive"}, "output_config": {"effort": "medium"},
                    "messages": [{"role": "user", "content": "hello"}]}


def test_real_cost_logged_and_cache_hit(rnd):
    j, chat = judge(rnd, propose_reply)
    items, _ = crj.plan_propose(rnd["cfg"], rnd["cells"])
    out = crj.run_propose(j, items)
    assert len(chat.bodies) == 12 and all(o["status"] == "ok" for o in out)
    assert out[0]["differences"][0]["shown_by_model"] == "claude-opus-4-6"
    assert out[1]["differences"][0]["shown_by_model"] == "claude-opus-5-5"
    entries = rr.Ledger(rnd["cfg"].ledger_path).read()
    spends = [e for e in entries if e.get("kind") == "spend"]
    assert len(spends) == 12 and all(e["source"] == "judge" for e in spends)
    one = claude_cost(USAGE, "claude-sonnet-5-5")
    assert one == pytest.approx((1000 * 2 + 500 * 10) / 1e6)
    assert rr.judge_spent(entries) == pytest.approx(12 * one)
    # a rerun: every reply comes from the cache, no call, no new ledger line
    j2, chat2 = judge(rnd, propose_reply)
    out2 = crj.run_propose(j2, items)
    assert chat2.bodies == [] and j2.calls == 0 and out2 == out
    assert rr.judge_spent(rr.Ledger(rnd["cfg"].ledger_path).read()) == pytest.approx(12 * one)
    assert len(list((rnd["out"] / "cache" / "propose").iterdir())) == 12
    saved = json.loads((rnd["out"] / "proposals.json").read_text())
    assert len(saved["items"]) == 12


def test_budget_guard_refuses_before_the_call(rnd):
    prompt = "x" * 3000
    worst = crj.worst_case_usd(prompt)
    assert worst == pytest.approx((1000 * 2 + crj.MAX_TOKENS * 10) / 1e6)
    rr.add_spend(rnd["cfg"], 10.0 - worst + 0.001, "judge", "earlier")
    j, chat = judge(rnd, ["{}"])
    with pytest.raises(crj.BudgetRefused):
        j.raw("label", "item", prompt)
    assert chat.bodies == []
    assert len([e for e in rr.Ledger(rnd["cfg"].ledger_path).read()
                if e.get("kind") == "spend"]) == 1
    # just inside the reserve: allowed, and the real cost is logged
    rr.add_spend(rnd["cfg"], -0.002, "judge", "correction")
    j.raw("label", "item", prompt)
    assert len(chat.bodies) == 1
    last = rr.Ledger(rnd["cfg"].ledger_path).read()[-1]
    assert last["source"] == "judge" and last["cost_usd"] == pytest.approx(0.007)
    assert last["note"].startswith("exp-08 part B label item")


def test_budget_refusal_exits_nonzero(rnd, capsys):
    round_json(rnd["rj"].parent, reserve=0.01)
    rc = crj.main(["propose", "--round-json", str(rnd["rj"]), "--runs-root", str(rnd["runs"]),
                   "--out-dir", str(rnd["out"])], chat=FakeChat(propose_reply))
    assert rc == crj.EXIT_BUDGET == 3
    assert "would exceed the judge reserve" in capsys.readouterr().err


# --------------------------------------------------------------------------
# commit check, full pipeline, part_b
# --------------------------------------------------------------------------

def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd,
                   check=True, capture_output=True)


def test_commit_check(tmp_path):
    repo = tmp_path / "repo"
    (repo / "judge").mkdir(parents=True)
    p = repo / "judge" / "candidates.json"
    assert "does not exist" in crj.commit_check(p)
    p.write_text("{}")
    git(repo, "init", "-q")
    assert "not committed" in crj.commit_check(p)
    git(repo, "add", "judge/candidates.json")
    assert "not committed" in crj.commit_check(p)
    git(repo, "commit", "-q", "-m", "freeze")
    assert crj.commit_check(p) is None
    p.write_text('{"changed": 1}')
    assert "has changes" in crj.commit_check(p)


def test_pipeline_label_refused_until_committed_then_part_b(rnd, capsys):
    repo = rnd["out"].parent
    git(repo, "init", "-q")
    args = ["--round-json", str(rnd["rj"]), "--runs-root", str(rnd["runs"]),
            "--out-dir", str(rnd["out"])]
    assert crj.main(["propose", *args], chat=FakeChat(propose_reply)) == 0
    chat = FakeChat([FREEZE_REPLY])
    assert crj.main(["freeze", *args], chat=chat) == 0
    assert "P024" in chat.bodies[0]["messages"][0]["content"]        # 12 calls x 2 differences
    assert not any(m in chat.bodies[0]["messages"][0]["content"] for m in OPUS)
    cands = json.loads((rnd["out"] / "candidates.json").read_text())["candidates"]
    assert [c["id"] for c in cands] == ["C01", "C02"]
    # label refuses before the commit and makes no call
    chat = FakeChat(label_reply)
    assert crj.main(["label", *args], chat=chat) == crj.EXIT_COMMIT
    assert chat.bodies == [] and "not committed" in capsys.readouterr().err
    git(repo, "add", "judge/candidates.json")
    git(repo, "commit", "-q", "-m", "freeze candidates")
    assert crj.main(["label", *args], chat=chat) == 0
    assert len(chat.bodies) == 60
    labels = json.loads((rnd["out"] / "labels.json").read_text())
    assert len(labels) == 30 * 2 * 2
    assert {k for k in labels[0]} >= {"run_id", "level", "task_id", "candidate", "pass", "value"}
    res = cr.part_b(labels, OPUS, TASKS[3:], draws=200)
    assert set(res) == {"C01", "C02"}
    assert res["C01"]["count_table"] == {m: "12/12" for m in OPUS}
    assert res["C01"]["n_runs"] == 30 and res["C02"]["count_table"] == {m: "0/12" for m in OPUS}
    # status reports calls and dollars; a rerun of label makes no call
    chat2 = FakeChat(label_reply)
    assert crj.main(["label", *args], chat=chat2) == 0 and chat2.bodies == []
    capsys.readouterr()
    assert crj.main(["status", *args]) == 0
    st = capsys.readouterr().out
    assert "judge calls made: 73" in st and "committed and unchanged" in st
    assert f"${73 * claude_cost(USAGE, crj.MODEL):.4f}" in st


def test_module_imports_without_credentials():
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("ANTHROPIC") and k != "OPENBENCH_API_KEY"}
    code = ("import sys; sys.path.insert(0, 'research/analysis'); import claude_round_judge as m; "
            "print(m.MODEL)")
    root = os.path.join(os.path.dirname(__file__), "..")
    r = subprocess.run([sys.executable, "-c", code], cwd=root, env=env, capture_output=True,
                       text=True)
    assert r.returncode == 0 and "claude-sonnet-5-5" in r.stdout


def test_dry_run_makes_no_call(rnd, capsys):
    args = ["--round-json", str(rnd["rj"]), "--runs-root", str(rnd["runs"]),
            "--out-dir", str(rnd["out"]), "--dry-run"]
    chat = FakeChat([])
    assert crj.main(["propose", *args], chat=chat) == 0
    assert crj.main(["label", *args], chat=chat) == 0
    out = capsys.readouterr().out
    assert chat.bodies == [] and "propose: 12 planned calls, 0 cached" in out
    assert "label: 60 planned calls" in out
