"""Regression guards for bugs found during live use.

Each test pins a fix for a bug that previously produced a *wrong result* (not a
crash) and was caught by manual audit rather than a test. If any of these fails,
a result-corrupting regression has slipped back in.
"""

from __future__ import annotations

from datetime import UTC, datetime

from openbench import paths
from openbench.models import HardnessTier

# --- #infra: provider slugs broke Docker container names ----------------------

def test_slugify_model_strips_slashes():
    from openbench.runners.execute import slugify_model

    assert slugify_model("openrouter/deepseek/deepseek-chat-v3-0324") == \
        "openrouter_deepseek_deepseek-chat-v3-0324"
    assert "/" not in slugify_model("a/b/c")
    assert slugify_model("deepseek-v4-pro") == "deepseek-v4-pro"  # already safe


# --- #9: parametrized F2P ids were scored failed regardless of outcome --------

def test_parse_junit_matches_parametrized_expansions():
    """SWE-bench ids are often unparametrized (test_foo) while junit reports the
    expansions (test_foo[a], test_foo[b]). Exact/endswith matching saw neither,
    so a fully passing parametrized test graded as failed (scikit-learn-32659's
    golden gate failed 7/8 F2P on exactly this)."""
    from openbench.grading.mergeability import parse_junit

    xml = """<testsuite>
      <testcase classname="pkg.tests.test_mod" name="test_foo[a]"/>
      <testcase classname="pkg.tests.test_mod" name="test_foo[b]"/>
      <testcase classname="pkg.tests.test_mod" name="test_bar[x]"><failure/></testcase>
      <testcase classname="pkg.tests.test_mod" name="test_bar[y]"/>
      <testcase classname="pkg.tests.test_mod" name="test_plain"/>
    </testsuite>"""
    expected = [
        "pkg/tests/test_mod.py::test_foo",    # all params green -> passed
        "pkg/tests/test_mod.py::test_bar",    # one param red -> failed
        "pkg/tests/test_mod.py::test_plain",  # unparametrized exact -> passed
    ]
    passed, failed = parse_junit(xml, expected)
    assert passed == ["pkg/tests/test_mod.py::test_foo", "pkg/tests/test_mod.py::test_plain"]
    assert failed == ["pkg/tests/test_mod.py::test_bar"]


# --- #8: the cost cap must bind on EVERY loop path, incl. fence-less replies ---

def test_cost_cap_fires_on_fenceless_turns(tmp_path, monkeypatch):
    """A model replying without a bash fence skips exec via `continue`; the cap
    check must still run (it once sat after exec only — a fence-less model
    burned 2.2x the cap on pure prompt tokens before the turn cap saved it)."""
    from openbench.models import RunLimits, Task
    from openbench.runners.harness import Harness
    from openbench.runners.protocols import TextFenceProtocol

    monkeypatch.setattr(paths, "TASKS", tmp_path / "tasks")
    tdir = paths.task_dir("demo__repo-1")
    tdir.mkdir(parents=True)
    (tdir / "prompt.md").write_text("Implement the feature.")
    task = Task(
        task_id="demo__repo-1", repo="demo/repo", pr_number=1,
        base_commit="a" * 40, merge_commit="b" * 40,
        merged_at=datetime(2026, 6, 1, tzinfo=UTC),
        tier=HardnessTier.MAIN, hardness_score=1.0,
    )
    monkeypatch.setattr(
        "openbench.runners.harness.dockerutil.exec_in",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not exec")),
    )

    def chat(messages):  # fence-less reply, $1.00 provider-reported per call
        return {
            "choices": [{"message": {"content": "thinking out loud, no fence"}}],
            "usage": {"prompt_tokens": 9, "completion_tokens": 9, "cost": 1.0},
        }

    runner = Harness(TextFenceProtocol(chat_fn=chat))
    run_path = tmp_path / "run"
    run_path.mkdir()
    exit_reason, usage = runner.run(
        task, "c", run_path, "any-model", RunLimits(max_turns=50, max_cost_usd=2.5)
    )
    assert exit_reason == "cost_cap"
    assert usage["num_turns"] == 3  # 3 x $1.00 crosses $2.50; turn 4 never calls out


# --- #1: the harness must execute the FIRST action, not a hallucinated DONE ----

def test_first_fence_not_hallucinated_done():
    from openbench.runners.protocols import _extract_command

    # model hallucinates a whole trajectory ending in DONE; we take the first real act
    reply = "Let me look.\n```bash\nls src/\n```\n(fake output)\n```bash\necho OPENBENCH_DONE\n```"
    assert _extract_command(reply) == "ls src/"


# --- 29263: P2P must also hold at base+test.patch, not just at the merged commit

