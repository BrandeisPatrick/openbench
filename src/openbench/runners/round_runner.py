"""Batch runner for a pre-registered, fixed-credit experiment round (round 2).

The design lives in research/experiments/exp-08-opus-line.md ("Design shared by
round 2", "Round budget rule"), exp-09 and exp-10. This module turns a round
config (round.json) into a deterministic plan of cells, runs one stage of it
three at a time, and keeps an append-only ledger (ledger.jsonl, next to the
config) that is the single record of money spent.

Money rules, in order of importance:
- Start rule: a run starts only if
  spent + caps of runs in flight + its own cap <= ceiling - unspent judge reserve.
  Checked and reserved under one lock (Budget.try_reserve), so worker threads
  cannot race past it. The first refusal stops all scheduling.
- Resume: a cell with a finished non-crash attempt in the ledger never runs again.
- An attempt that was paid but never logged (the process died) is found again
  through its `start` line and reconciled on the next start, from run.json when
  the run finished, else from the transcript's logged usage.
- A crash (exit `crash`, or an exception) is rerun once; both attempts count.

Ledger lines (`kind`):
- `spend`   manual spend: {source: prefreeze|manual|judge, cost_usd, note}
- `start`   an attempt began: {cell, stage, attempt, run_id, cap, started_at}
- `attempt` an attempt ended: cell, stage, run_id, exit_reason, cost_usd, turns,
            tokens, started/finished, attempt number, resolved / grade_error
- `grade`   a later grade of an already-logged attempt: {run_id, cell, resolved}
"""

from __future__ import annotations

import json
import os
import random
import threading
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from openbench.models import RunLimits, RunResult

STAGES: tuple[str, ...] = ("pilot", "exp08", "exp09", "exp10-haiku", "exp10-fable")

# Pre-registered drop order (exp-08 "Projection"), id -> label.
DROP_ORDER: tuple[tuple[str, str], ...] = (
    ("fable", "Fable from exp-10"),
    ("exp10", "all of exp-10"),
    ("exp09", "exp-09"),
    ("partb", "Part B (judge reserve)"),
    ("exp08-last-task", "the last task of the frozen list from exp-08"),
)
XHIGH_FACTOR = 1.3

# Exit codes of `run-round` (run mode).
EXIT_OK = 0
EXIT_BUDGET = 3       # start rule refused a run; nothing further scheduled
EXIT_SETUP = 4        # a run failed before it started (missing image, bad config)
EXIT_LOCKED = 5       # another run-round process holds the ledger
EXIT_INTERRUPTED = 130

_EPS = 1e-9
CRASHLIKE = ("crash", "interrupted")


def _now() -> str:
    return datetime.now(UTC).isoformat()


# --------------------------------------------------------------------------- plan


@dataclass(frozen=True)
class Cell:
    stage: str
    task_id: str
    model: str
    effort: str
    repeat: int
    cap: float
    experiments: tuple[str, ...]

    @property
    def key(self) -> str:
        return f"{self.model}|{self.effort}|{self.task_id}|{self.repeat}"


