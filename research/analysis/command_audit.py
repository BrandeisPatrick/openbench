"""exp-07 command audit: command-level habits and log-backed completion.

Specification: research/experiments/exp-07-command-audit.md. This header is
the authoritative statement of every definition the experiment file leaves
to the code. Definitions were fixed here, in code, before any metric was
computed on the corpus. Round 2 (2026-11-11, still before any metric was
computed) implements the spec's "Amendments before freeze" 1-8: test
outcome read from runner output, stashed spans and tree_revert in U,
edit:source_new, M10 on line ranges, class `scratch` and /tmp scripts in
M7, P1 on its count thresholds only, the narrowed test-like rule, and
model habit requiring unadjusted p_cell < 0.05.

Blinding
--------
The coding rules below were written while reading `exec` commands and
outputs of the DEVELOPMENT SUBSET only: the earliest repeat (by the
timestamp suffix of run_id) of each (model, task) cell among runs.csv rows
with included=1 (36 runs). grade.json and the `resolved` column were not
consulted while writing rules. On the development subset only
instrument-coverage numbers were computed (`--dev-coverage`: share of
segments classed `other`, unresolvable existing/new cases, parse failures,
and in round 2 the count of test segments whose outcome is unknown,
command-not-found segments, and paths coded edit:source_new).
Hand-label validation samples (`--make-label-sheets`) come only from
repeats 2 and 3.

Run selection
-------------
research/corpus/runs.csv (manifest.load_runs; manifest.py is the only place
that reads run directories' metadata), rows with included=1 on the four
verified tasks (convergence.VERIFIED). Repeat index 1..3 = order of the
run_id timestamp suffix within the cell. Set S = the three sympy tasks
(81 runs; all statistics and decision rules); set P = pytest-5262 (27 runs,
split by stale_image, never pooled into S). Every cell must have exactly
3 runs (an error otherwise). convergence.load_cells is not reused because it
opens every transcript; this module opens only the runs a mode needs.

Channels: `exec` records (command, exit_code, output) in file order,
`final.exit_reason` (run.json exit_reason if no final record),
workspace.patch, datasets/tasks/<task>/gold.patch and test.patch.

1. Shell segmentation
---------------------
A command is split into ordered segments on `&&`, `||`, `;`, `|`, `|&`,
background `&` and newlines that are outside single/double/ANSI-C quotes,
outside `$( )` and backticks, and outside heredoc bodies. A heredoc body
(`<<WORD`, `<<-WORD`, quoted or not) is attached to the segment that holds
its operator; the body ends at the first line equal to WORD (trailing
whitespace ignored; leading tabs stripped for `<<-`). An unterminated
heredoc takes the rest of the command and counts as a parse failure; so does
an unclosed quote. Subshell parentheses and `{ }` are dropped (their
contents are segments). Shell control words (`if/then/else/elif/fi`,
`for/while/until ... do/done`, `case/esac`, `!`, `time`) are not segments;
a `for x in ...` header is dropped, its body segments are kept. Comment
lines are dropped. `bash -c STR` / `sh -c STR` are replaced by the segments
of STR. Leading wrappers are stripped before classification: VAR=value
assignments, `env`, `timeout [opts] N`, `nice`, `nohup`, `stdbuf`, `sudo`,
`exec`, `command` (not `command -v`), `xargs [opts]`.
Pipeline filters: a stage after `|` whose program is a text filter (head,
tail, grep, sort, uniq, cut, tr, wc, sed, awk, cat, nl, less, more, column,
jq, fold, tee without a /repo target) and that names no file operand only
filters the previous stage's output; it is dropped (not a segment).
Working directory: every exec record starts in /repo (the harness default;
records do not share a shell). `cd DIR` changes the directory for the
following segments of the same record. Relative paths resolve against it.
Paths are normalized; a path is a repo path iff it lies under /repo, and is
then stored relative to /repo. /tmp, /dev/null and every other path outside
/repo are never edits. Paths containing `$`, `*`, `?`, `~` or backquotes
are unresolvable (counted, never edits); paths under __pycache__ /
.pytest_cache and *.pyc are ignored.
A segment whose program the record's output reports as `command not found`
is classed `other` and has no effect (e.g. `apply_patch` is not installed).

2. Segment classes (one per segment)
------------------------------------
done      echo/printf whose arguments contain OPENBENCH_DONE.
edit      the segment writes at least one repo path:
            redirection targets of `>`, `>>`, `&>`, `N>` (not `>&N` dups);
            `tee` operands; `sed -i` / `perl -i` file operands; `cp`/`mv`
            destination (a destination ending in `/` or `.` receives the
            source basename; `mv` also deletes its source); `rm` operands;
            `touch` operands; `patch`, `git apply` (targets from the diff
            text when it is a heredoc or a file whose content was written
            earlier in this run by a heredoc, else from `patching file X`
            lines in the output, else unresolved); `apply_patch` heredocs
            (`*** Add/Update/Delete File:` lines); Python run as heredoc,
            `-c`, or as a script whose content was written earlier in this
            run by a heredoc, when the code writes a repo path (see 3).
            `patch --dry-run`, `git apply --check/--stat/--numstat` are not
            edits (classed other / vcs).
test      pytest/py.test, tox, nox, `bin/test`, `bin/doctest` (any path or
          via python), `python -m pytest|unittest|tox|doctest`, or Python
          code (heredoc, -c, known script) that calls a test runner
          (pytest.main, sympy.test, sympy.doctest, sympy...runtests test /
          doctest, unittest.main, or subprocess with pytest).
run       any other python/python3/pythonX.Y invocation (heredoc, -c, -m
          other than pip, script), except `--version`/`-V` (setup).
scratch   writes a file outside /repo (redirection, tee, cp/mv destination,
          touch, Python write) and is not edit, test or run; /dev/* and
          /proc/* are not files. Outside writes of test/run segments are
          still recorded (they count for M7).
read      cat, head, tail, sed (without -i), nl, wc, less, more, awk, diff,
          cmp, xxd, od, strings with at least one file operand.
search    grep/egrep/fgrep/rg/ag/ack, find, ls, tree, locate, `git grep`,
          `git ls-files`.
vcs       every other git subcommand (status, diff, log, show, stash,
          checkout, restore, add, commit, reset, apply --check, ...).
          Flag tree_revert: `git checkout` with `--`, `.`, `-f`/`--force`;
          `git restore` unless it is --staged only; `git reset --hard`;
          `git stash drop|clear`; `git clean -f...`. `git checkout BRANCH`
          is not a revert. Stashed span: from `git stash` / `stash push` /
          `stash save` to the next `git stash pop|apply`; a span never
          closed runs to the end of the log.
setup     pip/pip3/uv/conda, `python -m pip`, cd, pushd/popd, export,
          unset, source/., alias, set, ulimit, mkdir, chmod, chown, which,
          type, `command -v`, pwd, `python --version`.
other     everything else (echo/printf without the marker, true, sleep,
          read programs without file operands, unknown programs).
A record's classes = the set of its segments' classes (its flags). Primary
class = first present in done > edit > test > run > scratch > read >
search > vcs > setup > other; a record with no segments is `other`. A
segment holding several of these takes the first in the same order.

Test outcome (per test segment; the record's whole output is read, so all
test segments of one record share the runner evidence):
  fail     a summary reports failed / error(s) / exceptions (pytest summary
           line `N failed, M passed in Ts`, sympy `tests finished: ...`,
           unittest `FAILED (...)`), or `DO *NOT* COMMIT!`;
  pass     otherwise, a summary with at least one passed test (pytest,
           sympy `tests finished: N passed`, unittest `Ran N tests` + OK);
  fail     otherwise, a collection error (`ERROR collecting`, `errors during
           collection`), `ImportError while loading conftest`,
           `INTERNALERROR`, `Interrupted:`, a pytest usage error (`ERROR: `,
           `error: unrecognized arguments|ambiguous option|argument`), a
           verbose per-test `::name FAILED|ERROR` marker, a Python
           traceback (header or `File "...", line N` frame) or an output
           whose last non-empty line is `XxxError...`/`XxxException...` (a
           summary wins over all of these);
  exit code   otherwise, only if the segment is the record's last raw
           segment and its output is not piped (0 -> pass, else fail);
  unknown  otherwise.

3. Python write extraction (regular expressions over the code)
---------------------------------------------------------------
Names are bound by `n = 'lit'`, `n = Path('lit')`, `n = os.path.join('a',
'b')`, `n = Path(m)`. Write targets: `open(E, MODE)` / `io.open` /
`codecs.open` with MODE containing w, a, x or +; `E.open('w'...)`;
`E.write_text(`, `E.write_bytes(`; `shutil.copy/copy2/copyfile/move` and
`os.rename/replace` destinations (move/rename also delete the source);
`os.remove/unlink`. E is a string literal, `Path('lit')`, or a bound name;
`os.devnull` is /dev/null. A write whose target cannot be resolved falls
back to every repo path literal passed to open()/Path() in the code; if
there is none the write is counted as unresolved and is not an edit.
Operation kind: `modify` if the code also reads the same path
(open without write mode, read_text, read_bytes), else `full`.

4. Existing versus new (per repo path written in the run)
---------------------------------------------------------
In order, first match wins:
  a. workspace.patch shows the path modified or deleted -> existing;
     `new file mode` -> new.
  b. gold.patch or test.patch lists the path as modified or deleted ->
     existing (a reference entry with `new file mode` is not evidence).
  c. an earlier segment (before the run's first write to the path) read it
     with a read or search program naming it as an operand, in a record
     whose output does not contain "No such file" -> existing.
  d. the run's first write operation on the path is a full write (`>`,
     tee, cp/mv destination, touch, apply_patch Add File, a diff creating
     the file, Python write without reading it) -> new.
  e. otherwise `unknown` (counted and reported).
Test-like: basename matches test_*.py, *_test.py or conftest.py, or a
directory component is test or tests, or the first component is testing
(sympy/testing/ is not test-like). Package root: sympy/ for the sympy tasks,
src/ for pytest. Sub-kind: existing & test-like -> existing_test; new &
test-like -> new_test; existing -> source; new, not test-like, a .py file
under the package root and marked `new file mode` in workspace.patch ->
source_new (so leftover *.backup / *.patch files stay scratch);
other new -> scratch; unknown -> unknown. An edit segment with no
resolvable target has sub-kind unknown. `unknown` edits are never a
change. A record has flag edit:<sub-kind> for every sub-kind among
its written paths.

5. Run-level metrics (records = exec records in file order)
-----------------------------------------------------------
N = records whose primary class is not done; n = |N|. Shares are over N.
M1  n_cmds              n; analysed as ln(n) (ln 0 taken as 0).
M2  first_edit_frac     (1-based index in N of the first record with flag
                        edit:source or edit:source_new - 1) / n; 1.0 if none
                        or n = 0.
M3  early_edit_share    share of the first min(10, n) records of N whose
                        primary class is edit; 0 if n = 0.
M4  test_share          share of N with a test flag.
M5  exec_share          share of N with a test or run flag.
M6  wrote_new_test      1 if any new_test path was written.
M7  wrote_scratch_script 1 if a .py path that is edit:scratch, or written
                        outside /repo by any segment (/tmp counts), is
                        executed by a later segment (python PATH, python -m
                        pytest PATH, pytest PATH, ./PATH).
M8  repeat_cmd_share    share of N whose whitespace-normalized command
                        equals that of an earlier record in N.
M9  noop_retest_share   of N records with a test flag, share whose command
                        equals an earlier test record's with no edit-flagged
                        record strictly between them and no edit flag on
                        the record itself; 0 if no tests.
M10 reread_share        of N records with a read flag, share in which some
                        read segment is a re-read. Per path, the lines shown
                        since the path's last edit are kept: `all` (cat, nl,
                        less, more), or ranges (`sed -n 'a,bp'` / `'ap'`
                        with one such range, `head -n N` / `head -N` /
                        default head = 1..N). A ranged read is a re-read if
                        at least half its lines were shown (or the whole
                        file was); a whole-file read only if the whole file
                        was shown; an unknown range (tail, wc, awk, sed with
                        patterns, head -c) only if the identical segment
                        text was seen since the last edit. Edits of the path
                        reset its state. 0 if no reads.
M11 search_miss_share   of N records with a search flag, share whose output
                        is empty (after strip) or exit code is non-zero;
                        0 if no searches.
M12 extra_files         paths in workspace.patch (incl. deletions) not in
                        gold.patch.
M13 patch_lines         added + removed lines in workspace.patch (counted
                        inside hunks); analysed as ln(1 + x).
U   unsupported_done    exit_reason == completed only (else empty). A
                        change = a segment writing an edit:source or
                        edit:source_new path, or a tree_revert. Candidate
                        tests = test segments after the last change (segment
                        order, any record incl. done records) and outside
                        stashed spans. U = 0 if a candidate has outcome
                        pass; if there are candidates and all are unknown:
                        U empty and U_unknown = 1; else U = 1.
                        U_sensitivity = U, with U_unknown runs scored 1.
                        U_lenient = 0 if U = 0 or a later non-stashed run
                        segment is its record's last raw segment with exit
                        code 0; else 1 (empty for U_unknown runs without
                        such a run). No edit:source/source_new segment ->
                        no_edit = 1 and U, U_lenient empty.
Descriptive: gold_file_hit (every path in gold.patch is in workspace.patch),
edit_jaccard_gold (convergence.jac over convergence.parse_patch edit sets of
workspace vs gold), edited_existing_test (any existing_test edit),
error_share (share of N with non-zero exit), leftover_new_files (paths with
`new file mode` in workspace.patch), cmd_not_found (segments the output
reports as `PROG: command not found`; names and counts in
cmd_not_found_progs), malformed_cmd (records with an unclosed quote or an
unterminated / malformed heredoc).

6. Analyses (set S unless stated)
---------------------------------
Metric values enter analyses after the transforms above (M1 ln, M13 ln1p).
A1  Balanced two-way layout 9 models x 3 tasks x 3 repeats: SS_model,
    SS_task, SS_model:task, SS_repeat (within cell) as shares of SS_total.
    p_main: permute which model each cell is, within task; statistic
    MS_model / MS_model:task. p_cell: permute runs within task; statistic
    MS_cells-within-task / MS_repeat, MS_cells-within-task =
    (SS_model + SS_model:task) / (T(M-1)). 10,000 draws, seed SEED + metric
    index (p_main) and SEED + 100 + metric index (p_cell);
    p = (1 + #{perm >= obs}) / (1 + draws), ties within 1e-12 count.
    A zero denominator gives +inf when the numerator is > 0, else 0.
    A metric with SS_total = 0 is reported constant, p = None, label
    indeterminate. Holm adjustment over the metrics with a p value, for
    p_main and for p_cell separately.
    Sensitivity (Caveats): on completed runs of S only, which is unbalanced,
    marginal shares of model, task, cell and within-cell (repeat) sums of
    squares; no permutation tests.
A2  Kendall's W of the nine model cell means, raters = three tasks,
    average ranks for ties with the tie-corrected denominator; None if the
    denominator is 0.
A3  n_cmds (raw and ln) of resolved vs unresolved: pooled over S, within
    task, within each mixed-outcome cell (1 or 2 of 3 resolved).
A4  Completed runs in S: U x resolved table (no_edit runs reported
    separately), per-model U counts with 95% Clopper-Pearson intervals
    (exact binomial tail inversion by bisection); same for U_lenient and
    for the sensitivity row U_sensitivity; U_unknown counted separately.
A5  Nearest centroid (Euclidean) on M1-M13 z-scored over S (labels not
    used for scaling; zero-sd features dropped). Leave-one-run-out and
    leave-one-task-out accuracy; ties go to the earlier model in
    convergence.ORDER. Null: 1,000 permutations of model labels within task
    (seed SEED + 500). Identification iff leave-one-task-out accuracy >
    95th percentile of its null.
A6  Set P, by stale_image (no model comparison): hit_runner_error (a test or
    run record output contains manifest.STALE_MARKER); env_repair (after
    the first runner error: pip install, a PYTHONPATH/PYTEST_* env prefix,
    or an edit of a repo path that is neither in gold.patch nor test-like);
    verified_other_means (completed, U_sensitivity = 1 and U_lenient = 0);
    done_without_passing_check (completed and U_sensitivity = 1);
    done_with_passing_test (completed and U = 0).
A7  Per lineage (convergence.LINEAGES), per metric: mean over S runs by
    generation and the delta of each link; links whose hosts differ
    (runs.csv host column) are labelled host-crossing.

Decision rules (fixed): model habit iff Holm-adjusted p_main < 0.05,
unadjusted p_cell < 0.05, W >= 0.6 and model share > repeat share; task-dependent model habit iff not a
model habit and Holm-adjusted p_cell < 0.05; repeat noise iff unadjusted
p_cell >= 0.05; otherwise indeterminate.

Predictions (groups with fewer than 5 runs -> not testable):
P1  scored on its count thresholds only: for every sympy task,
    kimi-k2-thinking and v3.2 have (M6 or M7) in >= 2 of 3 runs, and gpt-5.5
    in <= 1 of 3.
P2  pooled mean ln(n) unresolved - resolved > 0, and the mean over
    mixed-outcome cells of the within-cell difference is smaller than the
    pooled difference (shrinks or reverses). Needs >= 5 runs per outcome
    pooled and within mixed cells.
P3  share of runs with M8, M9 or M10 > 0 is >= 0.79, and |rate resolved -
    rate unresolved| <= 0.15.
P4  gold_file_hit rate >= 0.90 among resolved and lower among unresolved.
P5  mean early_edit_share lower and mean test_share higher in resolved
    runs, pooled and in every task where both groups have >= 5 runs.
P6  among completed runs with a defined U (no_edit and U_unknown
    excluded): U rate > 0 among resolved and U rate among unresolved > U
    rate among resolved.

Validation sheets (`--make-label-sheets`, seed SEED): V1 draws 40 exec
records per sympy task from repeats 2 and 3 (uniformly over the pooled
records of the task's 18 runs); V2 draws 30 completed runs from repeats 2
and 3 of set S (all of them if fewer). `--score-labels` computes Cohen's
kappa on the primary class (V1) and on unsupported_done (V2, rows where
the rule's U is defined). Until both exist every result is labelled
"unvalidated instrument".
"""

