"""Unit tests for research/analysis/command_audit.py (exp-07).

All inputs are synthetic: hand-made commands, transcripts and patches. No
test reads the run corpus.
"""

import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "research", "analysis"))
import command_audit as ca  # noqa: E402


def seg_texts(cmd):
    segs, fails = ca.split_segments(cmd)
    return [s["text"] for s in segs], fails


def coded(cmd, output="", ctx=None):
    return ca.code_command(cmd, output, ctx or ca.Ctx())


def classes(cmd, output=""):
    return [s["cls"] for s in coded(cmd, output)]


def writes(cmd, output="", ctx=None):
    return [w for s in coded(cmd, output, ctx) for w in s["writes"]]


# --------------------------------------------------------------------------
# segmentation
# --------------------------------------------------------------------------

def test_split_compound():
    texts, fails = seg_texts("cd /repo && grep -n x f.py | head -5; echo hi || true")
    assert texts == ["cd /repo", "grep -n x f.py", "head -5", "echo hi", "true"]
    assert fails == 0


def test_split_respects_quotes():
    texts, _ = seg_texts("""grep -n "a && b; c" f.py || echo 'x | y'""")
    assert texts == ['grep -n "a && b; c" f.py', "echo 'x | y'"]


def test_split_heredoc_body_attached():
    cmd = "cat > f.py << 'EOF' && python f.py\na && b; c | d\nEOF\nls"
    segs, fails = ca.split_segments(cmd)
    assert [s["text"] for s in segs] == ["cat > f.py << 'EOF'", "python f.py", "ls"]
    assert segs[0]["body"] == "a && b; c | d\n"
    assert segs[1]["body"] is None
    assert fails == 0


def test_split_heredoc_dash_strips_tabs():
    segs, fails = ca.split_segments("cat <<-END > x.txt\n\tbody\n\tEND\necho ok")
    assert [s["text"] for s in segs][-1] == "echo ok"
    assert segs[0]["body"] == "\tbody\n"
    assert fails == 0


def test_split_unterminated_heredoc_is_failure():
    segs, fails = ca.split_segments("cat > f.py << EOF\nprint(1)\n EOF")
    assert fails == 1
    assert len(segs) == 1 and "print(1)" in segs[0]["body"]


def test_split_command_substitution_and_subshell():
    texts, _ = seg_texts("for f in $(grep -rl x sympy; ls); do wc -l $f; done")
    assert texts[0].startswith("for f in $(grep -rl x sympy; ls)")
    texts, _ = seg_texts("(cd sympy && ls) && echo done")
    assert texts == ["cd sympy", "ls", "echo done"]


def test_python_c_multiline_stays_one_segment():
    texts, _ = seg_texts('python -c "\nimport x\nprint(1); print(2)\n" 2>&1')
    assert len(texts) == 1


def test_tokenize_redirections_and_quotes():
    toks, ok = ca.tokenize("""grep -n '>' f.py 2>&1 >out.txt""")
    assert ok
    assert toks == [("grep", "word"), ("-n", "word"), (">", "qword"), ("f.py", "word"),
                    ("2>&", "op"), ("1", "word"), (">", "op"), ("out.txt", "word")]


# --------------------------------------------------------------------------
# classes
# --------------------------------------------------------------------------

@pytest.mark.parametrize("cmd,expected", [
    ("echo OPENBENCH_DONE", ["done"]),
    ("sed -i 's/a/b/' sympy/core/x.py", ["edit"]),
    ("python -m pytest sympy/core/tests/test_x.py -q", ["test"]),
    ("pytest -q testing/test_capture.py", ["test"]),
    ("./bin/test sympy/polys", ["test"]),
    ("python bin/test sympy/polys", ["test"]),
    ("""python -c "from sympy.testing.runtests import test; test('printing')" """, ["test"]),
    ("""python -c "import sympy; sympy.test('core')" """, ["test"]),
    ("PYTHONPATH=/tmp/shim timeout 600 python -m pytest testing/ -q", ["test"]),
    ("python -m unittest discover", ["test"]),
    ("tox -e py39", ["test"]),
    ("python -c 'import sympy; print(sympy.__version__)'", ["run"]),
    ("python3 - << 'EOF'\nprint(open('sympy/core/x.py').read()[:10])\nEOF", ["run"]),
    ("python /tmp/check.py", ["run"]),
    ("cat sympy/core/symbol.py", ["read"]),
    ("sed -n '10,20p' sympy/core/symbol.py", ["read"]),
    ("head -n 40 f.py", ["read"]),
    ("wc -l f.py", ["read"]),
    ("nl -ba f.py", ["read"]),
    ("grep -rn foo sympy", ["search"]),
    ("find /repo -name '*.py'", ["search"]),
    ("ls -la", ["search"]),
    ("git grep -n foo", ["search"]),
    ("git diff", ["vcs"]),
    ("git stash pop", ["vcs"]),
    ("git checkout -- sympy/core/x.py", ["vcs"]),
    ("pip install -e .", ["setup"]),
    ("python -m pip list", ["setup"]),
    ("cd /repo", ["setup"]),
    ("export X=1", ["setup"]),
    ("mkdir -p /tmp/x", ["setup"]),
    ("chmod +x a.sh", ["setup"]),
    ("python --version", ["setup"]),
    ("which python3", ["setup"]),
    ("echo hello", ["other"]),
    ("true", ["other"]),
])
def test_segment_classes(cmd, expected):
    assert classes(cmd) == expected


def test_pipeline_filters_are_dropped():
    assert classes("python -m pytest x -q 2>&1 | tail -20") == ["test"]
    assert classes("grep -rn foo sympy | grep -v tests | head") == ["search"]
    assert classes("find . -name '*.py' | xargs grep -l foo") == ["search", "search"]
    # a filter with a file operand after a pipe is still a segment
    assert classes("echo x | cat - f.py") == ["other", "read"]