@dataclass
class RoundConfig:
    path: Path
    tasks: list[str]
    bridge_task: str
    seed: int
    ceiling_usd: float
    judge_reserve_usd: float
    spend_before_freeze_usd: float
    cap_usd_by_family: dict[str, float]
    max_turns: int
    wall_clock_s: int
    concurrency: int
    cpus: int
    memory: str
    repeats: int
    pilot_effort: str
    opus_models: list[str]
    opus_effort: str
    sonnet_model: str
    sonnet_efforts: list[str]
    haiku_model: str
    fable_model: str
    ladder_effort: str
    drops: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> RoundConfig:
        raw = json.loads(Path(path).read_text())
        names = set(cls.__dataclass_fields__) - {"path"}
        missing = sorted(n for n in names - set(raw) if n != "drops")
        if missing:
            raise ValueError(f"{path}: missing keys {missing}")
        cfg = cls(path=Path(path), **{k: v for k, v in raw.items() if k in names})
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if len(self.tasks) != len(set(self.tasks)):
            raise ValueError("round.json: duplicate task ids")
        if self.bridge_task not in self.tasks:
            raise ValueError("round.json: bridge_task must be one of tasks")
        bad = [d for d in self.drops if d not in dict(DROP_ORDER)]
        if bad:
            raise ValueError(f"round.json: unknown drops {bad}; valid: {[d for d, _ in DROP_ORDER]}")
        for m in self.pilot_models:
            self.cap_for(m)  # raises on an unknown family

    @property
    def ledger_path(self) -> Path:
        return self.path.parent / "ledger.jsonl"

    @property
    def lock_path(self) -> Path:
        return self.path.parent / "ledger.lock"

    @property
    def pilot_models(self) -> list[str]:
        return [*self.opus_models, self.sonnet_model, self.haiku_model, self.fable_model]

    @property
    def ladder(self) -> list[str]:
        return [self.haiku_model, self.sonnet_model, self.opus_models[-1], self.fable_model]

    def cap_for(self, model: str) -> float:
        parts = model.split("-")
        family = parts[1] if len(parts) > 1 else model
        if family not in self.cap_usd_by_family:
            raise ValueError(f"no dollar cap for model family {family!r} ({model})")
        return float(self.cap_usd_by_family[family])

    def limits(self, cell: Cell) -> RunLimits:
        return RunLimits(
            wall_clock_s=self.wall_clock_s, max_turns=self.max_turns, max_cost_usd=cell.cap
        )

    def experiments(self, model: str, effort: str) -> tuple[str, ...]:
        tags = []
        if model in self.opus_models and effort == self.opus_effort:
            tags.append("exp08")
        if model == self.sonnet_model and effort in self.sonnet_efforts:
            tags.append("exp09")
        if model in self.ladder and effort == self.ladder_effort:
            tags.append("exp10")
        return tuple(tags)

    def is_dropped(self, cell: Cell) -> bool:
        d = set(self.drops)
        if cell.stage == "pilot":
            return False  # the pilot is never dropped (it runs before projection)
        if "fable" in d and cell.stage == "exp10-fable":
            return True
        if "exp10" in d and cell.stage.startswith("exp10"):
            return True
        if "exp09" in d and cell.stage == "exp09":
            return True
        if "exp08-last-task" in d and cell.stage == "exp08" and cell.task_id == self.tasks[-1]:
            return True
        return False

    def judge_reserve(self) -> float:
        return 0.0 if "partb" in self.drops else self.judge_reserve_usd


def _cell(cfg: RoundConfig, stage: str, task: str, model: str, effort: str, rep: int) -> Cell:
    return Cell(stage, task, model, effort, rep, cfg.cap_for(model), cfg.experiments(model, effort))


def build_plan(cfg: RoundConfig) -> list[Cell]:
    """Every cell of the round, in run order (stage, then repeat, then shuffled).

    Depends only on the config. Within a stage the repeat-1 cells come first, in
    an order shuffled with `random.Random(f"{seed}|{stage}|r{repeat}")` applied to
    the cells sorted by key; then the repeat-2 cells, shuffled the same way.
    """
    reps = range(1, cfg.repeats + 1)
    pilot = [_cell(cfg, "pilot", cfg.bridge_task, m, cfg.pilot_effort, 1) for m in cfg.pilot_models]
    taken = {c.key for c in pilot}

    def rest(stage: str, models: Iterable[str], efforts: Iterable[str]) -> list[Cell]:
        efforts = list(efforts)
        out = []
        for m in models:
            for e in efforts:
                for t in cfg.tasks:
                    for r in reps:
                        c = _cell(cfg, stage, t, m, e, r)
                        if c.key not in taken:
                            taken.add(c.key)
                            out.append(c)
        return out

    by_stage = {
        "pilot": pilot,
        "exp08": rest("exp08", cfg.opus_models, [cfg.opus_effort]),
        "exp09": rest("exp09", [cfg.sonnet_model], cfg.sonnet_efforts),
        "exp10-haiku": rest("exp10-haiku", [cfg.haiku_model], [cfg.ladder_effort]),
        "exp10-fable": rest("exp10-fable", [cfg.fable_model], [cfg.ladder_effort]),
    }
    plan: list[Cell] = []
    for stage in STAGES:
        for r in reps:
            group = sorted((c for c in by_stage[stage] if c.repeat == r), key=lambda c: c.key)
            random.Random(f"{cfg.seed}|{stage}|r{r}").shuffle(group)
            plan.extend(group)
    return plan


# ------------------------------------------------------------------------- ledger


