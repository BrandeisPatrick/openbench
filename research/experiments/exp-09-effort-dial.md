# exp-09 — Effort dial: do the measures move when we turn a dial we control?

Status: pre-registered 2026-11-14 (frozen by the same commit as exp-08, before any run of this round). Cost: part of the round 2 budget (see exp-08, "Round budget rule"). Depends on: everything exp-08 depends on.

Admission note. Descriptive, admitted under the 2026-11-11 discovery reframing. Tasks, harness settings, caps, exclusions, run order, measures M1–M15, the trend test and the budget rule are those of [exp-08](exp-08-opus-line.md) and are not repeated here.

## Question

Q1. With the model held fixed, which command-level measures respond to the reasoning-effort setting?

Why it is in the round. exp-08 can only find a trend the measures are able to see. Effort is a cause we set ourselves, so a measure that does not move when effort goes from `low` to `xhigh` has not been shown to be sensitive, and "no trend" in exp-08 for that measure says little. It also separates two readings of an exp-08 trend: newer models behave differently, or newer models simply think more at the same setting.

## Protocol source

- Effort as a manipulated condition: round 1 [exp-02](exp-02-effort-modes.md) (proposed, never run), here on one model only.
- Known-cause check of a measuring instrument: planted-pattern recall as used in exp-07 Part B and reviewed in `reports/Agent pattern discovery experiments.md`.

## Design

Model `claude-sonnet-5-5` at four effort levels, in order: `low`, `medium`, `high`, `xhigh`. Everything else in the request is identical. `max` is left out: with 16000 output tokens per reply it risks cut-off replies, which would be an artifact of the harness.

4 levels × 6 tasks × 2 repeats = 48 runs. The `high` arm is also the Sonnet row of exp-10 (same condition, same runs, not a pooling of different conditions). Effort levels are separate conditions and are never merged into one cell.

## Analyses

A1. Variance split per measure with effort level in the place of model (level, task, level × task, repeat).

A2–A4. Trend test, sign agreement and shape exactly as exp-08 A2–A4, with the four effort levels as the ordered factor. Holm over M1–M15.

A5. **Thinking actually changed.** Thinking tokens per reply and replies ending with `max_tokens`, per level. If thinking tokens per reply do not rise from `low` to `xhigh` (same trend test, p < 0.05), the dial did not do what it says and the experiment is reported as uninformative (predictions are still scored and marked so).

A6. **Reading exp-08 through the dial** (descriptive): a table of the 15 measures with the exp-08 label (trend / candidate / none) beside the exp-09 label, and thinking tokens per reply by Opus generation.

## Decision rules (fixed)

- **responds to effort**: Holm-adjusted p < 0.05, at least four blocks have a sign, and at most one of them disagrees (the exp-08 rule).
- **candidate**: unadjusted p < 0.05 with the same sign condition.
- **not shown to respond**: otherwise.

For exp-08's "none" labels: where the measure responds to effort here, "none" is read as informative; where it does not, as "instrument not shown to be sensitive".

## Predictions (written before any run; never edited afterwards)

- P1. `n_cmds` rises with effort (responds or candidate).
- P2. `test_share` rises with effort (responds or candidate).
- P3. `backed_done` rises with effort (responds or candidate).
- P4. `reread_share` and `repeat_cmd_share` are not shown to respond.
- P5. Thinking tokens per reply rise with effort (A5 passes).
- P6. At least three of the 15 measures respond to effort.

## Caveats

Those of exp-08. In addition: one model only, so sensitivity is shown for Sonnet 5.5 and assumed, not shown, for the Opus models; four ordered levels with six tasks can confirm only consistent effects.