def test_command_not_found_is_other():
    cmd = "apply_patch <<'PATCH'\n*** Begin Patch\n*** Update File: a.py\n*** End Patch\nPATCH"
    out = "bash: line 1: apply_patch: command not found\n"
    segs = coded(cmd, out)
    assert [s["cls"] for s in segs] == ["other"] and segs[0]["writes"] == []


def test_bash_c_is_expanded():
    assert classes("bash -c \"cd /repo && sed -i 's/a/b/' x.py\"") == ["setup", "edit"]


def test_primary_class_order():
    recs = [{"command": "cd /repo && cat x.py && python -m pytest t.py && sed -i 's/a/b/' x.py",
             "output": "", "exit_code": 0, "turn": 1}]
    records, _ = ca.code_records(recs, {"x.py": "modified"}, set())
    assert records[0]["primary"] == "edit"
    assert records[0]["classes"] == {"setup", "read", "test", "edit"}


# --------------------------------------------------------------------------
# write-path extraction
# --------------------------------------------------------------------------

def test_redirect_writes():
    assert writes("echo x > sympy/a.py") == [("sympy/a.py", "full")]
    assert writes("echo x >> /repo/sympy/a.py") == [("sympy/a.py", "append")]
    assert writes("cat > new_test.py << 'EOF'\nx\nEOF") == [("new_test.py", "full")]
    assert writes("python t.py > /dev/null 2>&1") == []
    assert writes("cat > /tmp/fix.py << 'EOF'\nx\nEOF") == []
    assert writes("cd /tmp && echo x > a.py") == []
    assert writes("cd sympy && echo x > a.py") == [("sympy/a.py", "full")]


def test_tee_sed_perl_writes():
    assert writes("echo x | tee sympy/a.py") == [("sympy/a.py", "full")]
    assert writes("echo x | tee -a sympy/a.py") == [("sympy/a.py", "append")]
    assert writes("sed -i 's/a/b/' sympy/a.py sympy/b.py") == [
        ("sympy/a.py", "modify"), ("sympy/b.py", "modify")]
    assert writes("sed -i '' -e 's/a/b/' sympy/a.py") == [("sympy/a.py", "modify")]
    assert writes("perl -pi -e 's/a/b/' sympy/a.py") == [("sympy/a.py", "modify")]


def test_cp_mv_rm_writes():
    assert writes("cp sympy/a.py sympy/a.py.orig") == [("sympy/a.py.orig", "full")]
    assert writes("mv tmp.txt sympy/a.py") == [("sympy/a.py", "full"), ("tmp.txt", "delete")]
    assert writes("cp sympy/a.py /tmp/") == []
    assert writes("rm -f scratch.py") == [("scratch.py", "delete")]
    assert writes("cp a.py sympy/") == [("sympy/a.py", "full")]


def test_patch_and_git_apply_writes():
    diff = ("diff --git a/sympy/a.py b/sympy/a.py\n--- a/sympy/a.py\n+++ b/sympy/a.py\n"
            "@@ -1 +1 @@\n-x\n+y\n"
            "diff --git a/sympy/n.py b/sympy/n.py\nnew file mode 100644\n--- /dev/null\n"
            "+++ b/sympy/n.py\n@@ -0,0 +1 @@\n+z\n")
    assert writes(f"git apply << 'EOF'\n{diff}EOF") == [("sympy/a.py", "modify"),
                                                         ("sympy/n.py", "full")]
    ctx = ca.Ctx()
    assert writes(f"cat > /tmp/fix.patch << 'EOF'\n{diff}EOF", ctx=ctx) == []
    assert writes("patch -p1 < /tmp/fix.patch", ctx=ctx) == [("sympy/a.py", "modify"),
                                                            ("sympy/n.py", "full")]
    # GNU patch output names the file when the diff text is unknown
    assert writes("patch -p1 < /elsewhere.diff", "patching file sympy/b.py\n") == [
        ("sympy/b.py", "modify")]
    assert classes("git apply --check x.diff") == ["vcs"]
    assert classes("patch --dry-run -p1 < x.diff") == ["other"]


def test_apply_patch_writes_when_installed():
    cmd = ("apply_patch <<'PATCH'\n*** Begin Patch\n*** Update File: sympy/a.py\n@@\n-x\n+y\n"
           "*** Add File: sympy/tests/test_new.py\n+def test(): pass\n*** End Patch\nPATCH")
    assert writes(cmd) == [("sympy/a.py", "modify"), ("sympy/tests/test_new.py", "full")]


def test_python_heredoc_writes():
    cmd = ("python - <<'PY'\nimport pathlib\np = pathlib.Path('sympy/a.py')\n"
           "t = p.read_text()\np.write_text(t.replace('a', 'b'))\nPY")
    assert writes(cmd) == [("sympy/a.py", "modify")]
    cmd = ("python3 << 'EOF'\npath = 'sympy/b.py'\nwith open(path, 'w') as f:\n"
           "    f.write('x')\nEOF")
    assert writes(cmd) == [("sympy/b.py", "full")]
    cmd = ("python -c \"\nwith open('sympy/c.py', 'r') as f:\n    s = f.read()\n"
           "with open('sympy/c.py', 'w') as f:\n    f.writelines([s])\n\"")
    assert writes(cmd) == [("sympy/c.py", "modify")]
    # writes only outside /repo or to stdout -> run, not edit
    cmd = "python - <<'EOF'\nf = open('/tmp/x.txt', 'w')\nf.write('a')\nprint('ok')\nEOF"
    assert writes(cmd) == [] and classes(cmd) == ["run"]
    cmd = "python - <<'EOF'\nimport os\nwith open(os.devnull, 'wb') as fh:\n    pass\nEOF"
    assert writes(cmd) == [] and classes(cmd) == ["run"]