class Ledger:
    """Append-only JSONL. Each line is flushed and fsynced before append returns.

    A line cut short by a kill is skipped on read, and the next append starts on
    a fresh line so it cannot glue onto the fragment.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a torn final line from an interrupted write
        return out

    def append(self, entry: dict) -> None:
        line = json.dumps(entry, sort_keys=True)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            needs_nl = False
            if self.path.exists() and self.path.stat().st_size:
                with self.path.open("rb") as f:
                    f.seek(-1, os.SEEK_END)
                    needs_nl = f.read(1) != b"\n"
            with self.path.open("a") as f:
                f.write(("\n" if needs_nl else "") + line + "\n")
                f.flush()
                os.fsync(f.fileno())


def total_spent(entries: list[dict]) -> float:
    return sum(float(e.get("cost_usd") or 0.0) for e in entries if e.get("kind") in ("spend", "attempt"))


def judge_spent(entries: list[dict]) -> float:
    return sum(
        float(e.get("cost_usd") or 0.0)
        for e in entries
        if e.get("kind") == "spend" and e.get("source") == "judge"
    )


def spend_limit(cfg: RoundConfig, entries: list[dict]) -> float:
    """Ceiling minus the still-unspent judge reserve."""
    unspent = max(0.0, cfg.judge_reserve() - judge_spent(entries))
    return cfg.ceiling_usd - unspent


@dataclass
class CellState:
    attempts: list[dict] = field(default_factory=list)

    @property
    def done(self) -> bool:
        return any(a.get("exit_reason") not in CRASHLIKE for a in self.attempts)

    @property
    def crashes(self) -> int:
        # Attempts that failed before any run existed (no run_id, nothing spent)
        # are setup errors, not crashes of the cell.
        return sum(1 for a in self.attempts if a.get("exit_reason") == "crash" and not a.get("prestart"))

    @property
    def gave_up(self) -> bool:
        return not self.done and self.crashes >= 2

    @property
    def status(self) -> str:
        if self.done:
            return "done"
        if self.gave_up:
            return "crashed"
        return "rerun" if self.crashes else "remaining"

    def done_attempt(self) -> dict | None:
        for a in self.attempts:
            if a.get("exit_reason") not in CRASHLIKE:
                return a
        return None


def cell_states(entries: list[dict]) -> dict[str, CellState]:
    states: dict[str, CellState] = defaultdict(CellState)
    for e in entries:
        if e.get("kind") == "attempt":
            states[e["cell"]].attempts.append(e)
    return states


def orphan_starts(entries: list[dict]) -> list[dict]:
    """`start` lines with no `attempt` line for the same run: paid, never logged."""
    ended = {e.get("run_id") for e in entries if e.get("kind") == "attempt"}
    return [e for e in entries if e.get("kind") == "start" and e.get("run_id") not in ended]


def grades(entries: list[dict]) -> dict[str, bool]:
    """run_id -> resolved, from attempt lines and later grade lines (last wins)."""
    out: dict[str, bool] = {}
    for e in entries:
        if e.get("kind") in ("attempt", "grade") and e.get("resolved") is not None:
            out[e["run_id"]] = bool(e["resolved"])
    return out


# ------------------------------------------------------------------------ budget


class Budget:
    """Race-free start rule: reservation and check happen under one lock."""

    def __init__(self, spent: float, limit: float) -> None:
        self.spent = spent
        self.limit = limit
        self.in_flight = 0.0
        self._lock = threading.Lock()

    def try_reserve(self, cap: float) -> bool:
        with self._lock:
            if self.spent + self.in_flight + cap <= self.limit + _EPS:
                self.in_flight += cap
                return True
            return False

    def settle(self, cap: float, cost: float) -> None:
        with self._lock:
            self.in_flight -= cap
            self.spent += cost

    def headroom(self) -> float:
        with self._lock:
            return self.limit - self.spent - self.in_flight


# ------------------------------------------------------------------ run / grade

ExecuteFn = Callable[[Cell, RunLimits, Callable[[str], None]], RunResult]
GradeFn = Callable[[str], bool]


def default_execute(cfg: RoundConfig) -> ExecuteFn:
    def _execute(cell: Cell, limits: RunLimits, on_start: Callable[[str], None]) -> RunResult:
        from openbench.runners import get_runner
        from openbench.runners.execute import execute_run

        return execute_run(
            task_id=cell.task_id,
            runner=get_runner("claude-native", effort=cell.effort),
            model=cell.model,
            limits=limits,
            cpus=cfg.cpus,
            memory=cfg.memory,
            on_start=on_start,
        )

    return _execute


def default_grade(run_id: str) -> bool:
    # Same code path as `openbench grade` (writes runs/<run_id>/grade.json).
    from openbench.grading.mergeability import grade_run

    return grade_run(run_id).resolved


def transcript_cost(run_id: str, model: str) -> float | None:
    """Spend logged in a run's transcript (None if there is no transcript)."""
    from openbench import paths
    from openbench.runners.protocols.providers import claude_cost

    path = paths.run_dir(run_id) / "raw_transcript.jsonl"
    if not path.exists():
        return None
    cost = 0.0
    for line in path.read_text().splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("type") == "final":
            return float((rec.get("usage_totals") or {}).get("cost_usd") or 0.0)
        if rec.get("type") == "api_response" and rec.get("usage_raw"):
            cost += claude_cost(rec["usage_raw"], model)
    return cost