from __future__ import annotations

import csv
import json
import math
import os
import posixpath
import random
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import convergence as cv  # noqa: E402  (parse_patch, jac, VERIFIED, LINEAGES, ORDER)
import manifest  # noqa: E402  (run selection; see research/corpus/runs.csv)

SEED = 20261111
DRAWS = 10_000
A5_DRAWS = 1_000
DONE_MARKER = "OPENBENCH_DONE"
REPO = "/repo"
OUT_DIR = manifest.ROOT / "research" / "results" / "exp-07-command-audit"
SYMPY_TASKS = [t for t in cv.VERIFIED if t.startswith("sympy__")]
PYTEST_TASK = "pytest-dev__pytest-5262"

CLASS_ORDER = ["done", "edit", "test", "run", "scratch", "read", "search", "vcs", "setup",
               "other"]
SUBKINDS = ["source", "source_new", "existing_test", "new_test", "scratch", "unknown"]

# (id, key, transform for analyses)
METRICS = [
    ("M1", "n_cmds", "log"),
    ("M2", "first_edit_frac", None),
    ("M3", "early_edit_share", None),
    ("M4", "test_share", None),
    ("M5", "exec_share", None),
    ("M6", "wrote_new_test", None),
    ("M7", "wrote_scratch_script", None),
    ("M8", "repeat_cmd_share", None),
    ("M9", "noop_retest_share", None),
    ("M10", "reread_share", None),
    ("M11", "search_miss_share", None),
    ("M12", "extra_files", None),
    ("M13", "patch_lines", "log1p"),
]
DESCRIPTIVE = ["gold_file_hit", "edit_jaccard_gold", "edited_existing_test",
               "error_share", "leftover_new_files", "cmd_not_found", "malformed_cmd"]

# --------------------------------------------------------------------------
# 1. Shell segmentation
# --------------------------------------------------------------------------


def _read_heredoc_word(cmd: str, j: int):
    """Parse a heredoc delimiter word starting at j -> (word, end, ok)."""
    n = len(cmd)
    while j < n and cmd[j] in " \t":
        j += 1
    word, ok = [], True
    while j < n and cmd[j] not in " \t\n;&|<>()":
        c = cmd[j]
        if c in "'\"":
            k = cmd.find(c, j + 1)
            if k < 0:
                return "".join(word) + cmd[j + 1:], n, False
            inner = cmd[j + 1:k]
            if "\n" in inner:
                ok = False
            word.append(inner)
            j = k + 1
        elif c == "\\" and j + 1 < n:
            word.append(cmd[j + 1])
            j += 2
        else:
            word.append(c)
            j += 1
    return "".join(word), j, ok


def split_segments(cmd: str):
    """Split a shell command into segments.

    Returns (segments, failures) where each segment is a dict with keys
    text (the segment without heredoc bodies), body (heredoc body text or
    None) and sep (the separator before it: None, '&&', '||', ';', '|',
    '&', '\\n').
    """
    segs: list[dict] = []
    failures = 0
    buf: list[str] = []
    bodies: dict[int, list[str]] = defaultdict(list)
    pending: list[tuple[str, bool, int]] = []
    sep = None
    quote = None
    depth = 0  # $( ... ) nesting
    backtick = False
    i, n = 0, len(cmd)

    def flush(new_sep):
        nonlocal buf, sep
        text = "".join(buf).strip()
        segs.append({"text": text, "body": None, "sep": sep})
        buf = []
        sep = new_sep

    while i < n:
        c = cmd[i]
        if quote == "'":
            buf.append(c)
            if c == "'":
                quote = None
            i += 1
            continue
        if quote == '"':
            buf.append(c)
            if c == "\\" and i + 1 < n:
                buf.append(cmd[i + 1])
                i += 2
                continue
            if c == '"':
                quote = None
            i += 1
            continue
        if quote == "$'":
            buf.append(c)
            if c == "\\" and i + 1 < n:
                buf.append(cmd[i + 1])
                i += 2
                continue
            if c == "'":
                quote = None
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            if cmd[i + 1] == "\n":
                buf.append(" ")
            else:
                buf.append(cmd[i:i + 2])
            i += 2
            continue
        if c == "$" and cmd.startswith("$'", i):
            quote = "$'"
            buf.append("$'")
            i += 2
            continue
        if c in "'\"":
            quote = c
            buf.append(c)
            i += 1
            continue
        if c == "$" and cmd.startswith("$(", i):
            depth += 1
            buf.append("$(")
            i += 2
            continue
        if c == "`":
            backtick = not backtick
            buf.append(c)
            i += 1
            continue
        if depth > 0 or backtick:
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            buf.append(c)
            i += 1
            continue
        if c == "#" and not "".join(buf).strip():
            # comment line: skip to newline
            k = cmd.find("\n", i)
            i = n if k < 0 else k
            continue
        if cmd.startswith("<<", i) and not cmd.startswith("<<<", i):
            j = i + 2
            strip = False
            if j < n and cmd[j] == "-":
                strip, j = True, j + 1
            word, end, ok = _read_heredoc_word(cmd, j)
            bad = not ok or not word
            if bad:
                failures += 1
            pending.append((word, strip, len(segs), bad))
            buf.append(cmd[i:end])
            i = end
            continue
        if c == "\n":
            flush("\n")
            i += 1
            if pending:
                for word, strip, idx, bad in pending:
                    lines = []
                    found = False
                    while i < n:
                        k = cmd.find("\n", i)
                        line = cmd[i:] if k < 0 else cmd[i:k]
                        i = n if k < 0 else k + 1
                        test = line.lstrip("\t") if strip else line
                        if word and test.rstrip() == word:
                            found = True
                            break
                        lines.append(line)
                    if not found and not bad:
                        failures += 1
                    bodies[idx].append("\n".join(lines) + ("\n" if lines else ""))
                pending = []
            continue
        prev = buf[-1][-1:] if buf else ""
        if c == "&":
            if cmd.startswith("&&", i):
                flush("&&")
                i += 2
                continue
            if prev in "<>" or cmd.startswith("&>", i):
                buf.append(c)
                i += 1
                continue
            flush("&")
            i += 1
            continue
        if c == "|":
            if cmd.startswith("||", i):
                flush("||")
                i += 2
                continue
            if prev == ">":
                buf.append(c)
                i += 1
                continue
            flush("|")
            i += 2 if cmd.startswith("|&", i) else 1
            continue
        if c == ";":
            flush(";")
            i += 2 if cmd.startswith(";;", i) else 1
            continue
        if c == "(":
            if not "".join(buf).strip():
                i += 1
                continue
            buf.append(c)
            i += 1
            continue
        if c == ")":
            text = "".join(buf)
            if text.count("(") > text.count(")"):
                buf.append(c)
            else:
                flush(sep)
            i += 1
            continue
        buf.append(c)
        i += 1
    if quote or depth or backtick:
        failures += 1
    flush(None)
    if pending:
        failures += 1
        for _, _, idx, _ in pending:
            bodies[idx].append("")
    out = []
    for idx, s in enumerate(segs):
        if idx in bodies:
            s["body"] = "".join(bodies[idx])
        if s["text"] or s["body"]:
            out.append(s)
    # separator of a dropped empty segment carries forward
    return out, failures


def tokenize(s: str):
    """Tokenize one segment -> (tokens, ok). Token = (text, kind) with kind
    'word', 'qword' (contains quoting) or 'op' (unquoted redirection)."""
    toks: list[tuple[str, str]] = []
    cur: list[str] = []
    quoted = have = False
    ok = True
    i, n = 0, len(s)

    def push():
        nonlocal cur, quoted, have
        if have:
            toks.append(("".join(cur), "qword" if quoted else "word"))
        cur, quoted, have = [], False, False

    while i < n:
        c = s[i]
        if c in " \t\n":
            push()
            i += 1
            continue
        if c == "\\":
            if i + 1 < n:
                if s[i + 1] != "\n":
                    cur.append(s[i + 1])
                    have = quoted = True
                i += 2
            else:
                i += 1
            continue
        if c == "'":
            k = s.find("'", i + 1)
            if k < 0:
                ok, k = False, n
            cur.append(s[i + 1:k])
            have = quoted = True
            i = k + 1
            continue
        if c == "$" and s.startswith("$'", i):
            j = i + 2
            out = []
            while j < n and s[j] != "'":
                if s[j] == "\\" and j + 1 < n:
                    e = s[j + 1]
                    out.append({"n": "\n", "t": "\t", "'": "'", "\\": "\\"}.get(e, "\\" + e))
                    j += 2
                else:
                    out.append(s[j])
                    j += 1
            if j >= n:
                ok = False
            cur.append("".join(out))
            have = quoted = True
            i = j + 1
            continue
        if c == '"':
            j = i + 1
            out = []
            while j < n and s[j] != '"':
                if s[j] == "\\" and j + 1 < n and s[j + 1] in '$`"\\\n':
                    if s[j + 1] != "\n":
                        out.append(s[j + 1])
                    j += 2
                else:
                    out.append(s[j])
                    j += 1
            if j >= n:
                ok = False
            cur.append("".join(out))
            have = quoted = True
            i = j + 1
            continue
        if c in "<>" or (c == "&" and s.startswith("&>", i)):
            fd = ""
            if have and not quoted and "".join(cur).isdigit():
                fd = "".join(cur)
                cur, have = [], False
            else:
                push()
            m = re.match(r"&>>|&>|>>|>\||>&|<<<|<<-|<<|<&|<>|>|<", s[i:])
            toks.append((fd + m.group(0), "op"))
            i += len(m.group(0))
            continue
        cur.append(c)
        have = True
        i += 1
    push()
    return toks, ok