def test_python_known_script_is_analysed():
    ctx = ca.Ctx()
    body = "with open('/repo/sympy/a.py', 'w') as f:\n    f.write('x')\n"
    assert writes(f"cat > /tmp/fix.py << 'EOF'\n{body}EOF", ctx=ctx) == []
    segs = coded("python /tmp/fix.py", ctx=ctx)
    assert segs[0]["cls"] == "edit" and segs[0]["writes"] == [("sympy/a.py", "full")]
    ctx = ca.Ctx()
    coded("cat > /tmp/run.py << 'EOF'\nimport pytest\npytest.main(['-q'])\nEOF", ctx=ctx)
    assert [s["cls"] for s in coded("python /tmp/run.py", ctx=ctx)] == ["test"]


def test_paths_normalized_and_unresolvable():
    assert ca.norm_path("./sympy/../sympy/a.py", "/repo") == ("repo", "sympy/a.py")
    assert ca.norm_path("/repo/x.py", "/tmp") == ("repo", "x.py")
    assert ca.norm_path("x.py", "/tmp") == ("outside", "/tmp/x.py")
    assert ca.norm_path("$f", "/repo")[0] == "unresolvable"
    assert ca.norm_path("sympy/__pycache__/a.pyc", "/repo")[0] == "ignore"
    ctx = ca.Ctx()
    assert writes("echo x > $OUT", ctx=ctx) == [] and ctx.unresolvable_writes == 1


def test_is_test_like():
    assert ca.is_test_like("sympy/core/tests/test_x.py")
    assert ca.is_test_like("a_test.py")
    assert ca.is_test_like("conftest.py")
    assert ca.is_test_like("testing/helper.py")
    assert ca.is_test_like("sympy/core/tests/helpers.py")
    assert not ca.is_test_like("sympy/testing/runtests.py")
    assert not ca.is_test_like("src/_pytest/testing_utils.py")
    assert not ca.is_test_like("src/_pytest/capture.py")
    assert not ca.is_test_like("sympy/core/x.py")


# --------------------------------------------------------------------------
# existing / new resolution
# --------------------------------------------------------------------------

def _resolve(cmds, ws=None, ref=None, outputs=None):
    recs = [{"command": c, "output": (outputs or {}).get(i, ""), "exit_code": 0, "turn": i}
            for i, c in enumerate(cmds)]
    _, info = ca.code_records(recs, ws or {}, ref or set())
    return info


def test_existence_rules():
    # a. workspace patch decides
    info = _resolve(["echo x > a.py", "echo y > b.py"], ws={"a.py": "modified", "b.py": "new"})
    assert info["existence"] == {"a.py": "existing", "b.py": "new"}
    # b. reference patches
    info = _resolve(["sed -i 's/a/b/' sympy/tests/test_x.py"], ref={"sympy/tests/test_x.py"})
    assert info["subkind"]["sympy/tests/test_x.py"] == "existing_test"
    # c. earlier read (and not a failed read)
    info = _resolve(["cat sympy/a.py", "sed -i 's/a/b/' sympy/a.py"])
    assert info["subkind"]["sympy/a.py"] == "source"
    info = _resolve(["cat sympy/a.py", "sed -i 's/a/b/' sympy/a.py"],
                    outputs={0: "cat: sympy/a.py: No such file or directory"})
    assert info["existence"]["sympy/a.py"] == "unknown"
    assert info["n_unknown_existence"] == 1
    # d. first operation a full write
    info = _resolve(["cat > sympy/tests/test_new.py << 'EOF'\nx\nEOF", "cat sympy/tests/test_new.py"])
    assert info["subkind"]["sympy/tests/test_new.py"] == "new_test"
    info = _resolve(["cp sympy/a.py sympy/a.py.bak"])
    assert info["subkind"]["sympy/a.py.bak"] == "scratch"
    # e. unknown
    info = _resolve(["echo x >> notes.txt"])
    assert info["subkind"]["notes.txt"] == "unknown"


def test_patch_status_text():
    text = ("diff --git a/x.py b/x.py\nindex 1..2 100644\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n"
            "diff --git a/n.py b/n.py\nnew file mode 100644\n--- /dev/null\n+++ b/n.py\n"
            "diff --git a/d.py b/d.py\ndeleted file mode 100644\n--- a/d.py\n+++ /dev/null\n")
    assert ca.patch_status_text(text) == {"x.py": "modified", "n.py": "new", "d.py": "deleted"}


def test_patch_line_count(tmp_path):
    p = tmp_path / "w.patch"
    p.write_text("diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1,3 +1,3 @@\n a\n-b\n+c\n d\n"
                 "@@ -10,2 +10,3 @@\n e\n--- f\n+g\n+h\n")
    # "--- f" inside a hunk is a removed line, not a header
    assert ca.patch_line_count(str(p)) == 5


# --------------------------------------------------------------------------
# run-level metrics on hand-built transcripts
# --------------------------------------------------------------------------

def _metrics(cmds, ws_status, gold_files, exit_reason="completed", ws_lines=0, ref=None):
    recs = []
    for i, c in enumerate(cmds):
        if isinstance(c, tuple):
            cmd, out, rc = c
        else:
            cmd, out, rc = c, "x\n", 0
        recs.append({"command": cmd, "output": out, "exit_code": rc, "turn": i + 1})
    records, info = ca.code_records(recs, ws_status, ref or set())
    return ca.metrics_from_records(records, info, exit_reason, ws_status, gold_files, ws_lines)