def _attempt_entry(cell: Cell, attempt: int, started_at: str, run_id: str | None) -> dict:
    return {
        "kind": "attempt", "cell": cell.key, "stage": cell.stage, "task_id": cell.task_id,
        "model": cell.model, "effort": cell.effort, "repeat": cell.repeat, "attempt": attempt,
        "cap": cell.cap, "run_id": run_id, "started_at": started_at, "finished_at": None,
        "exit_reason": "crash", "cost_usd": 0.0, "turns": 0, "tokens_in": 0, "tokens_out": 0,
        "tokens_cached": 0, "tokens_thinking": 0, "resolved": None, "grade_error": None,
        "error": None, "prestart": False, "cost_estimated": False,
    }


def reconcile_orphans(cfg: RoundConfig, ledger: Ledger, plan: list[Cell], say: Callable[[str], None]) -> int:
    """Turn each orphaned `start` into an `attempt` line so its spend is counted.

    Run finished (run.json exists): logged with its real exit and cost; the cell
    is then done and is never rerun (it is graded by catch_up_grades). Otherwise
    exit `interrupted`, cost from the transcript's logged usage (a reply in
    flight at the kill is paid but not logged), the cap if there is none.
    """
    from openbench import paths

    by_key = {c.key: c for c in plan}
    n = 0
    for s in orphan_starts(ledger.read()):
        cell = by_key.get(s["cell"]) or _cell_from_key(cfg, s)
        entry = _attempt_entry(cell, int(s.get("attempt", 1)), s.get("started_at", ""), s["run_id"])
        entry["reconciled"] = True
        run_json = paths.run_dir(s["run_id"]) / "run.json"
        if run_json.exists():
            r = RunResult.model_validate_json(run_json.read_text())
            _fill_from_result(entry, r)
        else:
            cost = transcript_cost(s["run_id"], cell.model)
            entry["exit_reason"] = "interrupted"
            entry["cost_estimated"] = True
            entry["cost_usd"] = cell.cap if cost is None else cost
            entry["error"] = "process ended before the attempt was logged"
        ledger.append(entry)
        say(f"reconciled {s['run_id']}: {entry['exit_reason']} ${entry['cost_usd']:.2f}")
        n += 1
    return n


def _cell_from_key(cfg: RoundConfig, start: dict) -> Cell:
    """A start line whose cell is no longer in the plan (task list edited):
    its spend must still be counted, so rebuild the cell from its key."""
    model, effort, task_id, rep = start["cell"].split("|")
    return Cell(start.get("stage", "?"), task_id, model, effort, int(rep),
                float(start.get("cap") or cfg.cap_for(model)), ())


def _fill_from_result(entry: dict, r: RunResult) -> None:
    entry.update(
        run_id=r.run_id, exit_reason=r.exit_reason or "crash", cost_usd=r.total_cost_usd,
        turns=r.num_turns, tokens_in=r.total_tokens_in, tokens_out=r.total_tokens_out,
        tokens_cached=r.total_tokens_cached, tokens_thinking=r.total_thinking_tokens,
        started_at=r.started_at.isoformat(),
        finished_at=(r.finished_at or datetime.now(UTC)).isoformat(),
    )