CONTROL_PREFIX = {"do", "then", "else", "elif", "if", "while", "until", "!", "time", "{", "}"}
CONTROL_DROP = {"for", "case", "select", "function", "done", "fi", "esac", "in"}
FILTERS = {"head", "tail", "grep", "egrep", "fgrep", "rg", "sort", "uniq", "cut", "tr", "wc",
           "sed", "awk", "cat", "nl", "less", "more", "column", "jq", "fold", "tee", "xxd"}
READ_PROGS = {"cat", "head", "tail", "sed", "nl", "wc", "less", "more", "awk", "diff", "cmp",
              "xxd", "od", "strings", "bat"}
SEARCH_PROGS = {"grep", "egrep", "fgrep", "rg", "ag", "ack", "find", "ls", "tree", "locate"}
SETUP_PROGS = {"pip", "pip3", "uv", "conda", "cd", "pushd", "popd", "export", "unset", "source",
               ".", "alias", "set", "ulimit", "mkdir", "chmod", "chown", "which", "type", "pwd",
               "hash"}
PY_RE = re.compile(r"^python(\d+(\.\d+)?)?$")
TEST_CODE_RE = re.compile(
    r"\bpytest\.main\s*\(|\bsympy\.test\s*\(|\bsympy\.doctest\s*\(|runtests\s+import\b[^\n]*\b(test|doctest)\b"
    r"|runtests\.(test|doctest)\s*\(|\bunittest\.main\s*\(|subprocess[^\n]*pytest")
ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
OPT_WITH_ARG = {
    "head": {"-n", "-c"}, "tail": {"-n", "-c"}, "grep": {"-e", "-f", "-m", "-A", "-B", "-C",
                                                         "--include", "--exclude"},
    "sed": {"-e", "-f"}, "awk": {"-F", "-v", "-f"}, "wc": set(), "cat": set(), "nl": set(),
    "rg": {"-e", "-g", "-t", "-A", "-B", "-C", "-m"},
}


def _strip_wrappers(words: list[str]):
    """Strip env assignments and wrapper programs -> (words, env_names)."""
    env = []
    w = list(words)
    changed = True
    while w and changed:
        changed = False
        while w and ENV_RE.match(w[0]):
            env.append(w[0].split("=", 1)[0])
            w.pop(0)
            changed = True
        if not w:
            break
        p = w[0]
        if p == "env":
            w.pop(0)
            while w and (w[0].startswith("-") or ENV_RE.match(w[0])):
                if ENV_RE.match(w[0]):
                    env.append(w[0].split("=", 1)[0])
                if w[0] in ("-u",) and len(w) > 1:
                    w.pop(0)
                w.pop(0)
            changed = True
        elif p == "timeout":
            w.pop(0)
            while w and w[0].startswith("-"):
                if w[0] in ("-s", "-k", "--signal", "--kill-after") and len(w) > 1:
                    w.pop(0)
                w.pop(0)
            if w and re.match(r"^\d+(\.\d+)?[smhd]?$", w[0]):
                w.pop(0)
            changed = True
        elif p in ("nice", "nohup", "stdbuf", "sudo", "exec", "time"):
            w.pop(0)
            while w and w[0].startswith("-"):
                if w[0] == "-n" and len(w) > 1:
                    w.pop(0)
                w.pop(0)
            changed = True
        elif p == "command" and len(w) > 1 and w[1] not in ("-v", "-V"):
            w.pop(0)
            changed = True
        elif p == "xargs":
            w.pop(0)
            while w and w[0].startswith("-"):
                if w[0] in ("-n", "-I", "-P", "-L", "-d", "-s", "-E") and len(w) > 1:
                    w.pop(0)
                w.pop(0)
            changed = True
    return w, env


def norm_path(p: str, cwd: str):
    """-> ('repo', rel) | ('outside', abs) | ('unresolvable', p) | ('ignore', p)."""
    if not p or any(ch in p for ch in "$*?~`"):
        return ("unresolvable", p)
    full = posixpath.normpath(p if p.startswith("/") else posixpath.join(cwd, p))
    if full == REPO or full.startswith(REPO + "/"):
        rel = full[len(REPO) + 1:]
        if not rel:
            return ("outside", full)
        if "__pycache__" in rel.split("/") or ".pytest_cache" in rel.split("/") or rel.endswith(".pyc"):
            return ("ignore", rel)
        return ("repo", rel)
    return ("outside", full)


def is_test_like(rel: str) -> bool:
    parts = rel.split("/")
    base = parts[-1]
    if (base.startswith("test_") and base.endswith(".py")) or base.endswith("_test.py") \
            or base == "conftest.py":
        return True
    if len(parts) > 1 and parts[0] == "testing":
        return True
    return any(d in ("test", "tests") for d in parts[:-1])


def package_root(task_id: str | None) -> str:
    """Package root for edit:source_new: sympy/ for sympy tasks, src/ for pytest."""
    if task_id and task_id.startswith("pytest-dev__"):
        return "src/"
    return "sympy/"


# --------------------------------------------------------------------------
# 3. Python write extraction
# --------------------------------------------------------------------------

_STR = r"""[rRbBuU]?(?P<q>['"])(?P<s>[^'"\n]*)(?P=q)"""
_PATHLIKE = re.compile(r"^[^\s:]+$")


def _pathlike(s: str) -> bool:
    return bool(s) and bool(_PATHLIKE.match(s)) and not s.startswith(("http", "-")) and (
        "/" in s or re.search(r"\.[A-Za-z0-9]{1,6}$", s) is not None)


def _call_args(code: str, start: int) -> list[str]:
    """Top-level comma-separated args of the call whose '(' is at code[start]."""
    args, cur, depth, i, q = [], [], 0, start + 1, None
    while i < len(code):
        c = code[i]
        if q:
            cur.append(c)
            if c == "\\" and i + 1 < len(code):
                cur.append(code[i + 1])
                i += 2
                continue
            if c == q:
                q = None
        elif c in "'\"":
            q = c
            cur.append(c)
        elif c in "([{":
            depth += 1
            cur.append(c)
        elif c in ")]}":
            if depth == 0:
                args.append("".join(cur).strip())
                return [a for a in args if a]
            depth -= 1
            cur.append(c)
        elif c == "," and depth == 0:
            args.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
        i += 1
    args.append("".join(cur).strip())
    return [a for a in args if a]


def _py_names(code: str) -> dict[str, str]:
    names: dict[str, str] = {}
    for m in re.finditer(r"^\s*(\w+)\s*=\s*(?:pathlib\.)?Path\(\s*" + _STR + r"\s*\)", code, re.M):
        names[m.group(1)] = m.group("s")
    for m in re.finditer(r"^\s*(\w+)\s*=\s*" + _STR + r"\s*$", code, re.M):
        if _pathlike(m.group("s")):
            names[m.group(1)] = m.group("s")
    for m in re.finditer(r"^\s*(\w+)\s*=\s*os\.path\.join\(([^()\n]*)\)", code, re.M):
        parts = [p.group("s") for p in re.finditer(_STR, m.group(2))]
        if parts and len(parts) == len([a for a in m.group(2).split(",") if a.strip()]):
            names[m.group(1)] = posixpath.join(*parts)
    for m in re.finditer(r"^\s*(\w+)\s*=\s*(?:pathlib\.)?Path\(\s*(\w+)\s*\)", code, re.M):
        if m.group(2) in names:
            names[m.group(1)] = names[m.group(2)]
    return names


def _py_expr(expr: str, names: dict[str, str]):
    expr = expr.strip()
    m = re.fullmatch(_STR, expr)
    if m:
        return m.group("s")
    m = re.fullmatch(r"(?:pathlib\.)?Path\(\s*(.*?)\s*\)", expr)
    if m:
        return _py_expr(m.group(1), names)
    if expr == "os.devnull":
        return "/dev/null"
    if re.fullmatch(r"\w+", expr):
        return names.get(expr)
    return None


def py_effects(code: str):
    """-> (writes [(path, op)], reads set(path), unresolved_writes, is_test).

    Paths are returned as written in the code (not yet normalized)."""
    names = _py_names(code)
    writes: list[tuple[str | None, str]] = []
    reads: set[str] = set()
    literal_paths: list[str] = []
    for m in re.finditer(r"(?<![\w.])(?:io\.|codecs\.)?open\s*\(", code):
        args = _call_args(code, m.end() - 1)
        if not args:
            continue
        target = _py_expr(args[0], names)
        mode = "r"
        for a in args[1:]:
            mm = re.fullmatch(r"(?:mode\s*=\s*)?" + _STR, a)
            if mm:
                mode = mm.group("s")
                break
        if target:
            literal_paths.append(target)
        if any(ch in mode for ch in "wax+"):
            writes.append((target, "w"))
        elif target:
            reads.add(target)
    for m in re.finditer(r"((?:pathlib\.)?Path\([^()\n]*\)|\w+)\s*\.\s*(write_text|write_bytes|read_text|read_bytes|open)\s*\(", code):
        target = _py_expr(m.group(1), names)
        meth = m.group(2)
        if meth == "open":
            args = _call_args(code, m.end() - 1)
            mode = "r"
            if args:
                mm = re.fullmatch(r"(?:mode\s*=\s*)?" + _STR, args[0])
                mode = mm.group("s") if mm else "r"
            if any(ch in mode for ch in "wax+"):
                writes.append((target, "w"))
            elif target:
                reads.add(target)
        elif meth.startswith("write"):
            writes.append((target, "w"))
        elif target:
            reads.add(target)
        if target:
            literal_paths.append(target)
    for m in re.finditer(r"\b(shutil\.(?:copy|copy2|copyfile|move)|os\.(?:rename|replace))\s*\(", code):
        args = _call_args(code, m.end() - 1)
        if len(args) >= 2:
            writes.append((_py_expr(args[1], names), "full"))
            if m.group(1).endswith(("move", "rename", "replace")):
                writes.append((_py_expr(args[0], names), "delete"))
    for m in re.finditer(r"\bos\.(?:remove|unlink)\s*\(", code):
        args = _call_args(code, m.end() - 1)
        if args:
            writes.append((_py_expr(args[0], names), "delete"))
    out: list[tuple[str, str]] = []
    unresolved = 0
    for target, op in writes:
        if target is None:
            fallback = [p for p in literal_paths if _pathlike(p)]
            if fallback:
                out.extend((p, "modify") for p in fallback)
            else:
                unresolved += 1
            continue
        if op == "w":
            op = "modify" if target in reads else "full"
        out.append((target, op))
    return out, reads, unresolved, bool(TEST_CODE_RE.search(code))


# --------------------------------------------------------------------------
# Patch helpers
# --------------------------------------------------------------------------

def patch_status_text(text: str) -> dict[str, str]:
    """path -> 'new' | 'deleted' | 'modified' for every file in a diff text."""
    out: dict[str, str] = {}
    cur = None
    minus = None
    for line in text.splitlines():
        m = re.match(r"^diff --git a/(\S+) b/(\S+)", line)
        if m:
            cur = m.group(2)
            out[cur] = "modified"
            minus = None
            continue
        if line.startswith("new file mode") and cur:
            out[cur] = "new"
        elif line.startswith("deleted file mode") and cur:
            out[cur] = "deleted"
        elif line.startswith("--- "):
            minus = line[4:].split("\t")[0].strip()
        elif line.startswith("+++ ") and minus is not None:
            plus = line[4:].split("\t")[0].strip()
            if plus == "/dev/null":
                p = minus[2:] if minus.startswith(("a/", "b/")) else minus
                out.setdefault(p, "deleted")
            else:
                p = plus[2:] if plus.startswith(("a/", "b/")) else plus
                out.setdefault(p, "new" if minus == "/dev/null" else "modified")
            minus = None
    return out


def patch_status(path: str) -> dict[str, str]:
    if not os.path.isfile(path):
        return {}
    with open(path, errors="replace") as f:
        return patch_status_text(f.read())