MAIN_RUN = [
    ("grep -rn foo sympy", "sympy/a.py:1:foo\n", 0),          # 0 search hit
    "cat sympy/a.py",                                           # 1 read
    "cat sympy/a.py",                                           # 2 re-read
    "sed -i 's/x/y/' sympy/a.py",                               # 3 edit:source
    ("python -m pytest sympy/tests/test_a.py", "1 passed", 0),  # 4 test
    ("python -m pytest sympy/tests/test_a.py", "1 passed", 0),  # 5 no-op retest
    "cat sympy/a.py",                                           # 6 read after edit: not a re-read
    "cat > sympy/tests/test_new.py << 'EOF'\ndef test(): pass\nEOF",  # 7 edit:new_test
    "cat > repro.py << 'EOF'\nprint(1)\nEOF",                   # 8 edit:scratch
    ("python repro.py", "1\n", 0),                              # 9 run of the scratch script
    "echo 'z = 1' >> sympy/a.py",                               # 10 edit:source after last test
    ("grep -rn nothing sympy", "", 1),                          # 11 search miss
    ("echo OPENBENCH_DONE", "OPENBENCH_DONE\n", 0),             # 12 done
]


def test_metrics_main_run():
    ws = {"sympy/a.py": "modified", "sympy/tests/test_new.py": "new"}
    m = _metrics(MAIN_RUN, ws, ["sympy/a.py"], ws_lines=7)
    assert m["n_cmds"] == 12
    assert m["first_edit_frac"] == pytest.approx(3 / 12)
    assert m["early_edit_share"] == pytest.approx(3 / 10)
    assert m["test_share"] == pytest.approx(2 / 12)
    assert m["exec_share"] == pytest.approx(3 / 12)
    assert m["wrote_new_test"] == 1
    assert m["wrote_scratch_script"] == 1
    assert m["repeat_cmd_share"] == pytest.approx(3 / 12)
    assert m["noop_retest_share"] == pytest.approx(1 / 2)
    assert m["reread_share"] == pytest.approx(1 / 3)
    assert m["search_miss_share"] == pytest.approx(1 / 2)
    assert m["extra_files"] == 1
    assert m["patch_lines"] == 7
    # edits after its last passing test -> unsupported
    assert m["no_edit"] == 0
    assert m["unsupported_done"] == 1 and m["U_lenient"] == 1
    assert m["gold_file_hit"] == 1
    assert m["leftover_new_files"] == 1
    assert m["edited_existing_test"] == 0
    assert m["error_share"] == pytest.approx(1 / 12)
    assert m["primary_seq"][-1] == "done" and len(m["primary_seq"]) == 13


def test_metrics_supported_and_lenient():
    base = ["cat sympy/a.py", "sed -i 's/x/y/' sympy/a.py"]
    m = _metrics(base + [("pytest sympy/tests/test_a.py", "ok", 0), "echo OPENBENCH_DONE"],
                 {"sympy/a.py": "modified"}, ["sympy/a.py"])
    assert m["unsupported_done"] == 0 and m["U_lenient"] == 0
    m = _metrics(base + [("pytest sympy/tests/test_a.py", "failed", 1),
                         ("python -c 'import sympy'", "", 0), "echo OPENBENCH_DONE"],
                 {"sympy/a.py": "modified"}, ["sympy/a.py"])
    assert m["unsupported_done"] == 1 and m["U_lenient"] == 0
    # same record: edit then test -> the test segment is after the edit
    m = _metrics(base[:1] + [("sed -i 's/a/b/' sympy/a.py && pytest -q", "ok", 0)],
                 {"sympy/a.py": "modified"}, ["sympy/a.py"])
    assert m["unsupported_done"] == 0
    # not completed -> U undefined
    m = _metrics(base, {"sympy/a.py": "modified"}, ["sympy/a.py"], exit_reason="turn_cap")
    assert m["unsupported_done"] is None and m["U_lenient"] is None


def test_metrics_no_source_edit():
    m = _metrics(["cat sympy/a.py", "cat > /tmp/x.py << 'EOF'\nprint(1)\nEOF",
                  ("python /tmp/x.py", "1", 0), "echo OPENBENCH_DONE"], {}, ["sympy/a.py"])
    assert m["no_edit"] == 1
    assert m["unsupported_done"] is None
    assert m["first_edit_frac"] == 1.0
    assert m["gold_file_hit"] == 0
    assert m["wrote_scratch_script"] == 1  # a /tmp script written then executed counts
    assert m["noop_retest_share"] == 0.0 and m["search_miss_share"] == 0.0


def test_metrics_edited_existing_test_and_noop_rules():
    cmds = [
        "cat sympy/tests/test_a.py",
        "sed -i 's/a/b/' sympy/tests/test_a.py",
        ("pytest sympy/tests/test_a.py", "ok", 0),
        "sed -i 's/c/d/' sympy/a.py",
        ("pytest sympy/tests/test_a.py", "ok", 0),   # edit between -> not a no-op
        ("pytest sympy/tests/test_a.py", "ok", 0),   # no-op
    ]
    m = _metrics(cmds, {"sympy/a.py": "modified", "sympy/tests/test_a.py": "modified"}, ["sympy/a.py"])
    assert m["edited_existing_test"] == 1
    assert m["noop_retest_share"] == pytest.approx(1 / 3)
    assert m["first_edit_frac"] == pytest.approx(3 / 6)
    assert m["unsupported_done"] == 0


