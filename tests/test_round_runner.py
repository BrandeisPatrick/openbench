"""Round runner (runners/round_runner.py): plan, ledger, start rule, resume,
crash rerun, interruption. Fake runs only: no Docker, no API."""

from __future__ import annotations

import json
import shutil
import threading
import time
from collections import Counter
from datetime import UTC, datetime

import httpx
import pytest

from openbench import paths
from openbench.models import RunResult
from openbench.runners import round_runner as rr

ROUND_JSON = paths.ROOT / "research/corpus/runs-2026-11-claude-round/round.json"


@pytest.fixture
def cfg(tmp_path, monkeypatch) -> rr.RoundConfig:
    monkeypatch.setattr(paths, "RUNS", tmp_path / "runs")
    shutil.copy(ROUND_JSON, tmp_path / "round.json")
    return rr.RoundConfig.load(tmp_path / "round.json")


class FakeRuns:
    """execute() stand-in: per-model exit reason / cost, records calls."""

    def __init__(self, exit_for=None, cost=1.0, hold=0.0, raise_for=()):
        self.exit_for = exit_for or {}
        self.cost = cost
        self.hold = hold
        self.raise_for = set(raise_for)
        self.calls: list[str] = []
        self._lock = threading.Lock()
        self._n = 0

    def __call__(self, cell, limits, on_start):
        with self._lock:
            self._n += 1
            run_id = f"{cell.task_id}--claude-native--{cell.model}--{self._n:04d}"
            self.calls.append(cell.key)
        assert limits.max_cost_usd == cell.cap and limits.max_turns == 100
        on_start(run_id)
        if self.hold:
            time.sleep(self.hold)
        if cell.model in self.raise_for:
            raise RuntimeError("container died")
        now = datetime.now(UTC)
        return RunResult(
            run_id=run_id, task_id=cell.task_id, harness="claude-native", model=cell.model,
            started_at=now, finished_at=now, exit_reason=self.exit_for.get(cell.model, "completed"),
            total_cost_usd=self.cost, num_turns=7, effort=cell.effort,
        )


def _run(cfg, stage="pilot", fake=None, grade=lambda run_id: True):
    fake = fake or FakeRuns()
    out = rr.run_stage(cfg, stage, execute=fake, grade=grade, check=None, say=lambda m: None)
    return out, fake


def _attempts(cfg):
    return [e for e in rr.Ledger(cfg.ledger_path).read() if e["kind"] == "attempt"]


# --------------------------------------------------------------------- plan


def test_plan_has_132_cells_with_the_stage_sizes(cfg):
    plan = rr.build_plan(cfg)
    assert len(plan) == 132
    assert Counter(c.stage for c in plan) == {
        "pilot": 8, "exp08": 55, "exp09": 47, "exp10-haiku": 11, "exp10-fable": 11,
    }
    assert len({c.key for c in plan}) == 132
    # pilot: repeat 1, bridge task, effort high, all eight models
    pilot = [c for c in plan if c.stage == "pilot"]
    assert {c.task_id for c in pilot} == {"sympy__sympy-13757"}
    assert {c.effort for c in pilot} == {"high"} and {c.repeat for c in pilot} == {1}
    assert len({c.model for c in pilot}) == 8
    caps = {c.model: c.cap for c in plan}
    assert caps["claude-opus-4-6"] == 6 and caps["claude-fable-5-2"] == 8
    assert caps["claude-sonnet-5-5"] == 3 and caps["claude-haiku-5-5"] == 1
    tags = {(c.model, c.effort): c.experiments for c in plan}
    assert tags[("claude-opus-5-5", "high")] == ("exp08", "exp10")
    assert tags[("claude-sonnet-5-5", "high")] == ("exp09", "exp10")
    assert tags[("claude-sonnet-5-5", "low")] == ("exp09",)