def patch_line_count(path: str) -> int:
    """Added + removed lines, counted inside hunks by the hunk headers."""
    if not os.path.isfile(path):
        return 0
    total = 0
    old_left = new_left = 0
    with open(path, errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if old_left > 0 or new_left > 0:
                if line.startswith("+"):
                    total += 1
                    new_left -= 1
                elif line.startswith("-"):
                    total += 1
                    old_left -= 1
                elif line.startswith("\\"):
                    pass
                else:
                    old_left -= 1
                    new_left -= 1
                continue
            m = re.match(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@", line)
            if m:
                old_left = int(m.group(1)) if m.group(1) is not None else 1
                new_left = int(m.group(2)) if m.group(2) is not None else 1
    return total


def _diff_targets(text: str):
    """Targets [(path, op)] of a unified diff / apply_patch text (paths relative;
    a leading a/ or b/ is stripped, as -p1 / git apply do)."""
    out = []
    if "*** Begin Patch" in text or re.search(r"^\*\*\* (Add|Update|Delete) File:", text, re.M):
        for m in re.finditer(r"^\*\*\* (Add|Update|Delete) File:\s*(\S+)|^\*\*\* Move to:\s*(\S+)",
                             text, re.M):
            if m.group(3):
                out.append((m.group(3), "full"))
            else:
                op = {"Add": "full", "Update": "modify", "Delete": "delete"}[m.group(1)]
                out.append((m.group(2), op))
        return out
    for p, st in patch_status_text(text).items():
        out.append((p, {"new": "full", "deleted": "delete"}.get(st, "modify")))
    return out


# --------------------------------------------------------------------------
# 2. Segment classification
# --------------------------------------------------------------------------

def _operands(prog: str, args: list[str]) -> list[str]:
    """File operands of a read/search program (best effort)."""
    with_arg = OPT_WITH_ARG.get(prog, set())
    ops, i, script_taken = [], 0, False
    explicit_script = prog in ("sed", "awk") and any(a in ("-e", "-f") for a in args)
    grep_pattern_taken = prog in ("grep", "egrep", "fgrep", "rg") and any(
        a in ("-e", "-f") for a in args)
    while i < len(args):
        a = args[i]
        if a == "--":
            ops.extend(args[i + 1:])
            break
        if a.startswith("-") and a != "-":
            if a in with_arg:
                i += 1
            i += 1
            continue
        if prog in ("sed", "awk") and not explicit_script and not script_taken:
            script_taken = True
        elif prog in ("grep", "egrep", "fgrep", "rg") and not grep_pattern_taken:
            grep_pattern_taken = True
        elif prog == "find":
            pass
        else:
            ops.append(a)
        i += 1
    if prog == "find":
        ops = []
        for a in args:
            if a.startswith("-") or a in ("(", ")", "!"):
                break
            ops.append(a)
    return ops


class Ctx:
    """Per-run state shared across records: heredoc-written file contents."""

    def __init__(self):
        self.files: dict[str, str] = {}  # absolute path -> content written by heredoc
        self.parse_failures = 0
        self.unresolvable_writes = 0
        self.py_unresolved = 0


def classify_segment(seg: dict, cwd: str, output: str, ctx: Ctx, after_pipe: bool):
    """Classify one segment.

    -> dict(cls, writes [(rel|None, op)], reads [rel], evidence [rel], execs [rel],
            env [names], prog, cwd (after the segment)) or None if dropped."""
    toks, ok = tokenize(seg["text"])
    if not ok:
        ctx.parse_failures += 1
    words: list[str] = []
    redirs: list[tuple[str, str]] = []  # (op, target)
    stdin_file = None
    i = 0
    while i < len(toks):
        t, kind = toks[i]
        if kind == "op":
            op = t.lstrip("0123456789")
            nxt = toks[i + 1][0] if i + 1 < len(toks) else ""
            if op in (">&", "<&"):
                i += 2 if re.fullmatch(r"\d+|-", nxt or "") else 1
                if not re.fullmatch(r"\d+|-", nxt or "") and nxt:
                    redirs.append((">", nxt))
                continue
            if op in ("<<", "<<-", "<<<"):
                i += 2
                continue
            if op == "<":
                stdin_file = nxt
                i += 2
                continue
            if op in (">", ">>", "&>", "&>>", ">|", "<>"):
                redirs.append((op, nxt))
                i += 2
                continue
            i += 1
            continue
        words.append(t)
        i += 1
    # control words
    while words and words[0] in CONTROL_PREFIX:
        words.pop(0)
    while words and words[-1] == "}":
        words.pop()
    if words and words[0] in CONTROL_DROP:
        return None
    via_xargs = "xargs" in words[:3]
    words, env = _strip_wrappers(words)
    res = {"cls": "other", "writes": [], "reads": [], "evidence": [], "execs": [],
           "env": env, "prog": "", "cwd": cwd, "test_code": False, "scratch_writes": [],
           "read_ranges": [], "vcs": None, "not_found": False}
    body = seg.get("body")
    if not words and not redirs:
        return None
    prog_path = words[0] if words else ""
    prog = posixpath.basename(prog_path)
    res["prog"] = prog
    args = words[1:]
    # bash -c / sh -c are expanded by the caller
    if prog and re.search(rf"(^|\n|\s){re.escape(prog_path)}: (command )?not found", output):
        res["cls"] = "other"
        res["not_found"] = True
        return res
    # pipeline filters
    if after_pipe and prog in FILTERS and not redirs and not via_xargs:
        if prog == "tee":
            tgt = [a for a in args if not a.startswith("-")]
            if not any(norm_path(a, cwd)[0] == "repo" for a in tgt):
                return None
        elif not _operands(prog, args):
            return None

    writes: list[tuple[str | None, str]] = []

    def add_write(p, op):
        kind, val = norm_path(p, cwd)
        if kind == "repo":
            writes.append((val, op))
        elif kind == "outside":
            if op != "delete" and not val.startswith(("/dev/", "/proc/")) and val != "/dev":
                res["scratch_writes"].append(val)
        elif kind == "unresolvable":
            ctx.unresolvable_writes += 1

    def add_exec(p):
        k, v = norm_path(p, cwd)
        if k in ("repo", "outside"):
            res["execs"].append(v)

    # redirections
    for op, tgt in redirs:
        if op == "<>":
            continue
        add_write(tgt, "append" if ">>" in op else "full")
        k, v = norm_path(tgt, cwd)
        if k in ("outside", "repo") and body is not None:
            full = v if k == "outside" else posixpath.join(REPO, v)
            if ">>" in op:
                ctx.files[full] = ctx.files.get(full, "") + body
            else:
                ctx.files[full] = body

    is_py = bool(PY_RE.match(prog))
    cls = None
    test_code = False
    if prog in ("echo", "printf") and any(DONE_MARKER in a for a in args):
        res["cls"] = "done"
        return res
    if prog == "tee":
        app = any(a in ("-a", "--append") for a in args)
        for a in args:
            if not a.startswith("-"):
                add_write(a, "append" if app else "full")
                if body is not None:
                    k, v = norm_path(a, cwd)
                    if k in ("outside", "repo"):
                        ctx.files[v if k == "outside" else posixpath.join(REPO, v)] = body
    elif (prog == "sed" and any(a.startswith(("-i", "--in-place")) for a in args)) or (
            prog == "perl" and any(a.startswith("-") and not a.startswith("--") and "i" in a[1:]
                                   for a in args)):
        j, script_seen, files = 0, any(a in ("-e", "-f") for a in args), []
        while j < len(args):
            a = args[j]
            if a in ("-e", "-f"):
                j += 2
                continue
            if a == "-i" and prog == "sed" and j + 1 < len(args) and args[j + 1] == "":
                j += 2
                continue
            if a.startswith("-"):
                j += 1
                continue
            if not script_seen:
                script_seen = True
            else:
                files.append(a)
            j += 1
        for f in files:
            add_write(f, "modify")
    elif prog in ("cp", "mv"):
        ops = [a for a in args if not a.startswith("-")]
        if len(ops) >= 2:
            dest = ops[-1]
            for src in ops[:-1]:
                d = posixpath.join(dest, posixpath.basename(src)) if dest.endswith("/") or dest == "." else dest
                add_write(d, "full")
                if prog == "mv":
                    add_write(src, "delete")
                k, v = norm_path(src, cwd)
                full_src = v if k == "outside" else posixpath.join(REPO, v)
                kd, vd = norm_path(d, cwd)
                if k in ("outside", "repo") and kd in ("outside", "repo") and full_src in ctx.files:
                    ctx.files[vd if kd == "outside" else posixpath.join(REPO, vd)] = ctx.files[full_src]
                if k == "repo":
                    res["evidence"].append(v)
    elif prog == "rm":
        for a in args:
            if not a.startswith("-"):
                add_write(a, "delete")
    elif prog == "touch":
        for a in args:
            if not a.startswith("-"):
                add_write(a, "full")
    elif prog == "apply_patch":
        for p, op in _diff_targets(body or " ".join(args)):
            add_write(p, op)
        if not writes:
            ctx.unresolvable_writes += 1
            writes.append((None, "modify"))
    elif prog == "patch" or (prog == "git" and _git_sub(args)[0] == "apply"):
        is_git = prog == "git"
        sub_args = _git_sub(args)[1] if is_git else args
        if any(a in ("--dry-run", "--check", "--stat", "--numstat", "--summary") for a in sub_args):
            cls = "vcs" if is_git else "other"
        else:
            pfile = None
            j = 0
            while j < len(sub_args):
                a = sub_args[j]
                if a in ("-p", "-d", "--directory") and j + 1 < len(sub_args):
                    j += 1
                elif a in ("-i", "--input") and j + 1 < len(sub_args):
                    pfile = sub_args[j + 1]
                    j += 1
                elif not a.startswith("-"):
                    pfile = a
                j += 1
            pfile = pfile or stdin_file
            text = body
            if text is None and pfile:
                k, v = norm_path(pfile, cwd)
                text = ctx.files.get(v if k == "outside" else posixpath.join(REPO, v))
            targets = []
            if not is_git:
                targets = [(m.group(1), "modify") for m in
                           re.finditer(r"^patching file '?([^'\n]+?)'?$", output, re.M)]
            if not targets and text:
                targets = _diff_targets(text)
            for p, op in targets:
                add_write(p, op)
            if not targets:
                ctx.unresolvable_writes += 1
                writes.append((None, "modify"))
    elif is_py:
        code, script = None, None
        j = 0
        mod = None
        version = False
        while j < len(args):
            a = args[j]
            if a == "-c" and j + 1 < len(args):
                code = args[j + 1]
                break
            if a == "-m" and j + 1 < len(args):
                mod = args[j + 1]
                break
            if a in ("-V", "--version"):
                version = True
                break
            if a in ("-W", "-X") and j + 1 < len(args):
                j += 2
                continue
            if a == "-":
                code = body
                break
            if a.startswith("-"):
                j += 1
                continue
            script = a
            break
        if code is None and script is None and mod is None and not version:
            code = body
        if version:
            cls = "setup"
        elif mod is not None:
            mod_args = args[j + 2:]
            if mod in ("pytest", "py.test", "unittest", "tox", "doctest", "nose", "nox"):
                cls = "test"
            elif mod == "pip":
                cls = "setup"
            else:
                cls = "run"
            for a in mod_args:
                if a.split("::")[0].endswith(".py"):
                    add_exec(a.split("::")[0])
        else:
            if script is not None:
                k, v = norm_path(script, cwd)
                add_exec(script)
                full = v if k == "outside" else posixpath.join(REPO, v) if k == "repo" else None
                if posixpath.basename(script) in ("test", "doctest") and "bin" in script:
                    cls = "test"
                elif full and full in ctx.files:
                    code = ctx.files[full]
            if code is not None:
                pw, preads, unres, is_test = py_effects(code)
                ctx.py_unresolved += unres
                for p, op in pw:
                    add_write(p, op)
                test_code = is_test
            if cls is None:
                cls = "test" if test_code else "run"
    elif prog in ("pytest", "py.test", "tox", "nox") or (
            "/" in prog_path and prog in ("test", "doctest") and "bin" in prog_path):
        cls = "test"
        for a in args:
            if a.split("::")[0].endswith(".py"):
                add_exec(a.split("::")[0])
    elif prog == "git":
        sub, sub_args = _git_sub(args)
        cls = "search" if sub in ("grep", "ls-files") else "vcs"
        res["vcs"] = _git_effect(sub, sub_args)
    elif "/" in prog_path and prog.endswith(".py"):
        add_exec(prog_path)
        cls = "run"
    elif prog == "cd":
        cls = "setup"
        target = args[0] if args else "/root"
        if target != "-":
            k, v = norm_path(target, cwd)
            if k == "repo":
                res["cwd"] = posixpath.join(REPO, v)
            elif k == "outside":
                res["cwd"] = v
            elif target in ("~",):
                res["cwd"] = "/root"
    elif prog == "command" and args and args[0] in ("-v", "-V"):
        cls = "setup"
    elif prog in SETUP_PROGS:
        cls = "setup"
    elif prog in READ_PROGS:
        ops = _operands(prog, args)
        if ops or stdin_file:
            cls = "read"
            rng = _read_range(prog, args)
            for a in ops + ([stdin_file] if stdin_file else []):
                k, v = norm_path(a, cwd)
                if k == "repo":
                    res["reads"].append(v)
                    res["read_ranges"].append((v, rng))
        else:
            cls = "other"
    elif prog in SEARCH_PROGS:
        cls = "search"
        if prog not in ("ls", "find", "tree", "locate"):
            for a in _operands(prog, args):
                k, v = norm_path(a, cwd)
                if k == "repo":
                    res["evidence"].append(v)
    if writes:
        res["cls"] = "edit"
        if prog in READ_PROGS:
            for a in _operands(prog, args):
                k, v = norm_path(a, cwd)
                if k == "repo":
                    res["evidence"].append(v)
    elif cls in ("test", "run"):
        res["cls"] = cls
    elif res["scratch_writes"]:
        res["cls"] = "scratch"
    else:
        res["cls"] = cls or "other"
    res["writes"] = writes
    res["test_code"] = test_code
    if res["cls"] == "read" and "No such file" not in output:
        res["evidence"].extend(res["reads"])
    if "No such file" in output:
        res["evidence"] = []
    return res


def _git_effect(sub: str, args: list[str]):
    """'revert' | 'stash_push' | 'stash_end' | None for a git subcommand."""
    if sub == "stash":
        op = next((a for a in args if not a.startswith("-")), "push")
        if op in ("push", "save"):
            return "stash_push"
        if op in ("pop", "apply"):
            return "stash_end"
        if op in ("drop", "clear"):
            return "revert"
        return None
    if sub == "checkout" and ("--" in args or "." in args or "-f" in args or "--force" in args):
        return "revert"
    if sub == "restore" and not (("--staged" in args or "-S" in args)
                                 and "--worktree" not in args and "-W" not in args):
        return "revert"
    if sub == "reset" and "--hard" in args:
        return "revert"
    if sub == "clean" and any(a.startswith("-") and "f" in a for a in args):
        return "revert"
    return None


def _read_range(prog: str, args: list[str]):
    """Requested line range of a read: 'all', (first, last) or None (unknown)."""
    if prog in ("cat", "nl", "less", "more", "bat"):
        return "all"
    if prog == "sed":
        scripts = [args[i + 1] for i, a in enumerate(args[:-1]) if a == "-e"]
        if not scripts:
            scripts = [a for a in args if not a.startswith("-")][:1]
        rngs = []
        for sc in scripts:
            for part in sc.split(";"):
                m = re.fullmatch(r"\s*(\d+)(?:,(\d+))?p\s*", part)
                if not m:
                    return None
                a = int(m.group(1))
                rngs.append((a, int(m.group(2)) if m.group(2) else a))
        if len(rngs) == 1:
            return rngs[0]
        return None
    if prog == "head":
        n = 10
        for i, a in enumerate(args):
            if a == "-n" and i + 1 < len(args) and args[i + 1].isdigit():
                n = int(args[i + 1])
            elif re.fullmatch(r"-n?\d+", a):
                n = int(a.lstrip("-n"))
            elif a.startswith("-c") or a == "--bytes":
                return None
        return (1, n)
    return None


def _git_sub(args: list[str]):
    j = 0
    while j < len(args):
        a = args[j]
        if a in ("-C", "-c", "--git-dir", "--work-tree") and j + 1 < len(args):
            j += 2
            continue
        if a.startswith("-"):
            j += 1
            continue
        return a, args[j + 1:]
    return "", []


def code_command(cmd: str, output: str, ctx: Ctx, cwd: str = REPO,
                 outer_last: bool = True, outer_piped: bool = False) -> list[dict]:
    """Segment and classify one exec command -> list of classified segments.

    Each segment carries `last` (it is the record's last raw segment, pipeline
    filters included) and `piped` (its output goes into a pipe)."""
    segs, fails = split_segments(cmd)
    ctx.parse_failures += fails
    out = []
    for i, s in enumerate(segs):
        last = outer_last and i == len(segs) - 1
        piped = outer_piped or (i + 1 < len(segs) and segs[i + 1]["sep"] == "|")
        toks, _ = tokenize(s["text"])
        words = [t for t, k in toks if k != "op"]
        words, _ = _strip_wrappers([w for w in words if w not in CONTROL_PREFIX])
        if len(words) >= 3 and words[0] in ("bash", "sh") and words[1] in ("-c", "-lc", "-ec"):
            inner = code_command(words[2], output, ctx, cwd, last, piped)
            out.extend(inner)
            if inner:
                cwd = inner[-1]["cwd"]
            continue
        r = classify_segment(s, cwd, output, ctx, after_pipe=s["sep"] == "|")
        if r is None:
            continue
        r["text"] = s["text"]
        r["last"], r["piped"] = last, piped
        cwd = r["cwd"]
        out.append(r)
    return out


# --------------------------------------------------------------------------
# Test outcome
# --------------------------------------------------------------------------

_PYTEST_SUMMARY = re.compile(
    r"^[=\s]*((?:\d+ (?:passed|failed|errors?|skipped|xfailed|xpassed|warnings?|deselected|"
    r"rerun)(?:, )?)+) in [\d.]+ ?s(?:econds)?\b", re.M)
_SYMPY_SUMMARY = re.compile(r"tests finished: ([^\n]*)")
_UNITTEST_RAN = re.compile(r"^Ran (\d+) tests? in [\d.]+s\s*\n+\s*(OK|FAILED)\b", re.M)
_RUNNER_FAIL = re.compile(
    r"DO \*NOT\* COMMIT!|errors? during collection|^ERROR collecting|^E\s+ImportError|"
    r"ImportError while loading conftest|^INTERNALERROR|^Interrupted: |"
    r"Traceback \(most recent call last\)|^\s*File \"[^\"]+\", line \d+|"
    r"^ERROR: |: error: (?:unrecognized arguments|ambiguous option|argument)|"
    r"::\S+ (?:FAILED|ERROR)\b", re.M)
_LAST_LINE_EXC = re.compile(r"^[A-Za-z_][\w.]*(?:Error|Exception)\b(?::.*)?$")


def _counts(text: str) -> dict:
    c = Counter()
    for n, word in re.findall(r"(\d+) (passed|failed|errors?|exceptions?)", text):
        key = {"error": "error", "errors": "error", "exception": "error",
               "exceptions": "error"}.get(word, word)
        c[key] += int(n)
    return c


def test_outcome(output: str, rc: int, last: bool, piped: bool) -> str:
    """'pass' | 'fail' | 'unknown' for a test segment, read from its record's output."""
    summaries = [_counts(m.group(1)) for m in _PYTEST_SUMMARY.finditer(output)]
    summaries += [_counts(m.group(1)) for m in _SYMPY_SUMMARY.finditer(output)]
    for m in _UNITTEST_RAN.finditer(output):
        summaries.append(Counter({"passed": int(m.group(1))}) if m.group(2) == "OK"
                         else Counter({"failed": 1}))
    if any(c["failed"] or c["error"] for c in summaries):
        return "fail"
    if "DO *NOT* COMMIT!" in output:
        return "fail"
    if summaries and any(c["passed"] for c in summaries):
        return "pass"
    if _RUNNER_FAIL.search(output):
        return "fail"
    tail = [ln for ln in output.strip().splitlines() if ln.strip()]
    if tail and _LAST_LINE_EXC.match(tail[-1].strip()):
        return "fail"
    if last and not piped:
        return "pass" if rc == 0 else "fail"
    return "unknown"


test_outcome.__test__ = False  # not a pytest test despite the name


# --------------------------------------------------------------------------
# Run coding (records, existence, sub-kinds)
# --------------------------------------------------------------------------

def load_exec(run_dir: str):
    """-> (exec records, exit_reason)."""
    recs, exit_reason = [], None
    tp = os.path.join(run_dir, "raw_transcript.jsonl")
    if os.path.isfile(tp):
        with open(tp, errors="replace") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("type") == "exec":
                    recs.append(r)
                elif r.get("type") == "final":
                    exit_reason = r.get("exit_reason")
    if exit_reason is None:
        rj = os.path.join(run_dir, "run.json")
        if os.path.isfile(rj):
            with open(rj) as f:
                exit_reason = json.load(f).get("exit_reason")
    return recs, exit_reason


def ref_existing(task_id: str | None) -> set[str]:
    if not task_id:
        return set()
    out = set()
    for name in ("gold.patch", "test.patch"):
        for p, st in patch_status(str(manifest.TASKS / task_id / name)).items():
            if st != "new":
                out.add(p)
    return out


def code_records(exec_recs: list[dict], ws_status: dict[str, str], ref_exist: set[str],
                 pkg_root: str = "sympy/"):
    """Code a run's exec records. -> (records, info)."""
    ctx = Ctx()
    records = []
    for idx, r in enumerate(exec_recs):
        out = str(r.get("output") or "")
        before = ctx.parse_failures
        segs = code_command(str(r.get("command") or ""), out, ctx)
        rc = r.get("exit_code")
        rc = rc if isinstance(rc, int) else -1
        for s in segs:
            s["outcome"] = test_outcome(out, rc, s["last"], s["piped"]) if s["cls"] == "test" else None
        records.append({
            "idx": idx, "turn": r.get("turn"), "command": str(r.get("command") or ""),
            "norm": " ".join(str(r.get("command") or "").split()),
            "exit_code": rc, "output": out, "segs": segs,
            "malformed": ctx.parse_failures > before,
        })
    # stashed spans: from `git stash` (push/save) to the next `git stash pop/apply`;
    # an unclosed span runs to the end of the log.
    stashed = False
    for rec in records:
        for s in rec["segs"]:
            if s.get("vcs") == "stash_push":
                stashed = True
                s["stashed"] = False
                continue
            if s.get("vcs") == "stash_end":
                stashed = False
            s["stashed"] = stashed
    # existence resolution
    first_write: dict[str, tuple[tuple[int, int], str]] = {}
    evidence_pos: dict[str, tuple[int, int]] = {}
    for rec in records:
        for si, s in enumerate(rec["segs"]):
            pos = (rec["idx"], si)
            for p in s["evidence"]:
                evidence_pos.setdefault(p, pos)
            for p, op in s["writes"]:
                if p is not None and p not in first_write:
                    first_write[p] = (pos, op)
    existence: dict[str, str] = {}
    for p, (pos, op) in first_write.items():
        st = ws_status.get(p)
        if st in ("modified", "deleted"):
            e = "existing"
        elif st == "new":
            e = "new"
        elif p in ref_exist:
            e = "existing"
        elif p in evidence_pos and evidence_pos[p] < pos:
            e = "existing"
        elif op == "full":
            e = "new"
        else:
            e = "unknown"
        existence[p] = e
    subkind = {}
    for p, e in existence.items():
        tl = is_test_like(p)
        if e == "existing":
            subkind[p] = "existing_test" if tl else "source"
        elif e == "new":
            if tl:
                subkind[p] = "new_test"
            elif p.startswith(pkg_root) and p.endswith(".py") and ws_status.get(p) == "new":
                subkind[p] = "source_new"
            else:
                subkind[p] = "scratch"
        else:
            subkind[p] = "unknown"
    for rec in records:
        classes, subs = set(), set()
        for s in rec["segs"]:
            classes.add(s["cls"])
            if s["cls"] == "edit":
                s["subkinds"] = {subkind[p] if p is not None else "unknown" for p, _ in s["writes"]}
                subs |= s["subkinds"]
            if s.get("vcs") == "revert":
                classes.add("tree_revert")
        rec["classes"] = classes
        rec["subkinds"] = subs
        rec["primary"] = next((c for c in CLASS_ORDER if c in classes), "other")
    n_segs = sum(len(r["segs"]) for r in records)
    info = {
        "n_segments": n_segs,
        "n_other_segments": sum(1 for r in records for s in r["segs"] if s["cls"] == "other"),
        "other_progs": Counter(s["prog"] or "<none>" for r in records for s in r["segs"]
                               if s["cls"] == "other"),
        "n_paths_written": len(existence),
        "n_unknown_existence": sum(1 for e in existence.values() if e == "unknown"),
        "unresolved_edit_targets": ctx.unresolvable_writes,
        "py_unresolved_writes": ctx.py_unresolved,
        "parse_failures": ctx.parse_failures,
        "existence": existence,
        "subkind": subkind,
        "test_outcomes": Counter(s["outcome"] for r in records for s in r["segs"]
                                 if s["cls"] == "test"),
    }
    return records, info


CHANGE_KINDS = ("source", "source_new")


def _reread(shown: dict, path: str, rng, text: str) -> bool:
    """M10 rule for one read of `path` given what was shown since its last edit."""
    st = shown.setdefault(path, {"all": False, "ranges": [], "texts": set()})
    if rng is None:
        hit = text in st["texts"]
    elif rng == "all":
        hit = st["all"]
    else:
        a, b = rng
        if st["all"]:
            hit = True
        else:
            covered = set()
            for x, y in st["ranges"]:
                lo, hi = max(a, x), min(b, y)
                if lo <= hi:
                    covered.update(range(lo, hi + 1))
            hit = 2 * len(covered) >= (b - a + 1)
    if rng == "all":
        st["all"] = True
    elif rng is not None:
        st["ranges"].append(rng)
    st["texts"].add(text)
    return hit


def metrics_from_records(records, info, exit_reason, ws_status, gold_files, ws_lines,
                         ws_edits=frozenset(), gold_edits=frozenset()):
    subkind = info["subkind"]
    N = [r for r in records if r["primary"] != "done"]
    n = len(N)
    m: dict = {"exit_reason": exit_reason}
    m["n_cmds"] = n
    first_src = next((i for i, r in enumerate(N) if set(CHANGE_KINDS) & r["subkinds"]), None)
    m["first_edit_frac"] = 1.0 if first_src is None or n == 0 else first_src / n
    head = N[:10]
    m["early_edit_share"] = sum(r["primary"] == "edit" for r in head) / len(head) if head else 0.0
    m["test_share"] = sum("test" in r["classes"] for r in N) / n if n else 0.0
    m["exec_share"] = sum(bool({"test", "run"} & r["classes"]) for r in N) / n if n else 0.0
    m["wrote_new_test"] = int(any(v == "new_test" for v in subkind.values()))
    # M7: a .py that is edit:scratch (repo) or written outside /repo, later executed
    written_at: dict[str, tuple[int, int]] = {}
    m7 = 0
    for rec in records:
        for si, s in enumerate(rec["segs"]):
            pos = (rec["idx"], si)
            for p in s["execs"]:
                if p in written_at and written_at[p] < pos:
                    m7 = 1
            for p, _ in s["writes"]:
                if p is not None and p.endswith(".py") and subkind.get(p) == "scratch":
                    written_at.setdefault(p, pos)
            for p in s["scratch_writes"]:
                if p.endswith(".py"):
                    written_at.setdefault(p, pos)
    m["wrote_scratch_script"] = m7
    # M8
    seen, rep = set(), 0
    for r in N:
        if r["norm"] in seen:
            rep += 1
        seen.add(r["norm"])
    m["repeat_cmd_share"] = rep / n if n else 0.0
    # M9
    last_test: dict[str, int] = {}
    last_edit = -1
    tests = noop = 0
    for k, r in enumerate(N):
        if "test" in r["classes"]:
            tests += 1
            prev = last_test.get(r["norm"])
            if prev is not None and last_edit < prev and "edit" not in r["classes"]:
                noop += 1
            last_test[r["norm"]] = k
        if "edit" in r["classes"]:
            last_edit = k
    m["noop_retest_share"] = noop / tests if tests else 0.0
    # M10 on line ranges
    shown: dict[str, dict] = {}
    reads = rereads = 0
    for rec in records:
        hit = False
        for s in rec["segs"]:
            if s["cls"] == "read":
                for p, rng in s["read_ranges"]:
                    hit |= _reread(shown, p, rng, " ".join(s["text"].split()))
            for p, _ in s["writes"]:
                shown.pop(p, None)
        if rec["primary"] != "done" and "read" in rec["classes"]:
            reads += 1
            rereads += hit
    m["reread_share"] = rereads / reads if reads else 0.0
    # M11
    srch = [r for r in N if "search" in r["classes"]]
    m["search_miss_share"] = (sum(1 for r in srch if not r["output"].strip() or r["exit_code"] != 0)
                              / len(srch)) if srch else 0.0
    # M12, M13
    m["extra_files"] = len(set(ws_status) - set(gold_files))
    m["patch_lines"] = ws_lines
    # U
    last_change = None
    any_src = False
    for rec in records:
        for si, s in enumerate(rec["segs"]):
            src = s["cls"] == "edit" and bool(set(CHANGE_KINDS) & s.get("subkinds", set()))
            any_src |= src
            if src or s.get("vcs") == "revert":
                last_change = (rec["idx"], si)
    m["no_edit"] = int(not any_src)
    m["unsupported_done"] = m["U_lenient"] = None
    m["U_unknown"] = 0
    if exit_reason == "completed" and any_src:
        outcomes, lenient = [], False
        for rec in records:
            for si, s in enumerate(rec["segs"]):
                if (rec["idx"], si) <= last_change or s.get("stashed"):
                    continue
                if s["cls"] == "test":
                    outcomes.append(s["outcome"])
                elif s["cls"] == "run" and s["last"] and rec["exit_code"] == 0:
                    lenient = True
        if "pass" in outcomes:
            m["unsupported_done"] = m["U_lenient"] = 0
        elif outcomes and all(o == "unknown" for o in outcomes):
            m["U_unknown"] = 1
            m["U_lenient"] = 0 if lenient else None
        else:
            m["unsupported_done"] = 1
            m["U_lenient"] = 0 if lenient else 1
    m["U_sensitivity"] = 1 if m["U_unknown"] else m["unsupported_done"]
    # descriptive
    m["gold_file_hit"] = int(bool(gold_files) and set(gold_files) <= set(ws_status))
    m["edit_jaccard_gold"] = cv.jac(ws_edits, gold_edits)
    m["edited_existing_test"] = int(any(v == "existing_test" for v in subkind.values()))
    m["error_share"] = sum(r["exit_code"] != 0 for r in N) / n if n else 0.0
    m["leftover_new_files"] = sum(1 for st in ws_status.values() if st == "new")
    nf = Counter(s["prog"] for r in records for s in r["segs"] if s.get("not_found"))
    m["cmd_not_found"] = sum(nf.values())
    m["cmd_not_found_progs"] = ";".join(f"{k}:{v}" for k, v in sorted(nf.items()))
    m["malformed_cmd"] = sum(r["malformed"] for r in records)
    m["primary_seq"] = [r["primary"] for r in records]
    for k in ("n_segments", "n_other_segments", "n_unknown_existence",
              "unresolved_edit_targets", "py_unresolved_writes", "parse_failures"):
        m[k] = info[k]
    return m


def run_metrics(run_dir: str, task_id: str) -> dict:
    """M1-M13, U, U_lenient, no_edit, descriptive measures for one run."""
    recs, exit_reason = load_exec(run_dir)
    wp = os.path.join(run_dir, "workspace.patch")
    ws_status = patch_status(wp)
    records, info = code_records(recs, ws_status, ref_existing(task_id), package_root(task_id))
    gp = str(manifest.TASKS / task_id / "gold.patch")
    gold_files = list(patch_status(gp))
    ws_edits = cv.parse_patch(wp)[1]
    gold_edits = cv.parse_patch(gp)[1]
    return metrics_from_records(records, info, exit_reason, ws_status, gold_files,
                                patch_line_count(wp), ws_edits, gold_edits)


# --------------------------------------------------------------------------
# Statistics helpers
# --------------------------------------------------------------------------

def transform(key: str, v):
    t = dict((k, tr) for _, k, tr in METRICS).get(key)
    if v is None:
        return None
    if t == "log":
        return math.log(v) if v > 0 else 0.0
    if t == "log1p":
        return math.log1p(v)
    return float(v)


def anova_balanced(y: dict, models: list, tasks: list) -> dict:
    """Balanced two-way layout. y[(model, task)] = list of R values."""
    R = len(y[(models[0], tasks[0])])
    M, T = len(models), len(tasks)
    for k in y:
        if len(y[k]) != R:
            raise ValueError("unbalanced layout")
    allv = [v for mm in models for t in tasks for v in y[(mm, t)]]
    g = sum(allv) / len(allv)
    cell = {(mm, t): sum(y[(mm, t)]) / R for mm in models for t in tasks}
    mmean = {mm: sum(cell[(mm, t)] for t in tasks) / T for mm in models}
    tmean = {t: sum(cell[(mm, t)] for mm in models) / M for t in tasks}
    ss_total = sum((v - g) ** 2 for v in allv)
    ss_model = T * R * sum((mmean[mm] - g) ** 2 for mm in models)
    ss_task = M * R * sum((tmean[t] - g) ** 2 for t in tasks)
    ss_cells = R * sum((c - g) ** 2 for c in cell.values())
    ss_inter = ss_cells - ss_model - ss_task
    ss_rep = sum((v - cell[k]) ** 2 for k in cell for v in y[k])
    return {
        "ss": {"model": ss_model, "task": ss_task, "model:task": ss_inter, "repeat": ss_rep,
               "total": ss_total},
        "df": {"model": M - 1, "task": T - 1, "model:task": (M - 1) * (T - 1),
               "repeat": M * T * (R - 1)},
        "cells": ss_cells,
    }


def _ge(s: float, obs: float) -> bool:
    """s >= obs with a relative tie tolerance of 1e-12."""
    if not math.isfinite(obs):
        return s == obs
    return s >= obs - 1e-12 * max(1.0, abs(obs))


def _ratio(num, den):
    if den <= 1e-15:
        return math.inf if num > 1e-15 else 0.0
    return num / den


def _p_main_stat(cellmeans: dict, models, tasks, R, ss_cells, ss_task, g):
    M, T = len(models), len(tasks)
    mmean = [sum(cellmeans[t][i] for t in tasks) / T for i in range(M)]
    ss_model = T * R * sum((x - g) ** 2 for x in mmean)
    ss_inter = ss_cells - ss_model - ss_task
    return _ratio(ss_model / (M - 1), max(ss_inter, 0.0) / ((M - 1) * (T - 1)))


def _p_cell_stat(vals: dict, M, T, R, ss_total, ss_task):
    ss_cells = 0.0
    tot = sum(sum(v) for v in vals.values())
    g = tot / (M * T * R)
    for v in vals.values():
        for i in range(M):
            c = sum(v[i * R:(i + 1) * R]) / R
            ss_cells += R * (c - g) ** 2
    ss_rep = ss_total - ss_cells
    return _ratio((ss_cells - ss_task) / (T * (M - 1)), max(ss_rep, 0.0) / (M * T * (R - 1)))


def variance_split(rows: list[dict], key: str, models: list, tasks: list,
                   draws: int = DRAWS, seed: int = SEED) -> dict:
    """A1 for one metric: SS shares and the two permutation p-values."""
    y = defaultdict(list)
    for r in rows:
        if r["task_id"] in tasks and r["model"] in models:
            y[(r["model"], r["task_id"])].append(transform(key, r[key]))
    a = anova_balanced(y, models, tasks)
    ss = a["ss"]
    M, T, R = len(models), len(tasks), len(y[(models[0], tasks[0])])
    out = {"shares": None, "p_main": None, "p_cell": None, "constant": ss["total"] <= 1e-15,
           "ss": ss}
    if out["constant"]:
        return out
    out["shares"] = {k: ss[k] / ss["total"] for k in ("model", "task", "model:task", "repeat")}
    g = sum(v for vs in y.values() for v in vs) / (M * T * R)
    # p_main: permute model labels of cells within task
    cellmeans = {t: [sum(y[(mm, t)]) / R for mm in models] for t in tasks}
    obs = _p_main_stat(cellmeans, models, tasks, R, a["cells"], ss["task"], g)
    rng = random.Random(seed)
    ge = 0
    for _ in range(draws):
        perm = {t: rng.sample(cellmeans[t], M) for t in tasks}
        ge += _ge(_p_main_stat(perm, models, tasks, R, a["cells"], ss["task"], g), obs)
    out["p_main"] = (1 + ge) / (1 + draws)
    out["stat_main"] = obs
    # p_cell: permute runs within task
    vals = {t: [v for mm in models for v in y[(mm, t)]] for t in tasks}
    obs2 = _p_cell_stat(vals, M, T, R, ss["total"], ss["task"])
    rng = random.Random(seed + 100)
    ge = 0
    for _ in range(draws):
        perm = {t: rng.sample(vals[t], len(vals[t])) for t in tasks}
        ge += _ge(_p_cell_stat(perm, M, T, R, ss["total"], ss["task"]), obs2)
    out["p_cell"] = (1 + ge) / (1 + draws)
    out["stat_cell"] = obs2
    return out


def holm(pvals: list) -> list:
    """Holm step-down adjustment; None entries stay None and are not in the family."""
    idx = [i for i, p in enumerate(pvals) if p is not None]
    m = len(idx)
    order = sorted(idx, key=lambda i: pvals[i])
    adj = [None] * len(pvals)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvals[i]))
        adj[i] = running
    return adj


