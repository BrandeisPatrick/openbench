# Run corpus — Kimi lineage backfill (August 2026)

kimi-k2-thinking (Moonshot, Nov 2025 vintage, open weights) on the 4 active
verified tasks × 3 repeats = 12 runs, giving the Kimi lineage a third point:
k2-thinking → k2.6 → k3. Run 2026-08-28 with the same harness and tooluse
protocol as the July corpora.

## Provenance

- Host: OpenRouter (`openrouter/moonshotai/kimi-k2-thinking`), NOT
  first-party Moonshot (the first-party API variant was discontinued
  2026-05-25). Host differs from the banked k2.6/k3 runs (first-party) —
  a named confound for cross-generation behavioral comparisons.
- Caps: 100 turns, $2.00, 4 h wall. No run hit any cap (all exited
  `completed`); total API cost ≈ $1.55.
- Grading: images golden-gated same day (all 4 PASS); fresh null controls
  same day graded NOT RESOLVED with P2P 100% green (specificity), see
  `data/runs-2026-08-null-controls/`.
- Leak scan: no git-history mining in any transcript (only `git stash`
  round-trips used for baseline test verification). Gold-patch similarity
  of solved runs (0.41 mean edit-set Jaccard) is in-family (k2.6 0.30,
  k3 0.44) — no gold-leak signal.

## Result summary (derived from grade.json, criterion: applies ∧ builds ∧
all F2P pass ∧ no P2P fail)

12/12 resolved (Pass@1 100%, all four cells 3/3).