def catch_up_grades(ledger: Ledger, grade: GradeFn, say: Callable[[str], None]) -> None:
    """Grade finished, non-crash attempts that have no grade yet (a kill during
    grading, or a grade that failed earlier). Appends `grade` lines."""
    entries = ledger.read()
    graded = grades(entries)
    for e in entries:
        if e.get("kind") != "attempt" or e.get("exit_reason") in CRASHLIKE:
            continue
        if not e.get("run_id") or e["run_id"] in graded:
            continue
        line = {"kind": "grade", "cell": e["cell"], "run_id": e["run_id"], "at": _now(),
                "resolved": None, "grade_error": None}
        try:
            line["resolved"] = bool(grade(e["run_id"]))
        except Exception as exc:  # a grade failure never loses the run
            line["grade_error"] = f"{type(exc).__name__}: {exc}"
        ledger.append(line)
        say(f"graded {e['run_id']}: resolved={line['resolved']} {line['grade_error'] or ''}".rstrip())


def _prefreeze_entry(cfg: RoundConfig) -> dict:
    return {"kind": "spend", "source": "prefreeze", "at": _now(),
            "cost_usd": cfg.spend_before_freeze_usd,
            "note": "spent before the freeze (round.json spend_before_freeze_usd)"}


def with_prefreeze(cfg: RoundConfig, entries: list[dict]) -> list[dict]:
    """Entries plus the pre-freeze spend if the ledger does not hold it yet
    (read-only reports must count it before the first run writes it)."""
    if cfg.spend_before_freeze_usd and not any(
        e.get("kind") == "spend" and e.get("source") == "prefreeze" for e in entries
    ):
        return [_prefreeze_entry(cfg), *entries]
    return entries


def ensure_prefreeze(cfg: RoundConfig, ledger: Ledger) -> None:
    entries = ledger.read()
    if with_prefreeze(cfg, entries) is not entries:
        ledger.append(_prefreeze_entry(cfg))


@dataclass
class StageOutcome:
    exit_code: int
    message: str
    ran: int = 0