def _avg_ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def kendall_w(table: list[list[float]]):
    """table[rater][object] scores -> Kendall's W with tie correction."""
    m, n = len(table), len(table[0])
    ranks = [_avg_ranks(row) for row in table]
    sums = [sum(ranks[r][o] for r in range(m)) for o in range(n)]
    mean = sum(sums) / n
    s = sum((x - mean) ** 2 for x in sums)
    ties = 0.0
    for row in table:
        for c in Counter(row).values():
            ties += c ** 3 - c
    den = m * m * (n ** 3 - n) - m * ties
    return None if den <= 0 else 12 * s / den


def _binom_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k), X ~ Binomial(n, p)."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    if p <= 0:
        return 1.0
    if p >= 1:
        return 0.0
    lp, lq = math.log(p), math.log1p(-p)
    tot = 0.0
    for i in range(k + 1):
        tot += math.exp(math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1)
                        + i * lp + (n - i) * lq)
    return min(1.0, tot)


def clopper_pearson(k: int, n: int, alpha: float = 0.05):
    """Exact two-sided interval by bisection on the binomial tails."""
    if n == 0:
        return (None, None)

    def bisect(f, lo=0.0, hi=1.0):
        for _ in range(200):
            mid = (lo + hi) / 2
            if f(mid):
                hi = mid
            else:
                lo = mid
        return (lo + hi) / 2

    # lower: P(X >= k | p) = alpha/2, increasing in p
    lower = 0.0 if k == 0 else bisect(lambda p: 1 - _binom_cdf(k - 1, n, p) >= alpha / 2)
    # upper: P(X <= k | p) = alpha/2, decreasing in p
    upper = 1.0 if k == n else bisect(lambda p: _binom_cdf(k, n, p) <= alpha / 2)
    return (lower, upper)