def test_run_metrics_end_to_end(tmp_path, monkeypatch):
    tasks = tmp_path / "tasks"
    (tasks / "t1").mkdir(parents=True)
    (tasks / "t1" / "gold.patch").write_text(
        "diff --git a/pkg/a.py b/pkg/a.py\n--- a/pkg/a.py\n+++ b/pkg/a.py\n@@ -1 +1 @@\n-x\n+y\n")
    (tasks / "t1" / "test.patch").write_text("")
    monkeypatch.setattr(ca.manifest, "TASKS", tasks)
    run = tmp_path / "run"
    run.mkdir()
    lines = [
        {"type": "meta", "model": "m", "task_id": "t1"},
        {"type": "api_response", "turn": 1, "content": "", "reasoning_content": "x"},
        {"type": "exec", "turn": 1, "command": "sed -i 's/x/y/' pkg/a.py", "exit_code": 0, "output": ""},
        {"type": "exec", "turn": 2, "command": "pytest -q", "exit_code": 0, "output": "1 passed"},
        {"type": "exec", "turn": 3, "command": "echo OPENBENCH_DONE", "exit_code": 0,
         "output": "OPENBENCH_DONE"},
        {"type": "final", "exit_reason": "completed", "turns": 3},
    ]
    (run / "raw_transcript.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    (run / "workspace.patch").write_text(
        "diff --git a/pkg/a.py b/pkg/a.py\n--- a/pkg/a.py\n+++ b/pkg/a.py\n@@ -1 +1 @@\n-x\n+y\n")
    m = ca.run_metrics(str(run), "t1")
    assert m["exit_reason"] == "completed"
    assert m["n_cmds"] == 2 and m["unsupported_done"] == 0
    assert m["patch_lines"] == 2 and m["extra_files"] == 0
    assert m["gold_file_hit"] == 1 and m["edit_jaccard_gold"] == 1.0


# --------------------------------------------------------------------------
# statistics
# --------------------------------------------------------------------------

def test_anova_known_answer():
    y = {("a", "x"): [1, 3], ("a", "y"): [5, 7], ("b", "x"): [2, 4], ("b", "y"): [10, 12]}
    r = ca.anova_balanced(y, ["a", "b"], ["x", "y"])
    ss = r["ss"]
    assert ss["model"] == pytest.approx(18)
    assert ss["task"] == pytest.approx(72)
    assert ss["model:task"] == pytest.approx(8)
    assert ss["repeat"] == pytest.approx(8)
    assert ss["total"] == pytest.approx(106)
    assert r["df"] == {"model": 1, "task": 1, "model:task": 1, "repeat": 4}


def test_variance_split_shares_and_p():
    rows = []
    for mi, m in enumerate(["a", "b", "c"]):
        for t in ["x", "y"]:
            for rep in range(3):
                rows.append({"model": m, "task_id": t, "test_share": mi + 0.01 * rep})
    vs = ca.variance_split(rows, "test_share", ["a", "b", "c"], ["x", "y"], draws=200, seed=1)
    assert vs["shares"]["model"] > 0.99
    assert 0 < vs["p_main"] <= 1 and 0 < vs["p_cell"] <= 1
    assert vs["p_cell"] < 0.05
    const = [dict(r, test_share=0.5) for r in rows]
    vc = ca.variance_split(const, "test_share", ["a", "b", "c"], ["x", "y"], draws=10)
    assert vc["constant"] and vc["p_main"] is None


def test_kendall_w():
    assert ca.kendall_w([[1, 2, 3, 4], [1, 2, 3, 4], [1, 2, 3, 4]]) == pytest.approx(1.0)
    assert ca.kendall_w([[1, 2, 3], [1, 3, 2], [2, 1, 3]]) == pytest.approx(4 / 9)
    # scores, not ranks, are accepted; ties get average ranks
    assert ca.kendall_w([[0.1, 0.5, 0.9], [10, 20, 30]]) == pytest.approx(1.0)
    assert ca.kendall_w([[1, 1, 1], [1, 1, 1]]) is None


def test_holm():
    adj = ca.holm([0.01, 0.04, 0.03, 0.005])
    assert adj == pytest.approx([0.03, 0.06, 0.06, 0.02])
    assert ca.holm([0.5, None, 0.01]) == [pytest.approx(0.5), None, pytest.approx(0.02)]


def test_clopper_pearson():
    lo, hi = ca.clopper_pearson(3, 10)
    assert lo == pytest.approx(0.066739, abs=1e-5)
    assert hi == pytest.approx(0.652453, abs=1e-5)
    lo, hi = ca.clopper_pearson(0, 20)
    assert lo == 0.0 and hi == pytest.approx(1 - 0.025 ** (1 / 20), abs=1e-7)
    lo, hi = ca.clopper_pearson(5, 5)
    assert hi == 1.0 and lo == pytest.approx(0.025 ** (1 / 5), abs=1e-7)


def test_cohen_kappa():
    a = ["y"] * 20 + ["y"] * 5 + ["n"] * 10 + ["n"] * 15
    b = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
    assert ca.cohen_kappa(a, b) == pytest.approx(0.4)
    assert ca.cohen_kappa(["a", "b"], ["a", "b"]) == pytest.approx(1.0)


def test_decision_labels():
    base = {"constant": False, "shares": {"model": 0.5, "task": 0.1, "model:task": 0.1, "repeat": 0.3}}
    assert ca.decide({**base, "p_main_holm": 0.01, "p_cell_holm": 0.01, "p_cell": 0.001,
                      "kendall_w": 0.7}) == "model habit"
    assert ca.decide({**base, "p_main_holm": 0.01, "p_cell_holm": 0.01, "p_cell": 0.001,
                      "kendall_w": 0.4}) == "task-dependent model habit"
    assert ca.decide({**base, "p_main_holm": 0.5, "p_cell_holm": 0.5, "p_cell": 0.2,
                      "kendall_w": 0.4}) == "repeat noise"
    assert ca.decide({**base, "p_main_holm": 0.5, "p_cell_holm": 0.2, "p_cell": 0.02,
                      "kendall_w": 0.4}) == "indeterminate"


