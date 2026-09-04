# exp-03 — Teacher-inheritance test: does k3 carry the specialist lineage's procedures?

Status: proposed. Cost: $0 (existing traces). Better after the host-matched Kimi rerun.

## Claim tested

Kimi K3 was distilled from in-house specialist teachers descended from the
reasoning-specialist line (k2-thinking) rather than trained onward from the
generalist k2.6 alone. Conditional: the teachers are in-house, not
k2-thinking itself; the test detects inheritance of the specialist lineage's
habits, not of one public checkpoint.

## Protocol source

AgentEcho ([2604.21255](https://arxiv.org/abs/2604.21255), code released):
Response Pattern Similarity (verbal) and Action Graph Similarity (AGS =
node, sequence and dependency similarity of tool-use graphs) between agents'
trajectories on the same tasks. Within-family pairs score 5.9 pp higher AGS
than cross-family pairs, and a controlled distillation experiment shows AGS
separates teacher-specific convergence from general improvement.

Adaptation: our actions are shell commands, not typed tool calls. Nodes =
action classes (explore / edit / verify / navigate / utility), sequences =
ordered class strings, dependencies = file-level edges (edit file → later
test touching the file).

## Design

- Existing traces: k2-thinking, k2.6, k3 on the 4 tasks × 3 repeats; all
  other models as the background distribution of cross-model similarities.
- Statistic: Δ = AGS(k3, k2-thinking) − AGS(k3, k2.6), per task, compared
  with the spread of Δ-analogues across unrelated model pairs.
- Repeat after the host-matched Kimi rerun (all three generations on one
  host) to remove the serving confound on k2-thinking.

## Measures (`analysis/agent_echo.py`)

AGS components per the paper, computed per task between every model pair;
RPS on visible messages only (summaries excluded).

## Predictions

- Inheritance: Δ > 0 on most tasks by more than the cross-model spread — k3
  works like the specialist more than like its immediate predecessor.
- Null: Δ ≈ 0 or negative — k3 is closest to k2.6, the ordinary
  successor pattern.

## Decision rule (fixed)

"Inheritance" iff Δ > 0 on ≥ 3 of 4 tasks and mean Δ exceeds the 90th
percentile of unrelated-pair Δ-analogues. Otherwise null.

## Caveats

k2-thinking's byte-identical patches raise its self-similarity, not its
similarity to others; the statistic is cross-model so this does not inflate
Δ. Host difference for k2-thinking is a named confound until the rerun.
