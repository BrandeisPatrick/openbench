# exp-08 — Opus line: which habits move steadily across five Opus generations?

Status: pre-registered 2026-11-14 (frozen by the commit that adds this file, before any run of this round). Cost: part of the round budget below ($125 for exp-08, exp-09 and exp-10 together). Depends on: Docker task images, the `ant` login, `research/analysis/claude_round.py`.

Admission note. Descriptive on purpose, admitted under the owner's reframing of 2026-11-11 (openbench is for discovering agent behavior patterns, not for ranking). This file also holds everything the three experiments of round 2 share: tasks, harness settings, measures, the trend test, the budget rule. exp-09 and exp-10 refer to it.

Why a new round. Round 1 (exp-00 to exp-07) had three generations per lab. A perfectly ordered line through three points appears by chance one time in three, so no cross-generation trend could be established, and exp-07 found none. Its labs were also served by different hosts with different settings, and three of its four tasks came from one library. Round 2 uses one lab, one API, one request shape, five ordered generations and tasks from six libraries.

## Questions

Q1. Across five consecutive Opus generations under identical request settings, which command-level measures move steadily with generation?
Q2. Inside one model family, which measures are a habit of the model at all (more variation between models than between repeats)?
Q3. (Part B) Which behaviors separate the oldest generation from the newest when a reader is asked openly, and do the three generations in between fall in order?

## Protocol source

- Measures and their sources: exp-07 (Mehtiyev & Assunção 2604.02547; Bouzenia & Pradel 2506.18824; Hu et al. 2609.30725; Majgaonkar et al. 2511.00197; Chen, Sun et al. 2602.07900; Advani 2606.09863).
- Ordered-alternative test with blocks: Page (1963), "Ordered hypotheses for multiple treatments", JASA 58:216–230, used here with a within-block permutation null.
- Contrastive discovery with a held-out check (Part B): VibeCheck and Docent, as reviewed in `reports/Agent pattern discovery experiments.md`; proposals are made on one split and tested on another.
- Clustering and multiplicity: Miller (2411.00640); HypotheSAEs (2502.04382).

## Design shared by round 2

**Harness.** Runner `claude-native` (Anthropic Messages API, called from the host; task container has no network). Same system prompt (`SYSTEM_PROMPT_TOOLUSE`), same single `bash` tool and same one-command-per-turn loop as round 1. Request body, identical for every run: `max_tokens` 16000, `thinking: {"type": "adaptive", "display": "summarized"}`, `output_config: {"effort": E}`, top-level `cache_control: {"type": "ephemeral"}` (billing only; content and order unchanged). No other parameter is sent. All eleven (model, effort) pairs of the round were accepted by the API in a two-turn check on 2026-11-13 before this file was frozen.

**One command per turn.** When a reply holds more than one tool call, the harness runs the first and answers the others with "skipped: the harness executes only the first tool call per turn" (the round 1 rule for OpenAI-style providers, now also on this runner). The number of tool calls per reply is logged.

**Tasks.** Six tasks from six libraries, chosen by a rule that uses no model outcome. Candidates are the tasks labelled "15 min - 1 hour" in `datasets/tasks/`, two per library in task-id order, plus the fixed bridge task `sympy__sympy-13757` (27 stored round 1 runs). A candidate is accepted when its image builds, `openbench validate` accepts it, a golden run grades resolved, a null run grades unresolved, and the task's test command starts inside the image. Per library the first accepted candidate is used. The imported fail-to-pass and pass-to-pass lists are used unchanged: a candidate whose golden run does not grade resolved with them is rejected, not repaired. Dependency pins and system packages of the image are set per task and recorded in its `task.json`. The round uses the bridge task plus the first five libraries, in the order astropy, matplotlib, xarray, pytest, scikit-learn, sphinx, that have an accepted task.

TASKS (filled from the acceptance log before the freeze, never changed afterwards): see "Frozen task list" at the end of this file.

**Repeats.** 2 per cell.

**Caps.** 100 turns (as round 1), 3600 s wall clock, and a per-run dollar cap that is a safety net, not a design element: Opus $6, Fable $8, Sonnet $3, Haiku $1. Runs ending by a cap are kept, flagged and analysed as they are.

**Exclusions.** Only harness failures: exit `crash` (API or container failure). A crashed run is rerun once. No run is excluded for its behavior or its result.