def test_nearest_centroid_identifies_separated_models():
    X, y, tasks = [], [], []
    for mi, m in enumerate(["a", "b", "c"]):
        for t in ["x", "y", "z"]:
            for rep in range(3):
                X.append([mi * 10 + 0.1 * rep, -mi * 5.0])
                y.append(m)
                tasks.append(t)
    assert ca._nc_accuracy(X, y, tasks, ["a", "b", "c"], "loro") == 1.0
    assert ca._nc_accuracy(X, y, tasks, ["a", "b", "c"], "loto") == 1.0


def test_transforms():
    assert ca.transform("n_cmds", 1) == 0.0
    assert ca.transform("n_cmds", math.e) == pytest.approx(1.0)
    assert ca.transform("patch_lines", 0) == 0.0
    assert ca.transform("test_share", 0.25) == 0.25


def _synthetic_rows(seed=0):
    import random
    rng = random.Random(seed)
    rows = []
    for mi, m in enumerate(ca.cv.ORDER):
        for t in ca.cv.VERIFIED:
            for rep in (1, 2, 3):
                r = {"run_id": f"{t}--{m}--{rep}", "model": m, "task_id": t, "repeat": rep,
                     "resolved": rng.random() < 0.5, "stale_image": t == ca.PYTEST_TASK and rep > 1,
                     "exit_reason": "completed" if rep < 3 else "turn_cap", "host": "h"}
                for _, k, _ in ca.METRICS:
                    r[k] = mi + rng.random()
                r.update(no_edit=0, unsupported_done=rng.randint(0, 1) if rep < 3 else None)
                r.update(U_unknown=0, U_sensitivity=r["unsupported_done"])
                r["U_lenient"] = r["unsupported_done"]
                for k in ca.DESCRIPTIVE:
                    r[k] = rng.randint(0, 1)
                rows.append(r)
    return rows


def test_analyse_smoke_on_synthetic_rows():
    an = ca.analyse(_synthetic_rows(), draws=200, a5_draws=20)
    a1 = an["A1_A2_decisions"]
    assert set(a1) == {mid for mid, _, _ in ca.METRICS}
    # metric values are model index + noise: the model dominates
    assert a1["M4"]["shares"]["model"] > a1["M4"]["shares"]["repeat"]
    assert a1["M4"]["kendall_w"] > 0.6
    assert an["A5_identification"]["loto"]["accuracy"] > 0.5
    assert set(an["predictions"]) == {"P1", "P2", "P3", "P4", "P5", "P6"}
    assert all(v["verdict"] in ("replicates", "does not replicate", "not testable")
               for v in an["predictions"].values())
    assert an["status"] == "unvalidated instrument"
    json.dumps(ca._jsonable(an))


def test_score_labels(tmp_path):
    import csv

    def w(name, header, rows):
        with open(tmp_path / name, "w", newline="") as f:
            cw = csv.writer(f)
            cw.writerow(header)
            cw.writerows(rows)

    w("commands_to_label.csv", ["sample_id", "run_id", "turn", "command", "exit_code",
                                "output_head", "human_label"],
      [["C001", "r", 1, "ls", 0, "", "search"], ["C002", "r", 2, "cat a", 0, "", "read"],
       ["C003", "r", 3, "x", 0, "", ""]])
    w("commands_rule_labels.csv", ["sample_id", "rule_primary", "rule_flags"],
      [["C001", "search", "search"], ["C002", "read", "read"], ["C003", "other", "other"]])
    w("completion_to_check.csv", ["sample_id", "run_id", "last_15_records", "human_unsupported_done"],
      [["R001", "r", "", "1"], ["R002", "r", "", "0"]])
    w("completion_rule_labels.csv", ["sample_id", "rule_unsupported_done", "rule_U_lenient",
                                     "rule_no_edit"], [["R001", "1", "1", "0"], ["R002", "1", "0", "0"]])
    res = ca.score_labels(tmp_path)
    assert res["V1"]["n"] == 2 and res["V1"]["kappa"] == pytest.approx(1.0)
    assert res["V2"]["n"] == 2 and res["V2"]["agreement"] == pytest.approx(0.5)
    assert (tmp_path / "validation.json").is_file()



# --------------------------------------------------------------------------
# amendments before freeze (round 2)
# --------------------------------------------------------------------------

def test_decision_model_habit_needs_unadjusted_p_cell():
    base = {"constant": False, "shares": {"model": 0.5, "task": 0.1, "model:task": 0.1, "repeat": 0.3}}
    r = {**base, "p_main_holm": 0.01, "p_cell_holm": 0.3, "p_cell": 0.2, "kendall_w": 0.9}
    assert ca.decide(r) == "repeat noise"


def test_scratch_class_outside_repo():
    assert classes("cat > /tmp/fix.py << 'EOF'\nx = 1\nEOF") == ["scratch"]
    assert classes("grep -n x f.py > /tmp/hits.txt") == ["scratch"]
    assert classes("python -m pytest -q > /tmp/log.txt") == ["test"]
    assert classes("python t.py > /dev/null") == ["run"]
    assert classes("echo hi > /dev/null") == ["other"]
    recs = [{"command": "cat > /tmp/a.py << 'EOF'\nx\nEOF\ncat sympy/a.py", "output": "",
             "exit_code": 0, "turn": 1}]
    records, _ = ca.code_records(recs, {}, set())
    assert records[0]["primary"] == "scratch"