def test_plan_is_deterministic_and_depends_only_on_the_file(cfg, tmp_path):
    a = rr.build_plan(cfg)
    assert a == rr.build_plan(rr.RoundConfig.load(cfg.path))
    # Filling in a real task id changes only that task's cells, not the order of others.
    raw = json.loads(cfg.path.read_text())
    raw["tasks"][1] = "astropy__astropy-12907"
    other = tmp_path / "other" / "round.json"
    other.parent.mkdir()
    other.write_text(json.dumps(raw))
    b = rr.build_plan(rr.RoundConfig.load(other))
    assert [c.key for c in a if c.stage == "pilot"] == [c.key for c in b if c.stage == "pilot"]
    assert len(b) == 132
    # a different seed gives a different order
    raw["seed"] = 1
    other.write_text(json.dumps(raw))
    c = rr.build_plan(rr.RoundConfig.load(other))
    assert [x.key for x in b] != [x.key for x in c]


def test_stage_order_and_repeat_1_before_repeat_2(cfg):
    plan = rr.build_plan(cfg)
    stage_idx = [rr.STAGES.index(c.stage) for c in plan]
    assert stage_idx == sorted(stage_idx)
    for stage in rr.STAGES:
        reps = [c.repeat for c in plan if c.stage == stage]
        assert reps == sorted(reps), stage
        # shuffled: not simply grouped by model
        models = [c.model for c in plan if c.stage == stage and c.repeat == 1]
        if stage == "exp08":
            assert models != sorted(models)


# ------------------------------------------------------------- start rule


def test_budget_reservation_counts_runs_in_flight():
    b = rr.Budget(spent=100.0, limit=115.0)
    assert b.try_reserve(6.0)       # 100 + 0 + 6
    assert b.try_reserve(6.0)       # 100 + 6 + 6 = 112
    assert not b.try_reserve(6.0)   # 100 + 12 + 6 = 118 > 115
    assert b.try_reserve(3.0)       # exactly 115 is allowed
    b.settle(6.0, 0.5)
    assert b.spent == 100.5 and b.in_flight == 9.0