**Order.** The round runs task by task, in the order of the frozen task list. The reason is practical: the owner set a 10 GB disk budget for this round on 2026-11-14, and that holds one task image at a time. For each task, its image is built from the frozen commit and must pass a golden run (resolved) and a null run (unresolved) again before any of its runs start; then all of the task's cells are run and the image is deleted. Inside one task the stages go in stage order (see the budget rule). Inside one stage, the task's repeat-1 cells run in shuffled order (seed 20261113), then its repeat-2 cells in shuffled order, three runs at a time, so that every cell of the stage has one run before any has two and no model's runs sit together.

Consequence: task and calendar time go together. Every test of this round compares conditions inside a task (tasks are the blocks), where the runs of all conditions fall within the same few hours. Differences between tasks are not interpreted.

**Provenance.** Runs are frozen in `research/corpus/runs-2026-11-claude-round/` with a README (model ids, effort, dates, image ids, harness commit).

## Design of exp-08

Models, in release order (generation rank 1 to 5; release dates from the Models API): `claude-opus-4-6` (2026-02-04), `claude-opus-4-7` (2026-04-14), `claude-opus-4-8` (2026-05-28), `claude-opus-5` (2026-07-24), `claude-opus-5-5` (2026-09-21). Effort `high` for all five: it is the highest level every one of them accepts besides `max`. Opus 4.5 is left out because it does not accept adaptive thinking, so its request body would differ.

5 models × 6 tasks × 2 repeats = 60 runs.

## Measures (`research/analysis/command_audit.py` for M1–M13 and U, frozen in commit `9704517`; `research/analysis/claude_round.py` for the rest)

M1–M13 exactly as defined in exp-07: `n_cmds` (log), `first_edit_frac`, `early_edit_share`, `test_share`, `exec_share`, `wrote_new_test`, `wrote_scratch_script`, `repeat_cmd_share`, `noop_retest_share`, `reread_share`, `search_miss_share`, `extra_files`, `patch_lines` (log1p).