def test_source_new_subkind():
    def sub(cmds, ws, root="sympy/"):
        recs = [{"command": c, "output": "", "exit_code": 0, "turn": i} for i, c in enumerate(cmds)]
        return ca.code_records(recs, ws, set(), root)[1]["subkind"]
    s = sub(["cat > sympy/core/helper.py << 'EOF'\nx\nEOF"], {"sympy/core/helper.py": "new"})
    assert s["sympy/core/helper.py"] == "source_new"
    # not in the final patch -> scratch
    s = sub(["cat > sympy/core/helper.py << 'EOF'\nx\nEOF", "rm sympy/core/helper.py"], {})
    assert s["sympy/core/helper.py"] == "scratch"
    # outside the package root -> scratch
    s = sub(["cat > fix.py << 'EOF'\nx\nEOF"], {"fix.py": "new"})
    assert s["fix.py"] == "scratch"
    s = sub(["echo x > src/imp.py"], {"src/imp.py": "new"}, root=ca.package_root("pytest-dev__pytest-5262"))
    assert s["src/imp.py"] == "source_new"
    assert ca.package_root("sympy__sympy-13757") == "sympy/"


def test_git_effects():
    def vcs(cmd):
        return [s.get("vcs") for s in coded(cmd)]
    assert vcs("git checkout -- sympy/a.py") == ["revert"]
    assert vcs("git restore sympy/a.py") == ["revert"]
    assert vcs("git restore --staged sympy/a.py") == [None]
    assert vcs("git reset --hard") == ["revert"]
    assert vcs("git stash drop") == ["revert"]
    assert vcs("git stash") == ["stash_push"]
    assert vcs("git stash -q") == ["stash_push"]
    assert vcs("git stash pop") == ["stash_end"]
    assert vcs("git stash apply") == ["stash_end"]
    assert vcs("git diff") == [None]
    assert vcs("git checkout master") == [None]


PYTEST_FAIL = "FAILED t.py::test_x - assert 1 == 2\n========= 1 failed, 3 passed in 0.52s =========\n"
PYTEST_PASS = "....\n4 passed in 0.31s\n"
SYMPY_PASS = ("============================= test process starts ==============================\n"
              "sympy/polys/tests/test_polytools.py[148] ...........................     [OK]\n"
              "================== tests finished: 148 passed, in 12.34 seconds ==================\n")
SYMPY_FAIL = ("___________________________________________________________________\n"
              "================== tests finished: 147 passed, 1 failed, in 12.1 seconds ===\n"
              "DO *NOT* COMMIT!\n")


@pytest.mark.parametrize("output,rc,last,piped,expected", [
    (PYTEST_FAIL, 0, False, True, "fail"),     # pytest ... | tail -20 with a failing summary
    (PYTEST_PASS, 1, False, True, "pass"),
    (SYMPY_PASS, 0, True, False, "pass"),
    (SYMPY_FAIL, 0, True, False, "fail"),
    ("ERROR collecting sympy/x/tests/test_a.py\n", 0, False, True, "fail"),
    ("2 errors in 0.1s\n", 0, True, False, "fail"),
    ("Traceback (most recent call last):\n  ImportError: no module\n", 0, False, False, "fail"),
    ("Ran 3 tests in 0.002s\n\nOK\n", 1, False, True, "pass"),
    ("Ran 3 tests in 0.002s\n\nFAILED (failures=1)\n", 0, True, False, "fail"),
    ("no summary here\n", 0, True, False, "pass"),     # unpiped last segment: exit code
    ("no summary here\n", 1, True, False, "fail"),
    ("no summary here\n", 0, False, False, "unknown"),  # pytest ...; git stash pop
    ("no summary here\n", 0, True, True, "unknown"),
    ("no tests ran in 0.01s\n", 5, False, True, "unknown"),
    ("    from pkg_resources import x\nModuleNotFoundError: No module named 'pkg_resources'\n",
     0, False, True, "fail"),
    ("ERROR: not found: /repo/t.py::test_x\n", 0, False, True, "fail"),
    ("pytest: error: unrecognized arguments: --timeout=60\n", 0, False, True, "fail"),
    ("t.py::test_a PASSED\nt.py::test_b FAILED\n", 0, False, True, "fail"),
    ("t.py::test_a PASSED\nt.py::test_b PASSED\n", 0, False, True, "unknown"),
])
def test_test_outcome(output, rc, last, piped, expected):
    assert ca.test_outcome(output, rc, last, piped) == expected


def test_outcome_positions_in_records():
    def outcome(cmd, out, rc=0):
        recs = [{"command": cmd, "output": out, "exit_code": rc, "turn": 1}]
        records, _ = ca.code_records(recs, {}, set())
        return [s["outcome"] for s in records[0]["segs"] if s["cls"] == "test"]
    assert outcome("python -m pytest t.py 2>&1 | tail -20", PYTEST_FAIL) == ["fail"]
    assert outcome("python -m pytest t.py; git stash pop", "Saved\n", 0) == ["unknown"]
    assert outcome("./bin/test sympy/polys/tests/test_polytools.py", SYMPY_PASS) == ["pass"]
    assert outcome("pytest -q t.py", "", 0) == ["pass"]


def _run(cmds, ws=None, exit_reason="completed", root="sympy/"):
    recs = []
    for i, c in enumerate(cmds):
        cmd, out, rc = c if isinstance(c, tuple) else (c, "", 0)
        recs.append({"command": cmd, "output": out, "exit_code": rc, "turn": i + 1})
    ws = ws if ws is not None else {"sympy/a.py": "modified"}
    records, info = ca.code_records(recs, ws, set(), root)
    return ca.metrics_from_records(records, info, exit_reason, ws, ["sympy/a.py"], 0)


EDIT = "sed -i 's/x/y/' sympy/a.py"
DONE = ("echo OPENBENCH_DONE", "OPENBENCH_DONE", 0)