def cohen_kappa(a: list, b: list):
    if len(a) != len(b) or not a:
        return None
    n = len(a)
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[c] * cb[c] for c in set(ca) | set(cb)) / (n * n)
    if pe >= 1:
        return 1.0 if po == 1 else None
    return (po - pe) / (1 - pe)


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


# --------------------------------------------------------------------------
# 6. Analyses
# --------------------------------------------------------------------------

def _set_s(rows):
    return [r for r in rows if r["task_id"] in SYMPY_TASKS]


def _models(rows):
    present = {r["model"] for r in rows}
    return [m for m in cv.ORDER if m in present] + sorted(present - set(cv.ORDER))


def a1_a2_decisions(rows: list[dict], draws: int = DRAWS) -> dict:
    S = _set_s(rows)
    models = _models(S)
    tasks = [t for t in SYMPY_TASKS if any(r["task_id"] == t for r in S)]
    res = {}
    for i, (mid, key, _) in enumerate(METRICS):
        vs = variance_split(S, key, models, tasks, draws=draws, seed=SEED + i)
        cm = {(r["model"], r["task_id"]): [] for r in S}
        for r in S:
            cm[(r["model"], r["task_id"])].append(transform(key, r[key]))
        table = [[_mean(cm[(mm, t)]) for mm in models] for t in tasks]
        vs["kendall_w"] = None if vs["constant"] else kendall_w(table)
        res[mid] = {"key": key, **vs}
    ids = [mid for mid, _, _ in METRICS]
    adj_main = holm([res[i]["p_main"] for i in ids])
    adj_cell = holm([res[i]["p_cell"] for i in ids])
    for i, mid in enumerate(ids):
        r = res[mid]
        r["p_main_holm"], r["p_cell_holm"] = adj_main[i], adj_cell[i]
        r["label"] = decide(r)
    return res


def a1_completed_sensitivity(rows: list[dict]) -> dict:
    """A1 repeated on completed runs of S (unbalanced): marginal SS shares, no tests."""
    S = [r for r in _set_s(rows) if r["exit_reason"] == "completed"]
    out = {"n_runs": len(S)}
    for mid, key, _ in METRICS:
        vals = [(r["model"], r["task_id"], transform(key, r[key])) for r in S]
        if len(vals) < 2:
            out[mid] = None
            continue
        g = sum(v for _, _, v in vals) / len(vals)
        groups = {"model": defaultdict(list), "task": defaultdict(list), "cell": defaultdict(list)}
        for mm, t, v in vals:
            groups["model"][mm].append(v)
            groups["task"][t].append(v)
            groups["cell"][(mm, t)].append(v)
        means = {k: {kk: sum(vs) / len(vs) for kk, vs in d.items()} for k, d in groups.items()}
        tot = sum((v - g) ** 2 for _, _, v in vals)
        if tot <= 1e-15:
            out[mid] = {"constant": True}
            continue
        ss_m = sum((means["model"][mm] - g) ** 2 for mm, _, _ in vals)
        ss_t = sum((means["task"][t] - g) ** 2 for _, t, _ in vals)
        ss_c = sum((means["cell"][(mm, t)] - g) ** 2 for mm, t, _ in vals)
        out[mid] = {"model": ss_m / tot, "task": ss_t / tot, "cells": ss_c / tot,
                    "repeat": (tot - ss_c) / tot}
    return out


