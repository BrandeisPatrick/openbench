"""exp-08 Part B judge: B1 propose, B2 freeze, B3 label (B4 is claude_round.part_b).

Specification: research/experiments/exp-08-opus-line.md, section "Part B -
open contrast between the endpoints". This header records every choice the
spec leaves open. Pattern: research/analysis/judge_pass.py (exp-07, frozen;
only its JSON extractor is imported here).

Judge and request
-----------------
Model claude-sonnet-5-5, POST https://api.anthropic.com/v1/messages through
openbench.anthropic_auth.make_client and
openbench.runners.protocols.base._post_with_retry (the claude-native
runner's path). Body: model, max_tokens MAX_TOKENS, thinking
{"type": "adaptive"}, output_config {"effort": "medium"}, one user message.
Nothing else is sent (no structured-output format, no system prompt, no
sampling parameters). The prompt asks for one JSON object; the answer is the
first balanced JSON object in the `text` blocks. stop_reason `max_tokens` or
`refusal` -> recorded as missing, no retry. A reply that does not parse (or
fails validation) is asked once more with a note appended; a second failure is
recorded as missing. An API rejection (4xx) ends the command.

What the judge reads for one run
--------------------------------
From raw_transcript.jsonl: per turn, the thinking summary
(api_response.reasoning_content), the command, its exit code and its output
(exec records). Nothing else: no meta record, no assistant text, no usage, no
run id, no task id, no patch. Per turn:
    ### turn T
    thinking: <summary>
    $ <command>
    [exit C]
    <output>
Identity stripping (before any cut): every model id of round.json and every
match of IDENTITY_PATTERNS (claude / anthropic / opus / sonnet / haiku / fable,
with any version suffix) is replaced by `[model]`, case-insensitively; the
run id is replaced by `[run]`. Runs are called A and B.
Shortening, identical for every run: output > OUT_HEAD + OUT_TAIL chars ->
first OUT_HEAD + `[... N chars cut ...]` + last OUT_TAIL; thinking summary ->
THINK_HEAD / THINK_TAIL likewise; command -> CMD_HEAD / CMD_TAIL. A run whose
rendering exceeds RUN_CAP chars has the thinking and output of its middle
turns replaced by `[thinking and output omitted]`, nearest the middle first,
until it fits; if that is not enough, whole middle turns become
`### turn T [turn omitted]`.

Run selection
-------------
Ledger and transcripts through claude_round.load_ledger / select_cells: a
cell's run is its latest attempt that did not end crash or interrupted.
exp-08 cells: model in round.json opus_models, effort == opus_effort.
B1: discovery tasks = round.json tasks[:3]; per task and repeat 1..2 the
claude-opus-4-6 run and the claude-opus-5-5 run, in both orders (old as A,
then new as A): 12 calls. A missing cell skips its pair, reported.
B3: held-out tasks = round.json tasks[-3:]; all five opus_models, repeats
1..2: 30 runs, two passes each (60 calls). The two passes send the same
prompt; they are separate calls (the pass number is part of the cache key).
No shuffling is needed anywhere: every order is task list order x model
order x repeat x pass. (SEED is kept for any later use.)

Outputs (research/results/exp-08-opus-line/judge/)
--------------------------------------------------
cache/<stage>/<key>.json  raw reply (full API response) per request; key =
                          sha256 of {stage, item id, pass, request body}.
proposals.json            B1: per call the A/B -> model/run mapping, status
                          and the parsed difference list.
candidates.json           B2: at most 12 candidates (id C01.., name, rule,
                          merged_from) plus the numbered proposals. Must be
                          committed before `label` runs.
labels.json               B3: a JSON list of {run_id, level (model id),
                          task_id, repeat, candidate, pass, value 0/1}: the
                          input of claude_round.part_b(labels, opus_models,
                          held-out tasks). Kappa and B4 are computed there.

Budget
------
Before every call: worst case = ceil(prompt chars / CHARS_PER_TOKEN) input
tokens at the judge's input rate + MAX_TOKENS at its output rate
(providers.claude_price). The call is refused when judge dollars already in
the round ledger (round_runner.judge_spent) + worst case > the round's judge
reserve (RoundConfig.judge_reserve(): judge_reserve_usd, 0 if Part B was
dropped). After every call its real cost (providers.claude_cost of the
reply's usage) is appended to the ledger with round_runner.add_spend(source
"judge"). A refused call ends the command with exit code 3.
Worst case of the whole plan at these constants: 12 x ~$0.16 + 1 x ~$0.11 +
60 x ~$0.12 = about $9.4, under the $10 reserve (parse re-asks excluded).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

from openbench.runners import round_runner as rr
from openbench.runners.protocols.providers import claude_cost, claude_price

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import claude_round as cr  # noqa: E402
import command_audit as ca  # noqa: E402
from judge_pass import extract_json  # noqa: E402

MODEL = "claude-sonnet-5-5"
API_URL = "https://api.anthropic.com/v1/messages"
EFFORT = "medium"
MAX_TOKENS = 8000          # output cap per call (thinking + answer); keeps the plan's
                           # worst case under the $10 reserve
CHARS_PER_TOKEN = 3        # input-token estimate for the budget guard (as exp-07)
OUT_HEAD, OUT_TAIL = 400, 200
THINK_HEAD, THINK_TAIL = 500, 300
CMD_HEAD, CMD_TAIL = 600, 400
RUN_CAP = 60_000           # rendered chars per run
PROPOSE_MAX = 8            # differences kept per B1 call (spec sets no number)
CANDIDATES_MAX = 12        # B2, from the spec
SEED = cr.SEED
OLDEST, NEWEST = "claude-opus-4-6", "claude-opus-5-5"
REPEATS = (1, 2)
PASSES = (1, 2)
NOTE_PREFIX = "exp-08 part B"
EXIT_COMMIT = 2
EXIT_BUDGET = rr.EXIT_BUDGET
DEFAULT_OUT = cr.RESULTS / "exp-08-opus-line" / "judge"

# No \b: "_" is a word character, so "claude_opus" would slip past a word boundary.
IDENTITY_PATTERNS = [
    re.compile(r"(?<![a-z0-9])(?:claude|anthropic)(?:[\s_-]*(?:opus|sonnet|haiku|fable))?"
               r"(?:[\s_-]*\d+(?:[._-]\d+)*)?", re.I),
    re.compile(r"(?<![a-z0-9])(?:opus|sonnet|haiku|fable)(?:[\s_-]*\d+(?:[._-]\d+)*)?", re.I),
]

CONTEXT = (
    "You are reading logs of autonomous coding agents. Each agent was asked to fix an issue in "
    "a Python repository checked out at /repo, using one bash command per turn, and to run "
    "`echo OPENBENCH_DONE` when finished. For each turn a log shows the agent's thinking "
    "summary, the command, its exit code and its output. Long thinking, commands and outputs "
    "are cut to their start and end (cuts are marked), and in long logs the middle turns may be "
    "omitted (also marked). Product and model names are replaced by [model].")
JSON_ONLY = "Answer with a single JSON object with exactly these fields and no other text."
REASK = ("\n\nYour previous answer could not be read. Reply with exactly one JSON object in "
         "the requested format and no other text.")


# --------------------------------------------------------------------------
# Rendering one run
# --------------------------------------------------------------------------

def cut(s: str, head: int, tail: int) -> str:
    if len(s) <= head + tail:
        return s
    return f"{s[:head]}\n[... {len(s) - head - tail} chars cut ...]\n{s[-tail:]}"


def scrub(s: str, secrets=()) -> str:
    """Replace every model id / name and the given secrets (run ids)."""
    for sec in sorted((x for x in secrets if x), key=len, reverse=True):
        s = re.sub(re.escape(sec), "[run]", s, flags=re.I)
    for m in sorted(_MODELS, key=len, reverse=True):
        s = re.sub(re.escape(m), "[model]", s, flags=re.I)
    for pat in IDENTITY_PATTERNS:
        s = pat.sub("[model]", s)
    return s


_MODELS: list[str] = []   # round.json's model ids, set by load_cfg; stripped before the patterns


def run_turns(run_dir) -> list[dict]:
    """-> [{turn, thinking, command, exit_code, output}] from the transcript; meta never read."""
    turns: dict = {}
    for r in cr.read_transcript(run_dir)["replies"]:
        t = r.get("turn")
        turns.setdefault(t, {"turn": t})["thinking"] = r.get("reasoning_content") or ""
    for r in ca.load_exec(str(run_dir))[0]:
        t = r.get("turn")
        d = turns.setdefault(t, {"turn": t})
        d.update(command=r.get("command") or "", exit_code=r.get("exit_code"),
                 output=r.get("output") or "")
    return [turns[k] for k in sorted(turns, key=lambda x: (x is None, x if x is not None else 0))]


def _turn_text(d: dict, secrets, omit=False) -> str:
    lines = [f"### turn {d['turn']}"]
    think = scrub(str(d.get("thinking") or ""), secrets).strip()
    if "command" in d:
        cmd = cut(scrub(str(d["command"]), secrets), CMD_HEAD, CMD_TAIL)
    if omit:
        if "command" in d:
            lines.append(f"$ {cmd}")
        lines.append("[thinking and output omitted]")
        return "\n".join(lines) + "\n"
    if think:
        lines.append("thinking: " + cut(think, THINK_HEAD, THINK_TAIL))
    if "command" in d:
        lines.append(f"$ {cmd}")
        lines.append(f"[exit {d.get('exit_code')}]")
        lines.append(cut(scrub(str(d.get("output") or ""), secrets), OUT_HEAD, OUT_TAIL))
    else:
        lines.append("(no command)")
    return "\n".join(lines) + "\n"


def render_turns(turns: list[dict], secrets=(), cap: int = RUN_CAP) -> tuple[str, bool]:
    """-> (text, truncated). Same rule for every run (see header)."""
    parts = [_turn_text(d, secrets) for d in turns]
    total = sum(len(p) for p in parts)
    if total <= cap:
        return "".join(parts), False
    mid = (len(parts) - 1) / 2
    order = sorted(range(len(parts)), key=lambda i: (abs(i - mid), i))
    for i in order:
        if total <= cap:
            break
        new = _turn_text(turns[i], secrets, omit=True)
        total += len(new) - len(parts[i])
        parts[i] = new
    for i in order:
        if total <= cap:
            break
        new = f"### turn {turns[i]['turn']} [turn omitted]\n"
        total += len(new) - len(parts[i])
        parts[i] = new
    return "".join(parts), True


def render_run(cell: dict, cap: int = RUN_CAP) -> tuple[str, bool]:
    return render_turns(run_turns(cell["dir"]), secrets=(cell.get("run_id"),), cap=cap)


# --------------------------------------------------------------------------
# Prompts and parsers
# --------------------------------------------------------------------------

def propose_prompt(log_a: str, log_b: str) -> str:
    return (f"{CONTEXT}\n\nBelow are the logs of two different agents, A and B, on the same "
            "task.\n\n=== Run A ===\n" + log_a + "\n=== Run B ===\n" + log_b +
            f"\nList at most {PROPOSE_MAX} differences in how A and B work that could be checked "
            "from a log like these. Describe how the agent works, not whether it succeeded. For "
            "each difference give: name (a few words); rule (a yes/no question that can be "
            "decided for ONE run from its log alone); shown_by (\"A\" or \"B\", the run for which "
            "the answer is yes); evidence (one sentence citing turns).\n"
            'Format: {"differences": [{"name": "...", "rule": "...", "shown_by": "A", '
            f'"evidence": "..."}}]}}\n{JSON_ONLY}')


def parse_propose(obj) -> list[dict] | None:
    if not isinstance(obj, dict) or not isinstance(obj.get("differences"), list):
        return None
    out = []
    for d in obj["differences"]:
        if not isinstance(d, dict):
            continue
        name, rule, by = d.get("name"), d.get("rule"), d.get("shown_by")
        if isinstance(name, str) and name.strip() and isinstance(rule, str) and rule.strip() \
                and by in ("A", "B"):
            out.append({"name": name.strip(), "rule": rule.strip(), "shown_by": by,
                        "evidence": str(d.get("evidence") or "")})
    return out[:PROPOSE_MAX]


def freeze_prompt(proposals: list[dict]) -> str:
    lines = "\n".join(f"{p['pid']}: {p['name']} -- {p['rule']}" for p in proposals)
    return ("You are merging proposed behaviors of coding agents into one list. A reader compared "
            "pairs of agent logs and proposed the differences below, each with a yes/no rule.\n\n"
            "Proposals:\n" + lines +
            f"\n\nMerge duplicates and near-duplicates into at most {CANDIDATES_MAX} candidate "
            "behaviors. Prefer behaviors proposed more than once and rules that are specific. "
            "Each candidate needs a rule that can be answered yes or no for ONE run from its log "
            "alone (commands, outputs and thinking summaries), without comparing to another run. "
            "For each candidate give name, rule and merged_from (the proposal ids it covers).\n"
            'Format: {"candidates": [{"name": "...", "rule": "...", "merged_from": ["P001"]}]}\n'
            f"{JSON_ONLY}")


def parse_freeze(obj) -> list[dict] | None:
    if not isinstance(obj, dict) or not isinstance(obj.get("candidates"), list):
        return None
    out = []
    for c in obj["candidates"]:
        if not isinstance(c, dict):
            continue
        name, rule = c.get("name"), c.get("rule")
        if isinstance(name, str) and name.strip() and isinstance(rule, str) and rule.strip():
            mf = c.get("merged_from")
            out.append({"name": name.strip(), "rule": rule.strip(),
                        "merged_from": [str(x) for x in mf] if isinstance(mf, list) else []})
    if not out:
        return None
    # At most 12 (spec); extra ones are cut in reply order. Ids are assigned here.
    return [{"id": f"C{i:02d}", **c} for i, c in enumerate(out[:CANDIDATES_MAX], 1)]


def label_prompt(log: str, candidates: list[dict]) -> str:
    cands = "\n".join(f"{c['id']}: {c['name']} -- {c['rule']}" for c in candidates)
    example = ", ".join(f'"{c["id"]}": "yes"' for c in candidates[:2])
    return (f"{CONTEXT}\n\nLog of one run:\n{log}\n"
            "For every candidate behavior below, answer its rule for this run: yes or no.\n\n"
            f"Candidates:\n{cands}\n\n"
            f'Format: {{"answers": {{{example}, ...}}}} with one entry per candidate id, each '
            f'"yes" or "no".\n{JSON_ONLY}')


def _yes_no(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, str) and v.strip().lower() in ("yes", "no"):
        return int(v.strip().lower() == "yes")
    return None


def parse_label(obj, ids: list[str]) -> dict | None:
    """-> {candidate id: 0/1} with every id answered, else None (malformed)."""
    if not isinstance(obj, dict) or not isinstance(obj.get("answers"), dict):
        return None
    ans = obj["answers"]
    out = {}
    for i in ids:
        v = _yes_no(ans.get(i))
        if v is None:
            return None
        out[i] = v
    return out


# --------------------------------------------------------------------------
# Calls: cache, budget guard, ledger
# --------------------------------------------------------------------------

class BudgetRefused(Exception):
    pass


def request_body(prompt: str) -> dict:
    return {"model": MODEL, "max_tokens": MAX_TOKENS, "thinking": {"type": "adaptive"},
            "output_config": {"effort": EFFORT},
            "messages": [{"role": "user", "content": prompt}]}


def request_key(stage: str, item_id: str, body: dict, pass_no: int = 0) -> str:
    # The item id is part of the key so that two runs with identical logs still get one call
    # each; the pass number makes the two B3 passes separate calls.
    blob = json.dumps({"stage": stage, "item": item_id, "pass": pass_no, "body": body},
                      sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def worst_case_usd(prompt: str) -> float:
    p = claude_price(MODEL)
    return (math.ceil(len(prompt) / CHARS_PER_TOKEN) * p.input + MAX_TOKENS * p.output) / 1e6


def reply_text(resp: dict) -> str:
    return "".join(b.get("text", "") for b in resp.get("content") or [] if b.get("type") == "text")


_CLIENT = None


def api_chat(body: dict) -> dict:
    """POST one Messages request with the openbench credentials (imported lazily)."""
    global _CLIENT
    from openbench.anthropic_auth import make_client
    from openbench.runners.protocols.base import _post_with_retry
    if _CLIENT is None:
        _CLIENT = make_client(timeout=900, purpose="for the exp-08 Part B judge")
    return _post_with_retry(_CLIENT, API_URL, body)


class Judge:
    def __init__(self, cfg: rr.RoundConfig, out_dir, chat=None):
        self.cfg = cfg
        self.out_dir = Path(out_dir)
        self.chat = chat or api_chat
        self.ledger = rr.Ledger(cfg.ledger_path)
        self.calls = 0

    def cache_path(self, stage: str, key: str) -> Path:
        return self.out_dir / "cache" / stage / f"{key}.json"

    def is_cached(self, stage: str, item_id: str, prompt: str, pass_no: int = 0) -> bool:
        key = request_key(stage, item_id, request_body(prompt), pass_no)
        return self.cache_path(stage, key).is_file()

    def spent(self) -> float:
        return rr.judge_spent(self.ledger.read())

    def raw(self, stage: str, item_id: str, prompt: str, pass_no: int = 0) -> dict:
        """Cached reply, else one guarded call. -> cache record."""
        body = request_body(prompt)
        key = request_key(stage, item_id, body, pass_no)
        p = self.cache_path(stage, key)
        if p.is_file():
            return json.loads(p.read_text())
        worst = worst_case_usd(prompt)
        spent = self.spent()
        reserve = self.cfg.judge_reserve()
        if spent + worst > reserve + 1e-9:
            raise BudgetRefused(
                f"budget: judge spend ${spent:.4f} + worst case ${worst:.4f} for {stage} "
                f"{item_id} would exceed the judge reserve ${reserve:.2f}; call not started")
        resp = self.chat(body)
        self.calls += 1
        cost = claude_cost(resp.get("usage") or {}, MODEL)
        rr.add_spend(self.cfg, cost, "judge", f"{NOTE_PREFIX} {stage} {item_id} pass {pass_no} "
                     f"key {key[:12]}")
        rec = {"key": key, "stage": stage, "item_id": item_id, "pass": pass_no,
               "cost_usd": cost, "worst_case_usd": worst, "response": resp}
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rec, indent=1))
        return rec

    def ask(self, stage: str, item_id: str, prompt: str, parse, pass_no: int = 0) -> dict:
        """-> {status: ok|parse_error|max_tokens|refusal, answer, keys}. One re-ask on parse error."""
        keys = []
        for attempt, pr in enumerate((prompt, prompt + REASK)):
            rec = self.raw(stage, item_id if attempt == 0 else item_id + "#reask", pr, pass_no)
            keys.append(rec["key"])
            resp = rec["response"]
            stop = resp.get("stop_reason")
            if stop in ("max_tokens", "refusal"):
                return {"status": stop, "answer": None, "keys": keys}
            answer = parse(extract_json(reply_text(resp)) or None)
            if answer is not None:
                return {"status": "ok", "answer": answer, "keys": keys}
        return {"status": "parse_error", "answer": None, "keys": keys}


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------

def load_cfg(round_json) -> rr.RoundConfig:
    cfg = rr.RoundConfig.load(Path(round_json))
    _MODELS[:] = sorted(set(cfg.pilot_models) | set(cfg.opus_models))
    return cfg


def exp08_cells(cfg: rr.RoundConfig, runs_root) -> dict:
    """{(model, task_id, repeat): ledger entry with `dir`} for exp-08 cells."""
    if not cfg.ledger_path.is_file():
        raise SystemExit(f"no round ledger at {cfg.ledger_path}")
    cells, _ = cr.select_cells(cr.load_ledger(cfg.ledger_path), runs_root)
    return {(m, t, rep): e for (m, eff, t, rep), e in cells.items()
            if m in cfg.opus_models and eff == cfg.opus_effort}


def discovery_tasks(cfg) -> list[str]:
    return list(cfg.tasks[:3])


def held_out_tasks(cfg) -> list[str]:
    return list(cfg.tasks[-3:])


# --------------------------------------------------------------------------
# B1 propose
# --------------------------------------------------------------------------

def plan_propose(cfg, cells) -> tuple[list[dict], list[str]]:
    items, missing = [], []
    for t in discovery_tasks(cfg):
        for rep in REPEATS:
            old, new = cells.get((OLDEST, t, rep)), cells.get((NEWEST, t, rep))
            if old is None or new is None:
                missing.append(f"{t} repeat {rep}: " + ", ".join(
                    m for m, c in ((OLDEST, old), (NEWEST, new)) if c is None))
                continue
            logs = {OLDEST: render_run(old), NEWEST: render_run(new)}
            runs = {OLDEST: old, NEWEST: new}
            for order, (a, b) in (("old-first", (OLDEST, NEWEST)), ("new-first", (NEWEST, OLDEST))):
                items.append({
                    "item_id": f"{t}|r{rep}|{order}",
                    "prompt": propose_prompt(logs[a][0], logs[b][0]),
                    "meta": {"task_id": t, "repeat": rep, "order": order,
                             "A": {"model": a, "run_id": runs[a]["run_id"],
                                   "truncated": logs[a][1]},
                             "B": {"model": b, "run_id": runs[b]["run_id"],
                                   "truncated": logs[b][1]}}})
    return items, missing


def run_propose(judge: Judge, items: list[dict]) -> list[dict]:
    out = []
    try:
        for it in items:
            res = judge.ask("propose", it["item_id"], it["prompt"], parse_propose)
            diffs = [{**d, "shown_by_model": it["meta"][d["shown_by"]]["model"]}
                     for d in (res["answer"] or [])]
            out.append({"item_id": it["item_id"], **it["meta"], "status": res["status"],
                        "keys": res["keys"], "differences": diffs})
    finally:
        _write(judge.out_dir / "proposals.json", {"judge_model": MODEL, "items": out})
    return out


# --------------------------------------------------------------------------
# B2 freeze
# --------------------------------------------------------------------------

def numbered_proposals(proposals: list[dict]) -> list[dict]:
    out = []
    for it in proposals:
        for d in it["differences"]:
            out.append({"pid": f"P{len(out) + 1:03d}", "name": d["name"], "rule": d["rule"],
                        "item_id": it["item_id"], "shown_by_model": d.get("shown_by_model")})
    return out


def run_freeze(judge: Judge, n_planned: int) -> dict:
    pp = judge.out_dir / "proposals.json"
    if not pp.is_file():
        raise SystemExit("freeze needs proposals.json; run `propose` first")
    items = json.loads(pp.read_text())["items"]
    if len(items) < n_planned:
        raise SystemExit(f"freeze needs every propose call ({len(items)} of {n_planned} done)")
    props = numbered_proposals(items)
    if not props:
        raise SystemExit("no parsed proposals; nothing to freeze")
    res = judge.ask("freeze", "freeze", freeze_prompt(props), parse_freeze)
    if res["answer"] is None:
        raise SystemExit(f"freeze reply missing ({res['status']}); candidates.json not written")
    out = {"judge_model": MODEL, "status": res["status"], "keys": res["keys"],
           "candidates": res["answer"], "proposals": props}
    _write(judge.out_dir / "candidates.json", out)
    return out


# --------------------------------------------------------------------------
# B3 label
# --------------------------------------------------------------------------

def _git(args, cwd) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def commit_check(path) -> str | None:
    """None if `path` is committed in git and unchanged since; else the reason."""
    p = Path(path).resolve()
    if not p.is_file():
        return f"{p} does not exist (run `freeze`, then commit it)"
    top = _git(["rev-parse", "--show-toplevel"], p.parent)
    if top.returncode != 0:
        return f"{p} is not inside a git repository"
    root = top.stdout.strip()
    rel = os.path.relpath(p, root)
    if _git(["cat-file", "-e", f"HEAD:{rel}"], root).returncode != 0:
        return f"{rel} is not committed (commit the candidate list before labelling)"
    st = _git(["status", "--porcelain", "--", rel], root)
    if st.returncode != 0 or st.stdout.strip():
        return f"{rel} has changes since its last commit (commit or restore it)"
    return None


def plan_label(cfg, cells, candidates) -> tuple[list[dict], list[str]]:
    items, missing = [], []
    for t in held_out_tasks(cfg):
        for m in cfg.opus_models:
            for rep in REPEATS:
                c = cells.get((m, t, rep))
                if c is None:
                    missing.append(f"{m} {t} repeat {rep}")
                    continue
                log, trunc = render_run(c)
                prompt = label_prompt(log, candidates)
                for pn in PASSES:
                    items.append({"item_id": f"{t}|{m}|r{rep}", "pass": pn, "prompt": prompt,
                                  "meta": {"run_id": c["run_id"], "level": m, "task_id": t,
                                           "repeat": rep, "truncated": trunc}})
    return items, missing


def run_label(judge: Judge, items: list[dict], candidates: list[dict]) -> tuple[list, list]:
    ids = [c["id"] for c in candidates]
    labels, failed = [], []
    try:
        for it in items:
            res = judge.ask("label", it["item_id"], it["prompt"],
                            lambda o: parse_label(o, ids), pass_no=it["pass"])
            if res["answer"] is None:
                failed.append(f"{it['item_id']} pass {it['pass']}: {res['status']}")
                continue
            m = it["meta"]
            for cid in ids:
                labels.append({"run_id": m["run_id"], "level": m["level"], "task_id": m["task_id"],
                               "repeat": m["repeat"], "candidate": cid, "pass": it["pass"],
                               "value": res["answer"][cid]})
    finally:
        _write(judge.out_dir / "labels.json", labels)
    return labels, failed


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1) + "\n")


def _estimate(judge: Judge, stage: str, items: list[dict]) -> str:
    todo = [it for it in items
            if not judge.is_cached(stage, it["item_id"], it["prompt"], it.get("pass", 0))]
    worst = sum(worst_case_usd(it["prompt"]) for it in todo)
    return (f"{stage}: {len(items)} planned calls, {len(items) - len(todo)} cached; worst case of "
            f"the rest ${worst:.2f}; judge spend so far ${judge.spent():.4f} of "
            f"${judge.cfg.judge_reserve():.2f}")


def status(judge: Judge) -> str:
    entries = judge.ledger.read()
    mine = [e for e in entries if e.get("kind") == "spend" and e.get("source") == "judge"
            and str(e.get("note") or "").startswith(NOTE_PREFIX)]
    by_stage = Counter(str(e["note"]).split()[len(NOTE_PREFIX.split())] for e in mine)
    lines = [f"judge calls made: {len(mine)} {dict(by_stage)}",
             f"judge dollars spent (all judge entries): ${rr.judge_spent(entries):.4f} of "
             f"${judge.cfg.judge_reserve():.2f}"]
    for name in ("proposals.json", "candidates.json", "labels.json"):
        p = judge.out_dir / name
        lines.append(f"{name}: {'present' if p.is_file() else 'missing'}")
    cp = judge.out_dir / "candidates.json"
    if cp.is_file():
        why = commit_check(cp)
        lines.append("candidates.json committed and unchanged" if why is None else f"note: {why}")
    return "\n".join(lines)


def main(argv=None, chat=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["propose", "freeze", "label", "status"])
    ap.add_argument("--round-json", default=str(cr.ROUND_JSON))
    ap.add_argument("--runs-root", default=str(cr.manifest.ROOT / "runs"))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    ap.add_argument("--dry-run", action="store_true",
                    help="propose/label: list planned calls and the worst case; no call")
    a = ap.parse_args(argv)
    cfg = load_cfg(a.round_json)
    judge = Judge(cfg, a.out_dir, chat=chat)
    if a.command == "status":
        print(status(judge))
        return 0
    try:
        if a.command == "propose":
            items, missing = plan_propose(cfg, exp08_cells(cfg, a.runs_root))
            for m in missing:
                print(f"missing cell, pair skipped: {m}")
            if a.dry_run:
                print(_estimate(judge, "propose", items))
                return 0
            out = run_propose(judge, items)
            print(f"propose: {Counter(o['status'] for o in out)}; "
                  f"wrote {judge.out_dir / 'proposals.json'}")
        elif a.command == "freeze":
            items, _ = plan_propose(cfg, exp08_cells(cfg, a.runs_root))
            out = run_freeze(judge, len(items))
            print(f"freeze: {len(out['candidates'])} candidates; wrote "
                  f"{judge.out_dir / 'candidates.json'}; commit it before `label`")
        elif a.command == "label":
            cp = judge.out_dir / "candidates.json"
            why = commit_check(cp)
            if why is not None and not a.dry_run:
                print(f"label refused: {why}", file=sys.stderr)
                return EXIT_COMMIT
            candidates = json.loads(cp.read_text())["candidates"] if cp.is_file() else [
                {"id": f"C{i:02d}", "name": "x" * 40, "rule": "x" * 200}
                for i in range(1, CANDIDATES_MAX + 1)]   # dry run before the freeze
            items, missing = plan_label(cfg, exp08_cells(cfg, a.runs_root), candidates)
            for m in missing:
                print(f"missing cell, run skipped: {m}")
            if a.dry_run:
                print(_estimate(judge, "label", items))
                return 0
            labels, failed = run_label(judge, items, candidates)
            for f in failed:
                print(f"no labels: {f}")
            print(f"label: {len(labels)} labels from {len(items) - len(failed)} of {len(items)} "
                  f"calls; wrote {judge.out_dir / 'labels.json'}")
    except BudgetRefused as e:
        print(f"STOP: {e}", file=sys.stderr)
        print(f"calls made this command: {judge.calls}", file=sys.stderr)
        return EXIT_BUDGET
    print(f"calls made this command: {judge.calls}; judge spend ${judge.spent():.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