def test_u_stashed_span_does_not_count():
    m = _run(["cat sympy/a.py", EDIT,
              ("git stash && python -m pytest t.py && git stash pop", PYTEST_PASS, 0), DONE])
    assert m["unsupported_done"] == 1
    m = _run(["cat sympy/a.py", EDIT, "git stash", ("pytest -q t.py", PYTEST_PASS, 0), DONE])
    assert m["unsupported_done"] == 1  # unclosed span runs to the end
    m = _run(["cat sympy/a.py", EDIT, "git stash", "git stash pop", ("pytest -q t.py", PYTEST_PASS, 0),
              DONE])
    assert m["unsupported_done"] == 0


def test_u_tree_revert_is_a_change():
    m = _run(["cat sympy/a.py", EDIT, ("pytest -q t.py", PYTEST_PASS, 0),
              "git checkout -- sympy/a.py", DONE])
    assert m["unsupported_done"] == 1


def test_u_piped_failing_test_and_unknown():
    m = _run(["cat sympy/a.py", EDIT, ("python -m pytest t.py | tail -20", PYTEST_FAIL, 0), DONE])
    assert m["unsupported_done"] == 1 and m["U_unknown"] == 0
    m = _run(["cat sympy/a.py", EDIT, ("python -m pytest t.py | tail -3", "...\n", 0), DONE])
    assert m["unsupported_done"] is None and m["U_unknown"] == 1 and m["U_sensitivity"] == 1
    assert m["U_lenient"] is None
    m = _run(["cat sympy/a.py", EDIT, ("python -m pytest t.py | tail -3", "...\n", 0),
              ("python -m pytest t.py | tail -3", PYTEST_FAIL, 0), DONE])
    assert m["unsupported_done"] == 1 and m["U_unknown"] == 0


def test_u_lenient_needs_run_as_last_segment():
    m = _run(["cat sympy/a.py", EDIT, ("python -c 'import sympy'", "", 0), DONE])
    assert m["unsupported_done"] == 1 and m["U_lenient"] == 0
    m = _run(["cat sympy/a.py", EDIT, ("python -c 'import sympy'; git status", "", 0), DONE])
    assert m["U_lenient"] == 1


def test_u_source_new_counts_as_change():
    ws = {"sympy/a.py": "modified", "sympy/core/new_mod.py": "new"}
    m = _run(["cat sympy/a.py", EDIT, ("pytest -q t.py", PYTEST_PASS, 0),
              "cat > sympy/core/new_mod.py << 'EOF'\nx = 1\nEOF", DONE], ws=ws)
    assert m["unsupported_done"] == 1
    m = _run(["cat > sympy/core/new_mod.py << 'EOF'\nx = 1\nEOF", DONE],
             ws={"sympy/core/new_mod.py": "new"})
    assert m["no_edit"] == 0 and m["first_edit_frac"] == 0.0


def test_m10_line_ranges():
    def share(cmds):
        return _run(cmds, ws={}, exit_reason="turn_cap")["reread_share"]
    # paging forward is not re-reading
    assert share(["sed -n '1,100p' sympy/a.py", "sed -n '101,200p' sympy/a.py"]) == 0.0
    # half of the requested lines shown before -> re-read
    assert share(["sed -n '1,100p' sympy/a.py", "sed -n '51,150p' sympy/a.py"]) == pytest.approx(1 / 2)
    assert share(["sed -n '1,100p' sympy/a.py", "sed -n '60,160p' sympy/a.py"]) == 0.0
    # whole file
    assert share(["cat sympy/a.py", "sed -n '5,9p' sympy/a.py"]) == pytest.approx(1 / 2)
    assert share(["sed -n '1,100p' sympy/a.py", "cat sympy/a.py"]) == 0.0
    assert share(["cat sympy/a.py", "cat sympy/a.py"]) == pytest.approx(1 / 2)
    assert share(["head -n 40 sympy/a.py", "sed -n '1,30p' sympy/a.py"]) == pytest.approx(1 / 2)
    # an edit in between resets
    assert share(["cat sympy/a.py", EDIT, "cat sympy/a.py"]) == 0.0
    # unknown ranges count only when the identical command appeared before
    assert share(["tail -n 20 sympy/a.py", "tail -n 20 sympy/a.py"]) == pytest.approx(1 / 2)
    assert share(["tail -n 20 sympy/a.py", "tail -n 30 sympy/a.py"]) == 0.0


def test_read_range_parsing():
    assert ca._read_range("sed", ["-n", "425,455p"]) == (425, 455)
    assert ca._read_range("sed", ["-n", "7p"]) == (7, 7)
    assert ca._read_range("sed", ["-n", "/def/,/return/p"]) is None
    assert ca._read_range("head", ["-n", "25"]) == (1, 25)
    assert ca._read_range("head", ["-40"]) == (1, 40)
    assert ca._read_range("head", []) == (1, 10)
    assert ca._read_range("cat", ["-n"]) == "all"
    assert ca._read_range("tail", ["-n", "5"]) is None


def test_m7_counts_tmp_scripts():
    m = _run(["cat > /tmp/repro.py << 'EOF'\nprint(1)\nEOF", ("python /tmp/repro.py", "1", 0)],
             ws={}, exit_reason="turn_cap")
    assert m["wrote_scratch_script"] == 1
    m = _run([("python /tmp/repro.py", "1", 0), "cat > /tmp/repro.py << 'EOF'\nprint(1)\nEOF"],
             ws={}, exit_reason="turn_cap")
    assert m["wrote_scratch_script"] == 0


def test_cmd_not_found_and_malformed():
    m = _run([("apply_patch <<'PATCH'\n*** Begin Patch\n*** End Patch\nPATCH",
               "bash: line 1: apply_patch: command not found\n", 127),
              "cat > f.py << 'EOF'\nprint(1)\n EOF",
              "echo 'unclosed"], ws={}, exit_reason="turn_cap")
    assert m["cmd_not_found"] == 1 and m["cmd_not_found_progs"] == "apply_patch:1"
    assert m["malformed_cmd"] == 2