def decide(r: dict) -> str:
    if r.get("constant") or r.get("p_main_holm") is None:
        return "indeterminate"
    w = r.get("kendall_w")
    sh = r["shares"]
    if (r["p_main_holm"] < 0.05 and r["p_cell"] is not None and r["p_cell"] < 0.05
            and w is not None and w >= 0.6 and sh["model"] > sh["repeat"]):
        return "model habit"
    if r["p_cell_holm"] is not None and r["p_cell_holm"] < 0.05:
        return "task-dependent model habit"
    if r["p_cell"] is not None and r["p_cell"] >= 0.05:
        return "repeat noise"
    return "indeterminate"


def _group_stats(vals):
    vals = sorted(vals)
    if not vals:
        return {"n": 0, "mean": None, "median": None, "mean_log": None}
    k = len(vals)
    med = vals[k // 2] if k % 2 else (vals[k // 2 - 1] + vals[k // 2]) / 2
    return {"n": k, "mean": sum(vals) / k, "median": med,
            "mean_log": sum(transform("n_cmds", v) for v in vals) / k}


def a3_length_outcome(rows: list[dict]) -> dict:
    S = _set_s(rows)

    def contrast(rs):
        res = _group_stats([r["n_cmds"] for r in rs if r["resolved"]])
        unr = _group_stats([r["n_cmds"] for r in rs if not r["resolved"]])
        d = (unr["mean_log"] - res["mean_log"]) if res["n"] and unr["n"] else None
        return {"resolved": res, "unresolved": unr, "diff_mean_log_unres_minus_res": d}

    out = {"pooled": contrast(S), "by_task": {}, "mixed_cells": {}}
    for t in SYMPY_TASKS:
        out["by_task"][t] = contrast([r for r in S if r["task_id"] == t])
    cells = defaultdict(list)
    for r in S:
        cells[(r["model"], r["task_id"])].append(r)
    for (mm, t), rs in sorted(cells.items()):
        k = sum(r["resolved"] for r in rs)
        if 0 < k < len(rs):
            out["mixed_cells"][f"{mm}|{t}"] = contrast(rs)
    diffs = [c["diff_mean_log_unres_minus_res"] for c in out["mixed_cells"].values()]
    out["mixed_mean_diff"] = _mean(diffs)
    out["mixed_n_resolved"] = sum(c["resolved"]["n"] for c in out["mixed_cells"].values())
    out["mixed_n_unresolved"] = sum(c["unresolved"]["n"] for c in out["mixed_cells"].values())
    return out


def a4_completion(rows: list[dict]) -> dict:
    S = [r for r in _set_s(rows) if r["exit_reason"] == "completed"]
    out = {"n_completed": len(S), "no_edit": sum(r["no_edit"] for r in S),
           "U_unknown": sum(r.get("U_unknown") or 0 for r in S)}
    for key in ("unsupported_done", "U_lenient", "U_sensitivity"):
        rs = [r for r in S if r[key] is not None]
        table = {f"U={u}|resolved={int(v)}": sum(1 for r in rs if r[key] == u and bool(r["resolved"]) == v)
                 for u in (0, 1) for v in (False, True)}
        per_model = {}
        for mm in _models(S):
            mr = [r for r in rs if r["model"] == mm]
            k = sum(r[key] for r in mr)
            lo, hi = clopper_pearson(k, len(mr))
            per_model[mm] = {"k": k, "n": len(mr), "rate": k / len(mr) if mr else None,
                             "ci95": [lo, hi]}
        out[key] = {"table": table, "per_model": per_model}
    return out


def _zscore(S, keys):
    cols = {}
    for k in keys:
        xs = [transform(k, r[k]) for r in S]
        mu = sum(xs) / len(xs)
        sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / len(xs))
        if sd > 1e-12:
            cols[k] = [(x - mu) / sd for x in xs]
    return [[cols[k][i] for k in cols] for i in range(len(S))]


def _nearest(x, cents: dict, order):
    best, bd = None, math.inf
    for mm in order:
        c = cents.get(mm)
        if c is None:
            continue
        d = sum((a - b) ** 2 for a, b in zip(x, c, strict=True))
        if d < bd - 1e-12:
            best, bd = mm, d
    return best


def _nc_accuracy(X, y, tasks, order, scheme):
    """Nearest-centroid accuracy, leave-one-run-out or leave-one-task-out."""
    d = len(X[0]) if X else 0
    sums = defaultdict(lambda: [0.0] * d)
    cnt = Counter()
    tsums = defaultdict(lambda: [0.0] * d)
    tcnt = Counter()
    for x, yi, t in zip(X, y, tasks, strict=True):
        cnt[yi] += 1
        tcnt[(yi, t)] += 1
        for j, v in enumerate(x):
            sums[yi][j] += v
            tsums[(yi, t)][j] += v
    hits = 0
    if scheme == "loro":
        full = {m: [s / cnt[m] for s in sums[m]] for m in cnt}
        for x, yi in zip(X, y, strict=True):
            cents = dict(full)
            k = cnt[yi] - 1
            cents[yi] = [(s - v) / k for s, v in zip(sums[yi], x, strict=True)] if k else None
            hits += _nearest(x, cents, order) == yi
    else:
        fold = {}
        for t in set(tasks):
            fold[t] = {m: [(s - ts) / (cnt[m] - tcnt[(m, t)])
                           for s, ts in zip(sums[m], tsums[(m, t)], strict=True)]
                       for m in cnt if cnt[m] - tcnt[(m, t)] > 0}
        for x, yi, t in zip(X, y, tasks, strict=True):
            hits += _nearest(x, fold[t], order) == yi
    return hits / len(X)


def a5_identification(rows: list[dict], draws: int = A5_DRAWS) -> dict:
    S = _set_s(rows)
    if not S:
        return {}
    order = _models(S)
    X = _zscore(S, [k for _, k, _ in METRICS])
    y = [r["model"] for r in S]
    tasks = [r["task_id"] for r in S]
    out = {"chance": 1 / len(order)}
    rng = random.Random(SEED + 500)
    for scheme in ("loro", "loto"):
        acc = _nc_accuracy(X, y, tasks, order, scheme)
        null = []
        for _ in range(draws):
            yp = list(y)
            for t in set(tasks):
                idx = [i for i in range(len(y)) if tasks[i] == t]
                lab = [y[i] for i in idx]
                rng.shuffle(lab)
                for i, v in zip(idx, lab, strict=True):
                    yp[i] = v
            null.append(_nc_accuracy(X, yp, tasks, order, scheme))
        null.sort()
        q95 = null[min(len(null) - 1, int(math.ceil(0.95 * len(null))) - 1)]
        out[scheme] = {"accuracy": acc, "null_q95": q95,
                       "p": (1 + sum(v >= acc for v in null)) / (1 + draws)}
    out["identification"] = out["loto"]["accuracy"] > out["loto"]["null_q95"]
    return out


def a6_values(records, m, gold_files) -> dict:
    """Per-run A6 flags for set P (computed from the coded records)."""
    first_err = None
    for rec in records:
        if ({"test", "run"} & rec["classes"]) and manifest.STALE_MARKER in rec["output"]:
            first_err = rec["idx"]
            break
    repair = False
    if first_err is not None:
        for rec in records[first_err + 1:]:
            for s in rec["segs"]:
                if s["prog"] in ("pip", "pip3") or (PY_RE.match(s["prog"] or "") and "pip" in s["text"].split()):
                    repair = True
                if any(e == "PYTHONPATH" or e.startswith("PYTEST_") for e in s["env"]):
                    repair = True
                for p, _ in s["writes"]:
                    if p is not None and p not in gold_files and not is_test_like(p):
                        repair = True
    comp = m["exit_reason"] == "completed"
    u, ul = m["U_sensitivity"], m["U_lenient"]
    return {
        "hit_runner_error": int(first_err is not None),
        "env_repair": int(repair),
        "verified_other_means": int(comp and u == 1 and ul == 0),
        "done_without_passing_check": int(comp and u == 1),
        "done_with_passing_test": int(comp and u == 0),
    }


def a6_summary(rows: list[dict]) -> dict:
    P = [r for r in rows if r["task_id"] == PYTEST_TASK]
    out = {}
    for stale in (True, False):
        rs = [r for r in P if bool(r["stale_image"]) == stale]
        out["stale" if stale else "clean"] = {
            "n": len(rs), "completed": sum(r["exit_reason"] == "completed" for r in rs),
            "no_edit": sum(r["no_edit"] for r in rs),
            **{k: sum(r.get("a6_" + k, 0) for r in rs) for k in
               ("hit_runner_error", "env_repair", "verified_other_means",
                "done_without_passing_check", "done_with_passing_test")},
        }
    return out


def a7_lineage(rows: list[dict]) -> dict:
    S = _set_s(rows)
    host = {r["model"]: r.get("host", "") for r in rows}
    metric_keys = {k for _, k, _ in METRICS}
    keys = [k for _, k, _ in METRICS] + DESCRIPTIVE

    def val(r, k):
        return transform(k, r[k]) if k in metric_keys else r[k]

    out = {}
    for lab, ms in cv.LINEAGES:
        gens = {mm: {k: _mean([val(r, k) for r in S if r["model"] == mm]) for k in keys}
                for mm in ms}
        links = []
        for a, b in zip(ms, ms[1:], strict=False):
            delta = {}
            for k in keys:
                va, vb = gens[a][k], gens[b][k]
                delta[k] = None if va is None or vb is None else vb - va
            links.append({"link": f"{a}->{b}", "host_crossing": host.get(a) != host.get(b),
                          "delta": delta})
        out[lab] = {"by_generation": gens, "links": links,
                    "hosts": {mm: host.get(mm, "") for mm in ms}}
    return out


def _verdict(cond, testable):
    if not testable:
        return "not testable"
    return "replicates" if cond else "does not replicate"


def score_predictions(rows: list[dict], a3: dict) -> dict:
    S = _set_s(rows)
    res = [r for r in S if r["resolved"]]
    unr = [r for r in S if not r["resolved"]]
    out = {}
    # P1
    def k_of(mm, t):
        return sum(1 for r in S if r["model"] == mm and r["task_id"] == t
                   and (r["wrote_new_test"] or r["wrote_scratch_script"]))
    hi_models, lo_models = ["kimi-k2-thinking", "v3.2"], ["gpt-5.5"]
    need = [mm for mm in hi_models + lo_models]
    testable = all(sum(1 for r in S if r["model"] == mm) >= 5 for mm in need)
    cond = all(k_of(mm, t) >= 2 for mm in hi_models for t in SYMPY_TASKS) and \
        all(k_of(mm, t) <= 1 for mm in lo_models for t in SYMPY_TASKS)
    out["P1"] = {"verdict": _verdict(cond, testable),
                 "counts": {mm: {t: k_of(mm, t) for t in SYMPY_TASKS} for mm in need}}
    # P2
    p = a3["pooled"]
    testable = (p["resolved"]["n"] >= 5 and p["unresolved"]["n"] >= 5
                and a3["mixed_n_resolved"] >= 5 and a3["mixed_n_unresolved"] >= 5)
    d, md = p["diff_mean_log_unres_minus_res"], a3["mixed_mean_diff"]
    cond = d is not None and md is not None and d > 0 and md < d
    out["P2"] = {"verdict": _verdict(cond, testable), "pooled_diff": d, "mixed_mean_diff": md}
    # P3
    def any_rep(r):
        return r["repeat_cmd_share"] > 0 or r["noop_retest_share"] > 0 or r["reread_share"] > 0
    rate = _mean([float(any_rep(r)) for r in S])
    rr, ru = _mean([float(any_rep(r)) for r in res]), _mean([float(any_rep(r)) for r in unr])
    testable = len(res) >= 5 and len(unr) >= 5
    cond = testable and rate >= 0.79 and abs(rr - ru) <= 0.15
    out["P3"] = {"verdict": _verdict(cond, testable), "rate": rate, "rate_resolved": rr,
                 "rate_unresolved": ru}
    # P4
    gr, gu = _mean([r["gold_file_hit"] for r in res]), _mean([r["gold_file_hit"] for r in unr])
    cond = testable and gr >= 0.90 and gu < gr
    out["P4"] = {"verdict": _verdict(cond, testable), "resolved": gr, "unresolved": gu}
    # P5
    def p5(rs_res, rs_unr):
        if len(rs_res) < 5 or len(rs_unr) < 5:
            return None
        e = _mean([r["early_edit_share"] for r in rs_res]) < _mean([r["early_edit_share"] for r in rs_unr])
        t = _mean([r["test_share"] for r in rs_res]) > _mean([r["test_share"] for r in rs_unr])
        return e and t
    pooled = p5(res, unr)
    per_task = {t: p5([r for r in res if r["task_id"] == t], [r for r in unr if r["task_id"] == t])
                for t in SYMPY_TASKS}
    tested = [v for v in per_task.values() if v is not None]
    cond = bool(pooled) and bool(tested) and all(tested)
    out["P5"] = {"verdict": _verdict(cond, pooled is not None), "pooled": pooled,
                 "per_task": per_task}
    # P6
    comp = [r for r in S if r["exit_reason"] == "completed" and r["unsupported_done"] is not None]
    cr = [r["unsupported_done"] for r in comp if r["resolved"]]
    cu = [r["unsupported_done"] for r in comp if not r["resolved"]]
    testable = len(cr) >= 5 and len(cu) >= 5
    ur, uu = _mean(cr), _mean(cu)
    cond = testable and ur > 0 and uu > ur
    out["P6"] = {"verdict": _verdict(cond, testable), "U_resolved": ur, "U_unresolved": uu,
                 "n_resolved": len(cr), "n_unresolved": len(cu)}
    return out


# --------------------------------------------------------------------------
# Run selection and drivers
# --------------------------------------------------------------------------