def test_budget_is_race_free():
    b = rr.Budget(spent=0.0, limit=10.0)
    ok = []
    barrier = threading.Barrier(50)

    def grab():
        barrier.wait()
        ok.append(b.try_reserve(1.0))

    threads = [threading.Thread(target=grab) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(ok) == 10


def test_start_rule_refuses_with_runs_in_flight_and_stops(cfg):
    # Pilot order starts opus-4-8 ($6), sonnet ($3), opus-4-7 ($6). Spent 100.09
    # leaves 14.91 under the 115 limit: the first two start, the third would make
    # 100.09 + 9 in flight + 6 = 115.09 and is refused, though without the runs in
    # flight it would fit (106.09).
    order = [c.model for c in rr.build_plan(cfg) if c.stage == "pilot"][:3]
    assert order == ["claude-opus-4-8", "claude-sonnet-5-5", "claude-opus-4-7"]
    rr.add_spend(cfg, 100.0, "manual", "test")
    out, fake = _run(cfg, fake=FakeRuns(hold=0.3))
    assert out.exit_code == rr.EXIT_BUDGET
    assert "START RULE" in out.message and "claude-opus-4-7" in out.message
    assert len(fake.calls) == 2  # nothing further scheduled
    assert len(_attempts(cfg)) == 2  # runs in flight finished and were logged


def test_start_rule_refuses_the_run_that_would_cross_the_ceiling(cfg):
    # + 0.09 prefreeze = 108.59 spent, 6.41 left under 115: the $6 opus-4-8 run
    # starts; the $3 sonnet run would make 108.59 + 6 + 3 = 117.59 and is refused.
    rr.add_spend(cfg, 108.5, "manual", "test")
    out, fake = _run(cfg, fake=FakeRuns(hold=0.2))
    assert out.exit_code == rr.EXIT_BUDGET
    assert len(fake.calls) == 1 and fake.calls[0].startswith("claude-opus-4-8")
    spent = rr.total_spent(rr.Ledger(cfg.ledger_path).read())
    assert spent <= cfg.ceiling_usd - cfg.judge_reserve_usd


def test_judge_spend_releases_the_reserve(cfg):
    led = rr.Ledger(cfg.ledger_path)
    assert rr.spend_limit(cfg, led.read()) == 115.0
    rr.add_spend(cfg, 4.0, "judge", "part B")
    assert rr.spend_limit(cfg, led.read()) == 119.0


# --------------------------------------------------- resume / crash rerun


def test_prefreeze_spend_is_written_once(cfg):
    _run(cfg)
    _run(cfg)
    spends = [e for e in rr.Ledger(cfg.ledger_path).read() if e["kind"] == "spend"]
    assert [e["cost_usd"] for e in spends] == [0.09]


def test_resume_skips_finished_cells(cfg):
    out, fake = _run(cfg)
    assert out.exit_code == 0 and len(fake.calls) == 8
    out2, fake2 = _run(cfg)
    assert fake2.calls == [] and "nothing left" in out2.message
    lines = _attempts(cfg)
    assert len(lines) == 8 and all(e["resolved"] is True for e in lines)
    e = lines[0]
    for k in ("cell", "stage", "run_id", "exit_reason", "cost_usd", "turns", "tokens_in",
              "tokens_out", "started_at", "finished_at", "attempt", "resolved"):
        assert k in e


def test_non_crash_caps_count_as_finished(cfg):
    fake = FakeRuns(exit_for={"claude-haiku-5-5": "cost_cap", "claude-opus-5": "timeout"})
    _run(cfg, fake=fake)
    _, again = _run(cfg)
    assert again.calls == []


def test_crash_is_rerun_exactly_once(cfg):
    fake = FakeRuns(exit_for={"claude-haiku-5-5": "crash"})
    out, _ = _run(cfg, fake=fake)
    assert out.exit_code == 0
    haiku = [e for e in _attempts(cfg) if e["model"] == "claude-haiku-5-5"]
    assert [e["attempt"] for e in haiku] == [1, 2]
    assert all(e["exit_reason"] == "crash" and e["resolved"] is None for e in haiku)
    assert rr.total_spent(rr.Ledger(cfg.ledger_path).read()) == pytest.approx(0.09 + 9 * 1.0)
    # a restart does not try a third time
    _, again = _run(cfg)
    assert again.calls == []
    assert "crashed" in rr.status(cfg)


def test_exception_counts_as_crash_and_rerun_succeeds_after_restart(cfg):
    # Attempt 1 raises (after the run started: cap charged, no transcript).
    _run(cfg, fake=FakeRuns(raise_for={"claude-fable-5-2"}, exit_for={}))
    fable = [e for e in _attempts(cfg) if e["model"] == "claude-fable-5-2"]
    assert len(fable) == 2 and all(e["cost_estimated"] for e in fable)
    assert fable[0]["cost_usd"] == 8.0 and "container died" in fable[0]["error"]


def test_crash_then_restart_uses_the_remaining_rerun(cfg):
    rr.Ledger(cfg.ledger_path).append({
        "kind": "attempt", "cell": "claude-haiku-5-5|high|sympy__sympy-13757|1", "stage": "pilot",
        "model": "claude-haiku-5-5", "attempt": 1, "run_id": "x", "exit_reason": "crash",
        "cost_usd": 0.2,
    })
    _, fake = _run(cfg)
    assert len(fake.calls) == 8
    haiku = [e for e in _attempts(cfg) if e["model"] == "claude-haiku-5-5"]
    assert [e["attempt"] for e in haiku] == [1, 2]


def test_grade_failure_keeps_the_run_and_is_retried_later(cfg):
    def bad_grade(run_id):
        raise RuntimeError("docker gone")

    _run(cfg, grade=bad_grade)
    lines = _attempts(cfg)
    assert len(lines) == 8 and all("docker gone" in e["grade_error"] for e in lines)
    _, fake = _run(cfg)  # restart: no rerun, but the grades are caught up
    assert fake.calls == []
    graded = [e for e in rr.Ledger(cfg.ledger_path).read() if e["kind"] == "grade"]
    assert len(graded) == 8 and all(g["resolved"] for g in graded)


def test_setup_error_before_start_stops_without_burning_the_crash_rerun(cfg):
    def no_image(cell, limits, on_start):
        raise ValueError("no image_tag")

    out = rr.run_stage(cfg, "pilot", execute=no_image, grade=lambda r: True, check=None,
                       say=lambda m: None)
    assert out.exit_code == rr.EXIT_SETUP
    states = rr.cell_states(rr.Ledger(cfg.ledger_path).read())
    assert all(s.status == "remaining" for s in states.values())


# ------------------------------------------------------------ interruption


def test_ledger_survives_a_torn_last_line(cfg):
    led = rr.Ledger(cfg.ledger_path)
    led.append({"kind": "spend", "source": "manual", "cost_usd": 1.0})
    with cfg.ledger_path.open("a") as f:
        f.write('{"kind": "attempt", "cell": "cut sh')  # killed mid-write
    led.append({"kind": "spend", "source": "manual", "cost_usd": 2.0})
    assert [e["cost_usd"] for e in led.read()] == [1.0, 2.0]


def _write_run(run_id, model, *, finished: bool, turns_cost: list[dict]):
    d = paths.run_dir(run_id)
    d.mkdir(parents=True)
    with (d / "raw_transcript.jsonl").open("w") as f:
        f.write(json.dumps({"type": "meta", "model": model}) + "\n")
        for i, u in enumerate(turns_cost, 1):
            f.write(json.dumps({"type": "api_response", "turn": i, "usage_raw": u}) + "\n")
    if finished:
        now = datetime.now(UTC)
        (d / "run.json").write_text(RunResult(
            run_id=run_id, task_id="sympy__sympy-13757", harness="claude-native", model=model,
            started_at=now, finished_at=now, exit_reason="completed", total_cost_usd=2.5,
            num_turns=30).model_dump_json())


def test_interrupted_attempts_are_reconciled_not_repaid(cfg):
    led = rr.Ledger(cfg.ledger_path)
    # Process killed while grading opus-5 (run finished) and mid-run of haiku.
    for model, rid in (("claude-opus-5", "r-opus5"), ("claude-haiku-5-5", "r-haiku")):
        led.append({"kind": "start", "cell": f"{model}|high|sympy__sympy-13757|1",
                    "stage": "pilot", "attempt": 1, "run_id": rid, "cap": 1.0,
                    "started_at": "2026-11-13T00:00:00+00:00"})
    _write_run("r-opus5", "claude-opus-5", finished=True, turns_cost=[])
    _write_run("r-haiku", "claude-haiku-5-5", finished=False,
               turns_cost=[{"input_tokens": 1_000_000, "output_tokens": 0}])
    assert "started but not logged" in rr.status(cfg)

    _, fake = _run(cfg)
    entries = led.read()
    opus5 = [e for e in entries if e["kind"] == "attempt" and e["model"] == "claude-opus-5"]
    assert len(opus5) == 1 and opus5[0]["reconciled"] and opus5[0]["cost_usd"] == 2.5
    assert any(e["kind"] == "grade" and e["run_id"] == "r-opus5" for e in entries)
    haiku = [e for e in entries if e["kind"] == "attempt" and e["model"] == "claude-haiku-5-5"]
    assert haiku[0]["exit_reason"] == "interrupted" and haiku[0]["cost_estimated"]
    assert haiku[0]["cost_usd"] > 0
    assert haiku[1]["attempt"] == 2 and haiku[1]["exit_reason"] == "completed"
    # opus-5 finished before the kill: never paid for twice
    assert not any(k.startswith("claude-opus-5|") for k in fake.calls)
    assert len(fake.calls) == 7
    assert rr.orphan_starts(led.read()) == []


def test_second_process_is_locked_out(cfg):
    lock = rr._Lock(cfg.lock_path)
    assert lock.__enter__()
    try:
        out, fake = _run(cfg)
        assert out.exit_code == rr.EXIT_LOCKED and fake.calls == []
    finally:
        lock.__exit__()


# ------------------------------------------------------------ reports


def test_dry_run_touches_nothing(cfg):
    text = rr.dry_run(cfg, "pilot")
    assert "runs to start: 8" in text and "$42.00" in text
    assert not cfg.ledger_path.exists()


def test_projection_reports_drops_in_order(cfg):
    _run(cfg, fake=FakeRuns(cost=2.0))  # every pilot run cost $2
    text = rr.projection(cfg)
    # remaining 124 runs at $2 (exp09 xhigh x1.3) far exceeds 125
    assert "drop Fable from exp-10" in text and "exp-09" in text
    assert "claude-fable-5-2     $2.00" in text
    before = cfg.ledger_path.read_text()
    rr.projection(cfg)
    assert cfg.ledger_path.read_text() == before  # changed nothing


def test_projection_fits_when_cheap(cfg):
    _run(cfg, fake=FakeRuns(cost=0.1))
    assert "fits: no drops needed" in rr.projection(cfg)


def test_drops_in_config_remove_cells_from_the_schedule(cfg):
    raw = json.loads(cfg.path.read_text())
    raw["drops"] = ["fable", "partb"]
    cfg.path.write_text(json.dumps(raw))
    c2 = rr.RoundConfig.load(cfg.path)
    assert "runs to start: 0" in rr.dry_run(c2, "exp10-fable")
    assert rr.spend_limit(c2, []) == 125.0


# ------------------------------------------------------------ effort wiring


def test_effort_is_a_run_parameter():
    from openbench.runners import get_runner
    from openbench.runners.execute import _runner_effort

    assert get_runner("claude-native").protocol.meta()["thinking_effort"] == "xhigh"
    low = get_runner("claude-native", effort="low")
    assert low.protocol.meta()["thinking_effort"] == "low" and _runner_effort(low) == "low"
    assert _runner_effort(get_runner("claude-native", effort=None)) is None
    assert _runner_effort(get_runner("tooluse")) is None
    with pytest.raises(ValueError):
        get_runner("tooluse", effort="high")


# ------------------------------------------------------------ retries


def _client(responses):
    it = iter(responses)

    def handler(request):
        return next(it)

    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://x")


def test_retry_honors_retry_after_on_429_and_529(monkeypatch):
    from openbench.runners.protocols import base

    slept: list[float] = []
    monkeypatch.setattr(base, "_sleep", slept.append)
    c = _client([
        httpx.Response(429, headers={"retry-after": "45"}, text="rate"),
        httpx.Response(529, text="overloaded"),
        httpx.Response(200, json={"ok": True}),
    ])
    assert base._post_with_retry(c, "/v1", {}) == {"ok": True}
    assert slept[0] == 45.0 and 1.0 <= slept[1] <= 2.0


def test_retry_after_http_date_does_not_crash(monkeypatch):
    from openbench.runners.protocols import base

    monkeypatch.setattr(base, "_sleep", lambda s: None)
    c = _client([
        httpx.Response(429, headers={"retry-after": "Wed, 21 Oct 2015 07:28:00 GMT"}),
        httpx.Response(200, json={"ok": 1}),
    ])
    assert base._post_with_retry(c, "/v1", {}) == {"ok": 1}


def test_400_is_not_retried(monkeypatch):
    from openbench.runners.protocols import base

    slept: list[float] = []
    monkeypatch.setattr(base, "_sleep", slept.append)
    c = _client([httpx.Response(400, text="bad"), httpx.Response(200, json={})])
    with pytest.raises(RuntimeError, match="rejected"):
        base._post_with_retry(c, "/v1", {})
    assert slept == []


def test_rate_limit_backoff_rides_out_a_minute(monkeypatch):
    from openbench.runners.protocols import base

    slept: list[float] = []
    monkeypatch.setattr(base, "_sleep", slept.append)
    c = _client([httpx.Response(429)] * base._MAX_ATTEMPTS)
    with pytest.raises(RuntimeError, match="HTTP 429"):
        base._post_with_retry(c, "/v1", {})
    assert len(slept) == base._MAX_ATTEMPTS - 1  # no pointless wait after the last try
    assert sum(slept) > 120


# ------------------------------------------------------------ task filter


def _run_task(cfg, stage, task, fake=None, check=None):
    fake = fake or FakeRuns(cost=0.01)
    msgs: list[str] = []
    out = rr.run_stage(cfg, stage, execute=fake, grade=lambda r: True, check=check,
                       say=msgs.append, task=task)
    return out, fake, msgs


def test_filtered_run_schedules_only_that_task_in_plan_order(cfg):
    cfg.concurrency = 1  # call order == schedule order
    task = cfg.tasks[1]
    out, fake, msgs = _run_task(cfg, "exp08", task)
    want = [c.key for c in rr.build_plan(cfg) if c.stage == "exp08" and c.task_id == task]
    assert len(want) == 10
    assert out.exit_code == rr.EXIT_OK and fake.calls == want
    assert f"stage exp08, task {task}: 10 cells" in msgs[0]
    assert f"task {task}" in out.message
    # repeat-1 cells come before repeat-2 cells
    reps = [int(k.rsplit("|", 1)[1]) for k in fake.calls]
    assert reps == sorted(reps)
    again, fake2, _ = _run_task(cfg, "exp08", task)
    assert fake2.calls == [] and again.message == f"stage exp08, task {task}: nothing left to run"


def test_second_filtered_run_picks_up_another_task(cfg):
    _run_task(cfg, "exp08", cfg.tasks[1])
    out, fake, _ = _run_task(cfg, "exp08", cfg.tasks[2])
    assert out.exit_code == rr.EXIT_OK
    assert len(fake.calls) == 10
    assert {k.split("|")[2] for k in fake.calls} == {cfg.tasks[2]}
    done = {e["task_id"] for e in _attempts(cfg)}
    assert done == {cfg.tasks[1], cfg.tasks[2]}


def test_all_tasks_filtered_leaves_nothing_for_the_unfiltered_stage(cfg):
    total = 0
    for t in cfg.tasks:
        out, fake, _ = _run_task(cfg, "exp08", t)
        assert out.exit_code == rr.EXIT_OK
        total += len(fake.calls)
    assert total == 55
    out, fake = _run(cfg, "exp08")
    assert fake.calls == [] and out.message == "stage exp08: nothing left to run"


def test_unknown_task_is_a_setup_error(cfg):
    out, fake, _ = _run_task(cfg, "exp08", "no-such-task")
    assert out.exit_code == rr.EXIT_SETUP and "no-such-task" in out.message
    assert fake.calls == [] and not cfg.ledger_path.exists()
    with pytest.raises(ValueError, match="no-such-task"):
        rr.dry_run(cfg, "exp08", task="no-such-task")


def test_preflight_sees_only_the_filtered_task(cfg):
    seen: list[set[str]] = []

    def check(cells):
        seen.append({c.task_id for c in cells})
        return [f"{cells[0].task_id}: image not found"]

    out, fake, _ = _run_task(cfg, "exp08", cfg.tasks[3], check=check)
    assert seen == [{cfg.tasks[3]}]
    assert out.exit_code == rr.EXIT_SETUP and fake.calls == []


def test_filtered_dry_run(cfg):
    task = cfg.tasks[1]
    text = rr.dry_run(cfg, "exp08", task=task)
    assert text.startswith(f"stage exp08, task {task}: schedule in order")
    assert "runs to start: 10" in text and "$60.00" in text
    rows = [ln for ln in text.splitlines() if " cap $" in ln]
    assert len(rows) == 10 and all(task in ln for ln in rows)
    want = [c for c in rr.build_plan(cfg) if c.stage == "exp08" and c.task_id == task]
    assert [ln.split()[3] for ln in rows] == [c.model for c in want]
    # the bridge task already ran its repeat-1 cells in the pilot
    assert "runs to start: 5" in rr.dry_run(cfg, "exp08", task=cfg.bridge_task)
    assert not cfg.ledger_path.exists()


def test_status_has_a_per_task_table(cfg):
    _run(cfg, "pilot")
    _run_task(cfg, "exp08", cfg.tasks[1])
    raw = json.loads(cfg.path.read_text())
    raw["drops"] = ["fable"]
    cfg.path.write_text(json.dumps(raw))
    text = rr.status(rr.RoundConfig.load(cfg.path))
    lines = text.splitlines()
    head = next(i for i, ln in enumerate(lines) if ln.startswith("task "))
    assert lines[head].split()[:4] == ["task", "done", "remain", "dropped"]
    rows = {ln.split()[0]: [int(x) for x in ln.split()[1:4]] for ln in lines[head + 1:head + 7]}
    assert list(rows) == cfg.tasks
    plan = rr.build_plan(cfg)
    for t, (done, remain, dropped) in rows.items():
        n = sum(1 for c in plan if c.task_id == t)
        assert done + remain + dropped == n, t
    # bridge: 8 pilot done; task 2: its 10 exp08 cells done
    assert rows[cfg.bridge_task][0] == 8
    assert rows[cfg.tasks[1]][0] == 10
    fable = {t: sum(1 for c in plan if c.task_id == t and c.stage == "exp10-fable") for t in cfg.tasks}
    assert all(rows[t][2] == fable[t] for t in cfg.tasks)
    # the per-stage table is still first
    assert lines[0].startswith("stage ")
