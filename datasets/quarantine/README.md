# Quarantined tasks

Tasks moved out of `datasets/tasks/` after failing a fairness audit
(2026-07-08; in-container replays of the best agent patches against the hidden
tests). They must not be used in studies. Their run traces were pruned from
the frozen corpora on 2026-08-31 (never part of any reported result); the
audit evidence remains in git history at commit 425cd54 under
`data/runs-2026-07-generational-study/`.

Common root cause: **none of the three ever passed the validation gate**
(`validation` empty in task.json), and the gate at the time did not check the
failure modes below. Rule going forward: no task enters a study without a green
`openbench validate`.

## scikit-learn__scikit-learn-32659 — MIXED / salvageable with data fixes

- 3 of 8 FAIL_TO_PASS tests pass on the **unmodified base** + test.patch (free
  points; an empty patch scores 3/8).
- 3 of the 5 discriminating tests assert the gold PR's exact warning strings —
  agents failed for writing "'penalty' **is** deprecated" where gold wrote
  "**was** deprecated" (in-file precedent uses "is"; repo convention is mixed).
- The task image leaked the solution via git history (post-base commits,
  including the gold merge commit, survive in the clone); one agent run mined
  it with `git diff <merge>^..<merge>` and copied gold strings verbatim.
  Leak closed at run time in d96cced (agents now get a single-commit repo).
- To salvage: rebuild the F2P list from base-failing tests only, quote the
  required warning wording in prompt.md (or relax the asserts), re-validate.

## sympy__sympy-29263 — MISPOSED / do not salvage

The single F2P test does exact-expression equality against the gold
implementation's internal output AST. The best agent patch produced an
antiderivative **symbolically identical** to gold (`simplify(gold - agent) == 0`,
derivative check passes) and fully fixed the prompt's reproducer — and scored
0/1. The test also demands a degenerate branch unreachable under the prompt's
own `a > 0` assumption and exact forms for two integrand families the prompt
never mentions. (Separately: 3 P2P tests that failed on the unmodified base
were removed in 89b451b.)

## sympy__sympy-28318 — MISPOSED at any budget / do not salvage

The hidden tests import `create_transfer_function`, a factory name the
2,236-char prompt never states; the ImportError aborts pytest collection, so
all 12 F2P ids fail wholesale — including one that passes in isolation against
the best agent patch. The remaining tests additionally require an unprompted
default (`sampling_time=1`), exact LaTeX/pretty-print strings, and the PR's
full ~4,300-line class-hierarchy refactor.