def load_rows() -> list[dict]:
    """Included runs on the verified tasks, with repeat index (no transcript opened)."""
    cells = defaultdict(list)
    for row in manifest.load_runs():
        if not row["included"] or row["task_id"] not in cv.VERIFIED:
            continue
        cells[(row["model"], row["task_id"])].append(row)
    out = []
    for key, rs in sorted(cells.items()):
        if len(rs) != 3:
            raise SystemExit(f"cell {key} has {len(rs)} included runs; K=3 expected")
        rs.sort(key=lambda r: r["run_id"].rsplit("--", 1)[1])
        for i, r in enumerate(rs, 1):
            out.append({**r, "repeat": i, "dir": str(manifest.CORPUS / r["batch"] / r["run_id"])})
    return out


def compute_all() -> list[dict]:
    rows = []
    for r in load_rows():
        recs, exit_reason = load_exec(r["dir"])
        wp = os.path.join(r["dir"], "workspace.patch")
        ws_status = patch_status(wp)
        records, info = code_records(recs, ws_status, ref_existing(r["task_id"]),
                                     package_root(r["task_id"]))
        gp = str(manifest.TASKS / r["task_id"] / "gold.patch")
        gold_files = list(patch_status(gp))
        m = metrics_from_records(records, info, exit_reason, ws_status, gold_files,
                                 patch_line_count(wp), cv.parse_patch(wp)[1], cv.parse_patch(gp)[1])
        row = {k: r[k] for k in ("run_id", "model", "task_id", "lab", "generation", "host",
                                 "repeat", "resolved", "stale_image")}
        row["set"] = "S" if r["task_id"] in SYMPY_TASKS else "P"
        row.update(m)
        if r["task_id"] == PYTEST_TASK:
            row.update({"a6_" + k: v for k, v in a6_values(records, m, gold_files).items()})
        rows.append(row)
    return rows


def analyse(rows: list[dict], validated: bool = False, draws: int = DRAWS,
            a5_draws: int = A5_DRAWS) -> dict:
    a12 = a1_a2_decisions(rows, draws=draws)
    a3 = a3_length_outcome(rows)
    return {
        "status": "validated instrument" if validated else "unvalidated instrument",
        "A1_A2_decisions": a12,
        "A1_completed_only_sensitivity": a1_completed_sensitivity(rows),
        "A3_length_outcome": a3,
        "A4_completion": a4_completion(rows),
        "A5_identification": a5_identification(rows, draws=a5_draws),
        "A6_stale_image": a6_summary(rows),
        "A7_lineage": a7_lineage(rows),
        "predictions": score_predictions(rows, a3),
    }


METRIC_COLS = ["run_id", "model", "task_id", "set", "repeat", "lab", "generation", "host",
               "stale_image", "resolved", "exit_reason"] + [k for _, k, _ in METRICS] + [
    "unsupported_done", "U_lenient", "U_unknown", "U_sensitivity", "no_edit"] + DESCRIPTIVE + [
    "cmd_not_found_progs",
    "n_segments", "n_other_segments", "n_unknown_existence", "unresolved_edit_targets",
    "py_unresolved_writes", "parse_failures", "primary_seq"]


def write_metrics_csv(rows, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(METRIC_COLS)
        for r in rows:
            vals = []
            for c in METRIC_COLS:
                v = r.get(c)
                if c == "primary_seq":
                    v = " ".join(v)
                elif isinstance(v, bool):
                    v = int(v)
                vals.append("" if v is None else v)
            w.writerow(vals)


def _jsonable(o):
    if isinstance(o, float) and (math.isinf(o) or math.isnan(o)):
        return str(o)
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    return o


def print_summary(an: dict):
    def f(x, d=3):
        return "-" if x is None else f"{x:.{d}f}"

    print(f"exp-07 command audit [{an['status']}]")
    print(f"\nA1/A2 decisions (set S, Holm over {len(METRICS)} metrics):")
    print(f"  {'id':4s}{'metric':22s}{'model':>7s}{'task':>7s}{'m:t':>7s}{'rep':>7s}"
          f"{'p_main*':>9s}{'p_cell*':>9s}{'p_cell':>8s}{'W':>6s}  label")
    for mid, r in an["A1_A2_decisions"].items():
        sh = r["shares"] or {}
        print(f"  {mid:4s}{r['key']:22s}{f(sh.get('model'), 2):>7s}{f(sh.get('task'), 2):>7s}"
              f"{f(sh.get('model:task'), 2):>7s}{f(sh.get('repeat'), 2):>7s}"
              f"{f(r['p_main_holm']):>9s}{f(r['p_cell_holm']):>9s}{f(r['p_cell']):>8s}"
              f"{f(r['kendall_w'], 2):>6s}  {r['label']}")
    a4 = an["A4_completion"]
    print(f"\nA4 completion: {a4['n_completed']} completed runs in S, no_edit {a4['no_edit']}")
    print(f"  U_unknown (excluded from the main row): {a4['U_unknown']}")
    for key in ("unsupported_done", "U_lenient", "U_sensitivity"):
        print(f"  {key}: {a4[key]['table']}")
    a5 = an["A5_identification"]
    if a5:
        print(f"\nA5 identification: LORO {f(a5['loro']['accuracy'])} (null q95 "
              f"{f(a5['loro']['null_q95'])}), LOTO {f(a5['loto']['accuracy'])} (null q95 "
              f"{f(a5['loto']['null_q95'])}); identification={a5['identification']}")
    print("\nA6 set P by stale_image:")
    for k, v in an["A6_stale_image"].items():
        print(f"  {k}: {v}")
    print("\nPredictions:")
    for k, v in an["predictions"].items():
        print(f"  {k}: {v['verdict']}")


# --------------------------------------------------------------------------
# 7. Validation sheets
# --------------------------------------------------------------------------

def _flags(rec) -> str:
    fl = sorted(rec["classes"], key=lambda c: (CLASS_ORDER + ["tree_revert"]).index(c))
    fl += [f"edit:{s}" for s in SUBKINDS if s in rec["subkinds"]]
    return ";".join(fl)


def make_label_sheets(out_dir=None):
    out_dir = str(out_dir or (OUT_DIR / "labels"))
    os.makedirs(out_dir, exist_ok=True)
    rows = [r for r in load_rows() if r["repeat"] in (2, 3) and r["task_id"] in SYMPY_TASKS]
    rng = random.Random(SEED)
    coded = {}
    for r in rows:
        recs, exit_reason = load_exec(r["dir"])
        wp = os.path.join(r["dir"], "workspace.patch")
        ws_status = patch_status(wp)
        records, info = code_records(recs, ws_status, ref_existing(r["task_id"]),
                                     package_root(r["task_id"]))
        gp = str(manifest.TASKS / r["task_id"] / "gold.patch")
        m = metrics_from_records(records, info, exit_reason, ws_status, list(patch_status(gp)),
                                 patch_line_count(wp))
        coded[r["run_id"]] = (r, records, m)
    sample = []
    for t in SYMPY_TASKS:
        pool = [(rid, rec) for rid, (r, recs, _) in sorted(coded.items()) if r["task_id"] == t
                for rec in recs]
        sample.extend(rng.sample(pool, min(40, len(pool))))
    rng.shuffle(sample)
    with open(os.path.join(out_dir, "commands_to_label.csv"), "w", newline="") as f, \
            open(os.path.join(out_dir, "commands_rule_labels.csv"), "w", newline="") as g:
        w, k = csv.writer(f, lineterminator="\n"), csv.writer(g, lineterminator="\n")
        w.writerow(["sample_id", "run_id", "turn", "command", "exit_code", "output_head",
                    "human_label"])
        k.writerow(["sample_id", "rule_primary", "rule_flags"])
        for i, (rid, rec) in enumerate(sample, 1):
            sid = f"C{i:03d}"
            w.writerow([sid, rid, rec["turn"], rec["command"], rec["exit_code"],
                        rec["output"][:600], ""])
            k.writerow([sid, rec["primary"], _flags(rec)])
    completed = [(rid, recs, m) for rid, (r, recs, m) in sorted(coded.items())
                 if m["exit_reason"] == "completed"]
    pick = rng.sample(completed, min(30, len(completed)))
    with open(os.path.join(out_dir, "completion_to_check.csv"), "w", newline="") as f, \
            open(os.path.join(out_dir, "completion_rule_labels.csv"), "w", newline="") as g:
        w, k = csv.writer(f, lineterminator="\n"), csv.writer(g, lineterminator="\n")
        w.writerow(["sample_id", "run_id", "last_15_records", "human_unsupported_done"])
        k.writerow(["sample_id", "rule_unsupported_done", "rule_U_lenient", "rule_no_edit"])
        for i, (rid, recs, m) in enumerate(pick, 1):
            sid = f"R{i:03d}"
            lines = []
            for rec in recs[-15:]:
                c = " ".join(rec["command"].split())[:300]
                o = " ".join(rec["output"].split())[-300:]
                lines.append(f"[turn {rec['turn']} rc={rec['exit_code']}] $ {c}\n    -> {o}")
            w.writerow([sid, rid, "\n".join(lines), ""])
            k.writerow([sid, "" if m["unsupported_done"] is None else m["unsupported_done"],
                        "" if m["U_lenient"] is None else m["U_lenient"], m["no_edit"]])
    print(f"wrote {len(sample)} command samples and {len(pick)} completion samples to {out_dir}")


def score_labels(out_dir=None) -> dict:
    out_dir = str(out_dir or (OUT_DIR / "labels"))

    def read(name):
        with open(os.path.join(out_dir, name), newline="") as f:
            return {r["sample_id"]: r for r in csv.DictReader(f)}

    res = {}
    h, k = read("commands_to_label.csv"), read("commands_rule_labels.csv")
    pairs = [(h[s]["human_label"].strip(), k[s]["rule_primary"]) for s in h
             if h[s]["human_label"].strip() and s in k]
    res["V1"] = {"n": len(pairs), "kappa": cohen_kappa([a for a, _ in pairs], [b for _, b in pairs]),
                 "agreement": _mean([float(a == b) for a, b in pairs])}
    h, k = read("completion_to_check.csv"), read("completion_rule_labels.csv")
    pairs = [(h[s]["human_unsupported_done"].strip(), k[s]["rule_unsupported_done"]) for s in h
             if h[s]["human_unsupported_done"].strip() and k.get(s, {}).get("rule_unsupported_done", "") != ""]
    res["V2"] = {"n": len(pairs), "kappa": cohen_kappa([a for a, _ in pairs], [b for _, b in pairs]),
                 "agreement": _mean([float(a == b) for a, b in pairs])}
    with open(os.path.join(out_dir, "validation.json"), "w") as f:
        json.dump(res, f, indent=2)
    print(json.dumps(res, indent=2))
    return res


# --------------------------------------------------------------------------
# Development-subset coverage
# --------------------------------------------------------------------------

def dev_coverage():
    """Instrument coverage on repeat 1 of every cell. Opens only those runs."""
    rows = [r for r in load_rows() if r["repeat"] == 1]
    tot = Counter()
    other = Counter()
    outcomes = Counter()
    nf = Counter()
    unknown_cases = []
    for r in rows:
        recs, _ = load_exec(r["dir"])
        ws_status = patch_status(os.path.join(r["dir"], "workspace.patch"))
        records, info = code_records(recs, ws_status, ref_existing(r["task_id"]),
                                     package_root(r["task_id"]))
        tot["runs"] += 1
        tot["records"] += len(records)
        tot["records_primary_other"] += sum(rec["primary"] == "other" for rec in records)
        for k in ("n_segments", "n_other_segments", "n_paths_written", "n_unknown_existence",
                  "unresolved_edit_targets", "py_unresolved_writes", "parse_failures"):
            tot[k] += info[k]
        other.update(info["other_progs"])
        outcomes.update(info["test_outcomes"])
        nf.update(s["prog"] for rec in records for s in rec["segs"] if s.get("not_found"))
        tot["malformed_records"] += sum(rec["malformed"] for rec in records)
        tot["source_new_paths"] += sum(1 for v in info["subkind"].values() if v == "source_new")
        unknown_cases += [p for p, e in info["existence"].items() if e == "unknown"]
    print(f"development subset: {tot['runs']} runs, {tot['records']} exec records, "
          f"{tot['n_segments']} segments")
    print(f"  segments classed other: {tot['n_other_segments']} "
          f"({tot['n_other_segments'] / max(1, tot['n_segments']):.1%})")
    print(f"  records with primary class other: {tot['records_primary_other']} "
          f"({tot['records_primary_other'] / max(1, tot['records']):.1%})")
    print(f"  programs of other segments: {dict(other.most_common(15))}")
    print(f"  repo paths written: {tot['n_paths_written']}; existing/new unresolvable: "
          f"{tot['n_unknown_existence']} {sorted(set(unknown_cases))}")
    print(f"  edit segments with no resolvable target: {tot['unresolved_edit_targets']}; "
          f"python writes with unresolved target: {tot['py_unresolved_writes']}")
    print(f"  parse failures (unclosed quote / unterminated heredoc): {tot['parse_failures']} "
          f"in {tot['malformed_records']} records")
    n_test = sum(outcomes.values())
    print(f"  test segments: {n_test}; outcome unknown: {outcomes['unknown']} "
          f"({outcomes['unknown'] / max(1, n_test):.1%})")
    print(f"  command-not-found segments: {dict(nf)}")
    print(f"  paths coded edit:source_new: {tot['source_new_paths']}")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--dev-coverage" in argv:
        dev_coverage()
        return 0
    if "--make-label-sheets" in argv:
        make_label_sheets()
        return 0
    if "--score-labels" in argv:
        score_labels()
        return 0
    rows = compute_all()
    write_metrics_csv(rows, str(OUT_DIR / "metrics.csv"))
    validated = os.path.isfile(OUT_DIR / "labels" / "validation.json")
    an = analyse(rows, validated=validated)
    with open(OUT_DIR / "analysis.json", "w") as f:
        json.dump(_jsonable(an), f, indent=2)
    print_summary(an)
    print(f"\nwrote {OUT_DIR / 'metrics.csv'} and {OUT_DIR / 'analysis.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
