# exp-10 — Size ladder: does a habit follow the generation or the size of the model?

Status: pre-registered 2026-11-14 (frozen by the same commit as exp-08, before any run of this round). Cost: part of the round 2 budget (see exp-08, "Round budget rule"); this experiment is the first to be cut if the budget is short. Depends on: everything exp-08 depends on.

Admission note. Descriptive, admitted under the 2026-11-11 discovery reframing. Tasks, harness settings, caps, exclusions, run order, measures M1–M15, the trend test and the budget rule are those of [exp-08](exp-08-opus-line.md).

## Question

Q1. Among current models of different size run the same way, which command-level measures move steadily with size?
Q2. For each measure that trends across Opus generations in exp-08: does it also move with size, and in the same direction as "newer"?

Why it is in the round. A trend across generations could be a change in how the lab trains its models, or simply what a more capable model does. Size is the nearest handle on capability that can be varied with the generation held roughly fixed.

## Design

Four current models at effort `high`, ordered by list input price as the stated proxy for size: `claude-haiku-5-5` ($0.10 per MTok), `claude-sonnet-5-5` ($2), `claude-opus-5-5` ($4), `claude-fable-5-2` ($8). Fable 5.2 is a separate product line released 2026-11-09, seven weeks after Opus 5.5; it is the top of the ladder, not a member of the 5.5 family, and every table says so.

New runs: Haiku and Fable, 2 models × 6 tasks × 2 repeats = 24. The Sonnet runs are the `high` arm of exp-09 and the Opus runs are the Opus 5.5 row of exp-08 (same request settings, same runs).

If the budget rule drops Fable, the ladder has three levels and is reported descriptively only, with no test: an ordered line through three points appears by chance one time in three.

## Analyses

A1. Variance split per measure (model, task, model × task, repeat).

A2–A4. Trend test, sign agreement and shape exactly as exp-08 A2–A4, with the four models as the ordered factor. Holm over M1–M15.

A5. **Generation against size** (descriptive): for each of the 15 measures, the exp-08 label and direction beside the exp-10 label and direction, read as:
- trend in both, same direction: the measure follows capability; generation and size cannot be separated.
- trend across generations, none across sizes: the measure follows the generation.
- trend across sizes, none across generations: the measure follows size.
- none in both: no ordered pattern found.
- a candidate label in either experiment: not classified.
- trend in both, opposite directions: reported as such, with no reading.

## Decision rules (fixed)

- **moves with size**: Holm-adjusted p < 0.05, at least four blocks have a sign, and at most one of them disagrees (the exp-08 rule).
- **candidate**: unadjusted p < 0.05 with the same sign condition.
- **none**: otherwise.

## Predictions (written before any run; never edited afterwards)

- P1. `backed_done` rises with size (moves or candidate).
- P2. `repeat_cmd_share` falls with size (moves or candidate).
- P3. `n_cmds` shows no ordered pattern.
- P4. Haiku 5.5 has the lowest `backed_done` of the four.
- P5. At least one of the 15 measures moves with size.

## Caveats

Those of exp-08. In addition: price is a proxy for size, and size a proxy for capability; the four models were released over five weeks to two months apart, so generation is only roughly fixed; Fable 5.2 carries extra safety measures that the others do not.