class _Lock:
    """Exclusive, non-blocking lock so two batch processes never share a ledger."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._f = None

    def __enter__(self) -> bool:
        import fcntl

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = self.path.open("w")
        try:
            fcntl.flock(self._f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._f.close()
            self._f = None
            return False
        return True

    def __exit__(self, *exc) -> None:
        if self._f is not None:
            self._f.close()


def preflight(cells: list[Cell]) -> list[str]:
    """Problems that would make every run of these cells fail before it starts."""
    from openbench import dockerutil, paths
    from openbench.models import Task

    problems = []
    for task_id in sorted({c.task_id for c in cells}):
        tj = paths.task_dir(task_id) / "task.json"
        if not tj.exists():
            problems.append(f"{task_id}: no task.json")
            continue
        task = Task.model_validate_json(tj.read_text())
        if not task.image_tag:
            problems.append(f"{task_id}: no image_tag (run build-env)")
        elif not dockerutil.image_exists(task.image_tag):
            problems.append(f"{task_id}: image {task.image_tag} not found")
    return problems


def task_error(cfg: RoundConfig, task: str | None) -> str | None:
    """Why `task` is not a valid task filter for this round (None if it is)."""
    if task is None or task in cfg.tasks:
        return None
    return f"unknown task {task!r}; round.json tasks: {cfg.tasks}"


def _label(stage: str, task: str | None) -> str:
    return f"stage {stage}" if task is None else f"stage {stage}, task {task}"


def _in_scope(c: Cell, stage: str, task: str | None) -> bool:
    return c.stage == stage and (task is None or c.task_id == task)


def run_stage(
    cfg: RoundConfig,
    stage: str,
    *,
    execute: ExecuteFn | None = None,
    grade: GradeFn | None = None,
    check: Callable[[list[Cell]], list[str]] | None = preflight,
    say: Callable[[str], None] = print,
    task: str | None = None,
) -> StageOutcome:
    """Run every remaining cell of `stage`, `cfg.concurrency` at a time.

    With `task`, only that task's cells of the stage, in plan order; preflight
    then checks only that task. Orphan reconciliation and catch-up grading
    still cover the whole ledger.
    """
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}; expected one of {list(STAGES)}")
    err = task_error(cfg, task)
    if err:
        return StageOutcome(EXIT_SETUP, err)
    execute = execute or default_execute(cfg)
    grade = grade or default_grade
    lock = _Lock(cfg.lock_path)
    if not lock.__enter__():
        return StageOutcome(EXIT_LOCKED, f"another run-round holds {cfg.lock_path}")
    try:
        return _run_locked(cfg, stage, execute, grade, check, say, task)
    finally:
        lock.__exit__()


def _run_locked(cfg, stage, execute, grade, check, say, task=None) -> StageOutcome:
    ledger = Ledger(cfg.ledger_path)
    plan = build_plan(cfg)
    ensure_prefreeze(cfg, ledger)
    reconcile_orphans(cfg, ledger, plan, say)
    catch_up_grades(ledger, grade, say)

    label = _label(stage, task)
    entries = ledger.read()
    states = cell_states(entries)
    todo = [
        c for c in plan
        if _in_scope(c, stage, task) and not cfg.is_dropped(c)
        and not states[c.key].done and not states[c.key].gave_up
    ]
    if not todo:
        return StageOutcome(EXIT_OK, f"{label}: nothing left to run")
    if check is not None:
        problems = check(todo)
        if problems:
            return StageOutcome(EXIT_SETUP, "preflight failed:\n  " + "\n  ".join(problems))

    budget = Budget(total_spent(entries), spend_limit(cfg, entries))
    say(f"{label}: {len(todo)} cells, spent ${budget.spent:.2f} of limit ${budget.limit:.2f}")
    stop = threading.Event()
    reason: dict[str, str] = {}
    prior = {c.key: list(states[c.key].attempts) for c in todo}
    slots = threading.Semaphore(cfg.concurrency)
    ran = Counter()
    ran_lock = threading.Lock()

    def halt(code: str, msg: str) -> None:
        reason.setdefault("code", code)
        reason.setdefault("msg", msg)
        stop.set()

    def one_attempt(cell: Cell, attempt: int) -> dict:
        started_at = _now()
        entry = _attempt_entry(cell, attempt, started_at, None)

        def on_start(run_id: str) -> None:
            entry["run_id"] = run_id
            ledger.append({"kind": "start", "cell": cell.key, "stage": cell.stage,
                           "attempt": attempt, "run_id": run_id, "cap": cell.cap,
                           "started_at": started_at})

        try:
            r = execute(cell, cfg.limits(cell), on_start)
            _fill_from_result(entry, r)
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
            if entry["run_id"] is None:
                entry["prestart"] = True  # nothing started, nothing spent
            else:
                cost = transcript_cost(entry["run_id"], cell.model)
                entry["cost_usd"] = cell.cap if cost is None else cost
                entry["cost_estimated"] = True
        if entry["exit_reason"] not in CRASHLIKE and entry["run_id"]:
            try:
                entry["resolved"] = bool(grade(entry["run_id"]))
            except Exception as exc:  # a grade failure never loses the run
                entry["grade_error"] = f"{type(exc).__name__}: {exc}"
        entry["finished_at"] = entry["finished_at"] or _now()
        return entry

    def worker(cell: Cell) -> None:
        try:
            attempts = prior[cell.key]
            while True:
                entry = one_attempt(cell, len(attempts) + 1)
                budget.settle(cell.cap, float(entry["cost_usd"]))
                ledger.append(entry)
                attempts.append(entry)
                with ran_lock:
                    ran["n"] += 1
                say(_fmt(entry, budget))
                if entry["prestart"]:
                    halt("setup", f"{cell.key} failed before starting: {entry['error']}")
                    return
                if entry["exit_reason"] != "crash" or CellState(attempts).crashes >= 2:
                    return
                if stop.is_set():
                    return
                if not budget.try_reserve(cell.cap):
                    halt("budget", _budget_msg(cell, budget, rerun=True))
                    return
                say(f"rerunning {cell.key} after a crash")
        except Exception as exc:  # never let a worker die silently
            halt("setup", f"{cell.key}: worker error {type(exc).__name__}: {exc}")
        finally:
            slots.release()

    futures: list[Future] = []
    pool = ThreadPoolExecutor(max_workers=cfg.concurrency)
    try:
        for cell in todo:
            while not slots.acquire(timeout=0.5):
                pass
            if stop.is_set():
                slots.release()
                break
            if not budget.try_reserve(cell.cap):
                slots.release()
                halt("budget", _budget_msg(cell, budget, rerun=False))
                break
            futures.append(pool.submit(worker, cell))
        _wait_all(futures)
    except KeyboardInterrupt:
        halt("interrupted", "interrupted: no new runs; waiting for runs in flight to finish "
             "(Ctrl-C again exits at once: containers may be left running, and the next "
             "start reconciles the unlogged attempts from the ledger)")
        say(reason["msg"])
        try:
            _wait_all(futures)
        except KeyboardInterrupt:
            os._exit(EXIT_INTERRUPTED)
    finally:
        pool.shutdown(wait=True)

    code = reason.get("code")
    if code == "budget":
        return StageOutcome(EXIT_BUDGET, reason["msg"], ran["n"])
    if code == "setup":
        return StageOutcome(EXIT_SETUP, reason["msg"], ran["n"])
    if code == "interrupted":
        return StageOutcome(EXIT_INTERRUPTED, "interrupted; runs in flight finished and are logged", ran["n"])
    return StageOutcome(EXIT_OK, f"{label}: finished ({ran['n']} attempts)", ran["n"])


def _wait_all(futures: list[Future]) -> None:
    pending = set(futures)
    while pending:
        _, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)


def _budget_msg(cell: Cell, budget: Budget, rerun: bool) -> str:
    what = "crash rerun of" if rerun else "run"
    return (
        f"START RULE: the {what} {cell.key} (cap ${cell.cap:.2f}) would cross the limit "
        f"${budget.limit:.2f} (spent ${budget.spent:.2f}, in flight ${budget.in_flight:.2f}). "
        "Nothing further scheduled; runs in flight finished."
    )


def _fmt(e: dict, budget: Budget) -> str:
    mark = {True: "RESOLVED", False: "unresolved", None: "ungraded"}[e["resolved"]]
    extra = f" error={e['error']}" if e["error"] else ""
    extra += f" grade_error={e['grade_error']}" if e["grade_error"] else ""
    return (
        f"{e['cell']} #{e['attempt']}: {e['exit_reason']} {mark} ${e['cost_usd']:.2f} "
        f"{e['turns']} turns (spent ${budget.spent:.2f}){extra}"
    )


# ------------------------------------------------------------- reports (read-only)


def dry_run(cfg: RoundConfig, stage: str, task: str | None = None) -> str:
    err = task_error(cfg, task)
    if err:
        raise ValueError(err)
    plan = build_plan(cfg)
    states = cell_states(Ledger(cfg.ledger_path).read())
    lines = [f"{_label(stage, task)}: schedule in order"]
    to_run = []
    for i, c in enumerate(c for c in plan if _in_scope(c, stage, task)):
        st = "dropped" if cfg.is_dropped(c) else states[c.key].status
        if st in ("remaining", "rerun"):
            to_run.append(c)
        lines.append(
            f"{i + 1:4d}  {st:9s}  r{c.repeat}  {c.model:20s} {c.effort:7s} {c.task_id:32s} "
            f"cap ${c.cap:.2f}  [{','.join(c.experiments)}]"
        )
    worst = sum(c.cap for c in to_run)
    lines.append(f"runs to start: {len(to_run)}")
    lines.append(f"worst-case spend (sum of caps): ${worst:.2f}"
                 f"  (if every run crashed once: ${2 * worst:.2f})")
    return "\n".join(lines)


def status(cfg: RoundConfig) -> str:
    plan = build_plan(cfg)
    entries = with_prefreeze(cfg, Ledger(cfg.ledger_path).read())
    states = cell_states(entries)
    graded = grades(entries)
    lines = [f"{'stage':12s} {'done':>5s} {'crashed':>8s} {'rerun':>6s} {'remain':>7s} {'dropped':>8s} {'resolved':>9s}"]
    for stage in STAGES:
        cnt: Counter[str] = Counter()
        resolved = 0
        for c in plan:
            if c.stage != stage:
                continue
            st = states[c.key].status
            if cfg.is_dropped(c) and st != "done":
                st = "dropped"
            cnt[st] += 1
            a = states[c.key].done_attempt()
            if a and graded.get(a.get("run_id") or ""):
                resolved += 1
        lines.append(f"{stage:12s} {cnt['done']:5d} {cnt['crashed']:8d} {cnt['rerun']:6d} "
                     f"{cnt['remaining']:7d} {cnt['dropped']:8d} {resolved:9d}")
    width = max(len("task"), *(len(t) for t in cfg.tasks))
    lines.append(f"{'task':{width}s} {'done':>5s} {'remain':>7s} {'dropped':>8s}  (all stages)")
    for t in cfg.tasks:
        cnt = Counter()
        for c in plan:
            if c.task_id != t:
                continue
            st = states[c.key].status
            if cfg.is_dropped(c) and st != "done":
                st = "dropped"
            cnt[st] += 1
        lines.append(f"{t:{width}s} {cnt['done']:5d} {cnt['remaining'] + cnt['rerun']:7d} "
                     f"{cnt['dropped']:8d}")
    spent = total_spent(entries)
    limit = spend_limit(cfg, entries)
    lines.append(f"spent ${spent:.2f}; run limit ${limit:.2f} (ceiling ${cfg.ceiling_usd:.2f} "
                 f"minus unspent judge reserve); headroom ${limit - spent:.2f}")
    by_model: dict[str, float] = defaultdict(float)
    for e in entries:
        if e.get("kind") == "attempt":
            by_model[e["model"]] += float(e.get("cost_usd") or 0.0)
        elif e.get("kind") == "spend":
            by_model[f"(spend: {e.get('source')})"] += float(e.get("cost_usd") or 0.0)
    for m, v in sorted(by_model.items()):
        lines.append(f"  {m:28s} ${v:7.2f}")
    orphans = orphan_starts(entries)
    if orphans:
        lines.append(f"{len(orphans)} attempt(s) started but not logged (in flight now, or "
                     "interrupted; the next run-round reconciles them): "
                     + ", ".join(o["run_id"] for o in orphans))
    return "\n".join(lines)


def projection(cfg: RoundConfig) -> str:
    """exp-08 "Projection": pilot cost per model, projected remaining, drops."""
    plan = build_plan(cfg)
    entries = with_prefreeze(cfg, Ledger(cfg.ledger_path).read())
    states = cell_states(entries)
    pilot_cost: dict[str, float] = {}
    for c in plan:
        if c.stage == "pilot":
            a = states[c.key].done_attempt()
            if a is not None:
                pilot_cost[c.model] = float(a["cost_usd"])
    lines = ["pilot cost per run:"]
    for m in cfg.pilot_models:
        lines.append(f"  {m:20s} " + (f"${pilot_cost[m]:.2f}" if m in pilot_cost else "(no finished pilot run)"))
    missing = [m for m in cfg.pilot_models if m not in pilot_cost]
    if missing:
        lines.append(f"cannot project: no finished pilot run for {missing}")
        return "\n".join(lines)

    remaining = [c for c in plan if c.stage != "pilot" and states[c.key].status in ("remaining", "rerun")]

    def cost(c: Cell) -> float:
        return pilot_cost[c.model] * (XHIGH_FACTOR if c.effort == "xhigh" else 1.0)

    spent = total_spent(entries)
    unspent_reserve = max(0.0, cfg.judge_reserve_usd - judge_spent(entries))
    by_stage: dict[str, float] = defaultdict(float)
    for c in remaining:
        by_stage[c.stage] += cost(c)
    lines.append("projected cost of remaining cells:")
    for s in STAGES[1:]:
        n = sum(1 for c in remaining if c.stage == s)
        lines.append(f"  {s:12s} {n:3d} runs  ${by_stage[s]:.2f}")

    def total(drops: set[str]) -> float:
        probe = RoundConfig(**{**cfg.__dict__, "drops": sorted(drops)})
        proj = sum(cost(c) for c in remaining if not probe.is_dropped(c))
        reserve = 0.0 if "partb" in drops else unspent_reserve
        return spent + proj + reserve

    t0 = total(set())
    lines.append(f"spent ${spent:.2f} + projected ${t0 - spent - unspent_reserve:.2f} "
                 f"+ judge reserve ${unspent_reserve:.2f} = ${t0:.2f} against ceiling ${cfg.ceiling_usd:.2f}")
    if t0 <= cfg.ceiling_usd + _EPS:
        lines.append("fits: no drops needed")
        return "\n".join(lines)
    applied: set[str] = set()
    for did, label in DROP_ORDER:
        applied.add(did)
        t = total(applied)
        lines.append(f"  drop {label} [{did}] -> ${t:.2f}")
        if t <= cfg.ceiling_usd + _EPS:
            lines.append(f"pre-registered drops that make it fit: {sorted(applied, key=_drop_rank)} "
                         "(set them as \"drops\" in round.json; this command changed nothing)")
            return "\n".join(lines)
    lines.append("does NOT fit even with every pre-registered drop")
    return "\n".join(lines)


def _drop_rank(d: str) -> int:
    return [x for x, _ in DROP_ORDER].index(d)


def add_spend(cfg: RoundConfig, amount: float, source: str, note: str) -> None:
    if source not in ("manual", "judge", "prefreeze"):
        raise ValueError("source must be manual, judge or prefreeze")
    Ledger(cfg.ledger_path).append(
        {"kind": "spend", "source": source, "cost_usd": float(amount), "note": note, "at": _now()}
    )