| id | name | definition |
|---|---|---|
| M14 | `backed_done` | 1 if the run exits `completed`, made at least one source edit, and a passing test segment comes after its last change (exp-07's U is 0); 0 in every other case, including runs that do not complete, completed runs with no change, and runs whose test outcome cannot be read. Defined for every run. |
| M15 | `multi_call_share` | share of the run's replies that hold more than one tool call (replies with a logged tool-call count; undefined for round 1 transcripts, which have none) |

**Source roots.** The frozen coding rules know a library's source folder only for sympy (`sympy/`) and pytest (`src/`). For this round the roots are passed in per library, with no change to the rules: `astropy/`, `lib/matplotlib/`, `xarray/`, `sklearn/`, `sphinx/`.

U (`unsupported_done`, completed runs with an edit only) is reported as in exp-07 but is not in the tested family, because it is undefined for some runs.

Context, reported but not tested: `resolved`, exit reason, turns, thinking tokens per reply, output tokens per reply, replies ending with `max_tokens`, cost.

## Analyses

A1. **Variance split** per measure over the 60 runs (model, task, model × task, repeat), as exp-07 A1, with the exp-07 labels (model habit / task-dependent / repeat noise) and thresholds unchanged, and Holm over the 15 measures. If the layout is unbalanced, the tests use the tasks where every level has both runs, the dropped tasks are listed, and shares over all runs are reported beside them without tests.

A2. **Trend test** per measure (Page's L with a permutation null). Blocks are tasks. The cell value is the mean over the cell's runs. Within each block the five cell values are ranked (mid-ranks for ties). L = Σ_g g · R_g, where R_g is the rank sum of generation g. Statistic: |L − E0|, E0 = b·k·(k+1)²/4 for b blocks and k levels. Null: generation labels permuted within each block independently, 10,000 draws, seed 20261113; p = (1 + number of draws at least as extreme) / 10,001. Two-sided. Holm correction over the 15 measures M1–M15. Every measure's test starts a fresh generator from that seed. A cell's run is its latest attempt that did not end `crash` or `interrupted`. A block in which some level has no run is dropped for that measure; a measure with fewer than four complete blocks is not tested and leaves the Holm family. A measure with no variation is tested (p = 1) and stays in the family.

A3. **Sign agreement.** Per block, Spearman correlation between generation rank and cell value. A block whose cell values are all equal, or whose correlation is exactly 0, has no sign and is left out of the count: it says nothing about direction. When L equals E0 there is no direction and the label is none. Reported: blocks agreeing with the sign of L − E0, blocks disagreeing, blocks with no sign.

A4. **Shape** (descriptive, for measures labelled trend or candidate): cell values are centered per task and averaged per generation; `step-like` when the best single split of the ordered generations accounts for at least 90% of the between-generation sum of squares, else `gradual` (a straight ramp scores 75% with five levels and 80% with four; a pure step scores 100%).

A5. **Profile drift.** Nearest-centroid identification on the 15 z-scored measures, leave-one-task-out (chance 20%). Then the mean absolute difference between predicted and true generation rank, against a null that permutes model labels within task (10,000 draws, seed 20261113 + 500; one-sided, smaller is more extreme). Identification counts as above chance when accuracy exceeds the 95th percentile of the same null. A small rank error means runs are confused with neighboring generations, which is what a steady drift of the whole profile predicts.

A6. **Outcome check.** `resolved` per cell. If the resolved rates of the generations are not all equal, every measure labelled trend is recomputed on resolved runs only (unadjusted p and sign counts, no label) and both versions are reported.

A7. **Bridge** (descriptive only): the Opus runs on `sympy__sympy-13757` beside the 27 stored round 1 runs on the same task. Different providers, settings and dates; no test.

## Decision rules (fixed)

- **trend**: Holm-adjusted p < 0.05, at least four blocks have a sign, and at most one of them disagrees with the direction of L.
- **candidate**: unadjusted p < 0.05 and the same sign condition, but Holm-adjusted p ≥ 0.05. Named for a later round; not a finding.
- **none**: otherwise.

A result of "none" for every measure is a valid outcome and is reported as such. Measures that take only two values (M6, M7, M14) have cell means of 0, 0.5 or 1 with two repeats, so they need large, consistent differences to pass.

## Predictions (written before any run; never edited afterwards)

These are the author's guesses, from exp-07 and from vendor release notes, not from any run of this round.

- P1. `backed_done` rises with generation (trend or candidate).
- P2. `test_share` rises with generation (trend or candidate).
- P3. `n_cmds` shows no trend: run length is a per-model quirk, as in exp-07.
- P4. `early_edit_share` is near zero for all five models, so it cannot show a trend.
- P5. `multi_call_share` falls with generation (older models in the settings check sent two calls in one reply more often).
- P6. At least one and at most three of the 15 measures are labelled trend.
- P7. A5: identification is above chance, and the rank error is below its null (p < 0.05).

How predictions are scored, here and in exp-09 and exp-10: "trend or candidate" (or "responds or candidate", "moves or candidate") holds when the label is one of the two and the direction is the predicted one; "no trend", "no ordered pattern" and "not shown to respond" hold only when the label is none; "near zero" means every level's mean is at most 0.05; "the lowest" means strictly lowest.

## Part B — open contrast between the endpoints (judge budget reserved: $10)

Run after Part A is written up. The judge code is committed before any judge call of this round. Judge model: `claude-sonnet-5-5` (not one of the five subjects), adaptive thinking, effort medium. Model identities are hidden from the judge (the meta record is stripped, runs are called A and B).

- B1 **Propose.** Discovery tasks are the first three of the frozen task list. For each discovery task and repeat, the judge reads one Opus 4.6 run and one Opus 5.5 run (commands, shortened outputs, thinking summaries) in both A/B orders and lists differences in how the two work that could be checked from a log. 12 calls.
- B2 **Freeze.** One call merges the proposals into at most 12 candidate behaviors, each with a yes/no rule for one run. The list is committed before any labelling.
- B3 **Label.** Every run of the three held-out tasks, all five generations (30 runs), each candidate yes/no, twice with independent calls. Agreement between the two passes is reported (Cohen's κ per candidate); a candidate with κ < 0.6 is reported as unreliable and not tested.
- B4 **Test.** Per candidate, the A2 trend test over the five generations with the three held-out tasks as blocks (the four-block minimum of A2 does not apply here; all three blocks must be complete). The cell value is the mean of the yes answers over both runs and both passes. A candidate is labelled trend when Holm-adjusted p < 0.05 over the tested candidates, at least two blocks have a sign and none disagrees. The count table is reported for every candidate. With three blocks the test can only confirm strong patterns; everything else is reported as a candidate.

## Round budget rule (shared by exp-08, exp-09, exp-10)

- **Ceiling.** $125.00 of API spend at list prices, counted from 2026-11-13 and including checks, the pilot, every run (also crashed ones) and judge calls. Spent before the freeze: $0.09.
- **Start rule.** A run starts only if spent + the dollar caps of the runs in flight + its own cap ≤ $125 minus the unspent Part B reserve.
- **Pilot.** Repeat 1 of every model at effort `high` on the bridge task (5 Opus, Sonnet 5.5, Haiku 5.5, Fable 5.2): 8 runs. They are real data of their cells.
- **Projection.** Remaining cost = Σ over remaining runs of that model's pilot cost (× 1.3 for effort `xhigh`). If pilot + projection + reserve exceeds the ceiling, drop in this order until it fits: Fable from exp-10; all of exp-10; exp-09; Part B; the last task of the frozen list from exp-08. Every drop is recorded in the results file.
- **Stage order.** The pilot first (it is on the bridge task, the first task of the frozen list), then the projection and its drops. After that, for each task in turn: rest of exp-08, exp-09, exp-10 Haiku, exp-10 Fable. Part B last. If the start rule stops the round early, it is therefore the last tasks of the frozen list that lose runs, the later stages first; a task in which some level has no run is handled as A2 says (the block is dropped for that test).
- **Nothing is added** after the freeze, whatever is left of the budget.

## Validation

- V1. **Coverage of the coding rules on Claude's commands.** Per model: share of commands classed `other` and share of edits of kind `unknown`. Above 15% for a model, its measures are flagged as unreliable in every table.
- V2. **Runner start.** Per task: runs whose first test command fails because the test runner itself cannot start. A task where this happens in half the runs or more is reported separately and dropped from the blocks, as the pytest task was in exp-07.
- V3. The coding rules themselves are still unchecked against hand labels (exp-07 V1/V2 pending). Until then every result of this round carries "unvalidated instrument".

## Caveats

- Six tasks, two repeats: only strong, consistent trends can pass. Absence of a trend here is weak evidence of absence.
- The tasks are public SWE-bench Verified issues from before 2023. Every model here may have seen them and their fixes in training, newer ones possibly more.
- The same effort name is not the same amount of thinking on every model (levels were recalibrated on Opus 5.5). Thinking tokens per reply are reported so that this is visible.
- Thinking text is a summary written by the API, not the raw reasoning; Part A does not read it.
- All runs happen within a few days through one account; a later rerun may differ if a model is updated server-side.
- One harness, one prompt, one tool. Habits may not carry over to another scaffold.

## Frozen task list

1. `sympy__sympy-13757` (bridge task)
2. `astropy__astropy-12907`
3. `pydata__xarray-2905`
4. `pytest-dev__pytest-10051`
5. `scikit-learn__scikit-learn-10297`
6. `sphinx-doc__sphinx-10466`

Part B: discovery tasks are 1 to 3, held-out tasks are 4 to 6.

Acceptance log (2026-11-13 and 2026-11-14; no model run was involved):

| candidate | verdict | note |
|---|---|---|
| `sympy__sympy-13757` | accepted | bridge task |
| `astropy__astropy-12907` | accepted | |
| `matplotlib__matplotlib-14623` | rejected | golden run unresolved: half of the imported pass-to-pass list fails with the reference fix applied |
| `matplotlib__matplotlib-20488` | rejected | golden run unresolved with the imported lists: two pass-to-pass ids are cut off at a space in the dataset and one test needs the network. It resolves only after editing the list, which the rule does not allow |
| `pydata__xarray-2905` | accepted | |
| `pytest-dev__pytest-10051` | accepted | |
| `scikit-learn__scikit-learn-10297` | accepted | |
| `sphinx-doc__sphinx-10466` | accepted | |

matplotlib has no accepted task, so the five libraries after the bridge task are astropy, xarray, pytest, scikit-learn and sphinx. The second candidates of the other libraries were not needed and not tried.

How `openbench validate` was run: SWE-bench imports carry no merge commit, so validate's "merged" container had the task's gold and test patch applied to the base commit, and the fail-to-pass candidates were seeded with the task's own list. Nothing else in validate was changed.