def test_validate_drops_p2p_that_needs_the_gold_change(tmp_path, monkeypatch):
    """sympy-29263 shipped 3 'P2P' tests that require the gold change: the gate
    only ran P2P at the MERGED commit, so they passed validation yet failed on
    the unmodified base — an empty agent patch (and any agent not replicating
    gold) failed them, vetoing every resolution. validate_task must run P2P at
    base+test.patch (grading's empty-agent-patch tree) and drop what fails or
    does not collect there."""
    import re

    from openbench import dockerutil
    from openbench.models import Task
    from openbench.tasks.validate import validate_task

    P2P_OK = "tests/test_x.py::test_ok"
    P2P_NEEDS_GOLD = "tests/test_x.py::test_needs_gold"      # collects, fails at base
    P2P_IMPORTS_GOLD = "tests/test_y.py::test_imports_gold"  # can't collect at base
    F2P = [f"tests/test_new.py::test_f2p_{i}" for i in range(3)]

    monkeypatch.setattr(paths, "TASKS", tmp_path / "tasks")
    monkeypatch.setattr(paths, "CONFIGS", tmp_path / "configs")  # default limits
    tdir = paths.task_dir("demo__repo-1")
    tdir.mkdir(parents=True)
    (tdir / "gold.patch").write_text(
        "diff --git a/pkg/mod.py b/pkg/mod.py\n"
        "--- a/pkg/mod.py\n"
        "+++ b/pkg/mod.py\n"
        "@@ -1,1 +1,2 @@\n"
        " x = 1\n"
        "+y = 2\n"
    )
    (tdir / "test.patch").write_text(
        "diff --git a/tests/test_new.py b/tests/test_new.py\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/tests/test_new.py\n"
        "@@ -0,0 +1,6 @@\n"
        "+def test_f2p_0():\n"
        "+    assert True\n"
        "+def test_f2p_1():\n"
        "+    assert True\n"
        "+def test_f2p_2():\n"
        "+    assert True\n"
    )
    task = Task(
        task_id="demo__repo-1", repo="demo/repo", pr_number=1,
        base_commit="a" * 40, merge_commit="b" * 40,
        merged_at=datetime(2026, 6, 1, tzinfo=UTC),
        tier=HardnessTier.MAIN, hardness_score=1.0, image_tag="openbench/demo:1",
    )
    (tdir / "task.json").write_text(task.model_dump_json(indent=2))

    def junit_xml(results: dict[str, str]) -> str:
        cases = []
        for nid, status in results.items():
            path, name = nid.split("::")
            cls = path.removesuffix(".py").replace("/", ".")
            body = "" if status == "passed" else "<failure/>"
            cases.append(
                f'<testcase file="{path}" classname="{cls}" name="{name}">{body}</testcase>'
            )
        return "<testsuite>" + "".join(cases) + "</testsuite>"

    def status_at(container: str, nid: str) -> str:
        if "merged" in container:
            return "passed"  # everything is green at the merge commit
        if nid in F2P or nid == P2P_NEEDS_GOLD:
            return "failed"  # needs the gold change
        return "passed"

    junit_by_container: dict[str, str] = {}

    def fake_exec(container, command, workdir="/repo", timeout=1200, user=None):
        if command.startswith("test -d"):
            return dockerutil.ExecResult(1, "", "")  # no scoping: whole suite
        if "--collect-only" in command:
            if "no:cacheprovider" not in command:
                return dockerutil.ExecResult(0, "", "")  # sanity collect at base
            ids = {*F2P, P2P_OK, P2P_NEEDS_GOLD, P2P_IMPORTS_GOLD}
            if "base" in container:
                ids.discard(P2P_IMPORTS_GOLD)  # ImportError without gold
            return dockerutil.ExecResult(0, "\n".join(sorted(ids)), "")
        if "--junitxml" in command:
            requested = re.findall(r"'([^']+)'", command)
            if requested:
                results = {nid: status_at(container, nid) for nid in requested}
            else:
                # baseline whole-suite run at plain base: every P2P reports
                # green (full-suite ordering hid the dependence on gold)
                results = dict.fromkeys(
                    (P2P_OK, P2P_NEEDS_GOLD, P2P_IMPORTS_GOLD), "passed"
                )
            junit_by_container[container] = junit_xml(results)
            return dockerutil.ExecResult(0, "", "")
        if command.startswith("cat "):
            return dockerutil.ExecResult(0, junit_by_container.get(container, ""), "")
        return dockerutil.ExecResult(0, "", "")  # git/install/find/etc.

    monkeypatch.setattr(dockerutil, "image_exists", lambda tag: True)
    monkeypatch.setattr(dockerutil, "start_container", lambda image, name, **kw: name)
    monkeypatch.setattr(dockerutil, "exec_in", fake_exec)
    monkeypatch.setattr(dockerutil, "copy_in", lambda *a, **k: None)
    monkeypatch.setattr(dockerutil, "remove_container", lambda name: None)

    validation = validate_task("demo__repo-1")

    saved = Task.model_validate_json((tdir / "task.json").read_text())
    assert saved.pass_to_pass == [P2P_OK]
    assert saved.fail_to_pass == sorted(F2P)
    assert {P2P_NEEDS_GOLD, P2P_IMPORTS_GOLD} <= set(validation.flaky_tests_dropped)
    assert validation.p2p_pass_on_base is True
    assert validation.accepted is True
