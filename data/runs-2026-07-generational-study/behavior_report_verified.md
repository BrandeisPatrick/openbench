# Generational behavior comparison

> **Corpus restricted to `source == swebench-verified` tasks.**

> **Read me first.** This is a *descriptive* comparison, not hypothesis
> confirmation: n per model is small and the true degrees of freedom are the
> number of tasks, so every interval is a task-clustered bootstrap and the
> per-task sign agreement matters more than any single number. Contrasts are
> within-lab only (same wire protocol per pair — scaffold effects cancel);
> cross-lab differences are confounded by protocol and pricing. Solve rates
> are stratified by task provenance because SWE-bench-Verified PRs predate
> every model's training cutoff while mined PRs postdate the old generation's.

![Paired deltas](figures/paired_deltas.png)

![Axis radar](figures/axis_radar.png)

![Efficiency frontier](figures/efficiency_frontier.png)

![Pass trajectories](figures/pass_trajectories.png)

![Outcome composition](figures/outcome_composition.png)

## deepseek: `openrouter/deepseek/deepseek-chat-v3-0324` → `deepseek-v4-pro`

Runs: 12 old / 12 new (crashes excluded: 1 / 1)

### Solve rate

- **overall**: 0/12 → 12/12 (Δ 1.00 (95% CI [+1.00, +1.00]))
- **swebench-verified**: 0/12 → 12/12 (Δ 1.00 (95% CI [+1.00, +1.00]))

### What changed (headline effects)

- `re_read_rate` [exploration] ↑ — δ 1.00 (CI [+1.00, +1.00]), 3/3 tasks ↑; median 0.00 → 0.68
- `file_jaccard` [efficiency] ↑ — δ 0.92 (CI [+0.75, +1.00]), 4/4 tasks ↑; median 0.00 → 1.00
- `malformed_action_rate` [failure_modes] ↓ — δ -0.92 (CI [-1.00, -0.75]), 4/4 tasks ↓; median 1.00 → 0.00
- `test_run_rate` [verification] ↑ — δ 0.83 (CI [+0.50, +1.00]), 4/4 tasks ↑; median 0.00 → 0.15
- `green_observed` [verification] ↑ — δ 0.83 (CI [+0.50, +1.00]), 3/4 tasks ↑; median 0.00 → 1.00
- `files_explored` [exploration] ↑ — δ 0.83 (CI [+0.58, +1.00]), 4/4 tasks ↑; median 0.00 → 3.50
- `cost_usd` [efficiency] ↑ — δ 0.83 (CI [+0.62, +1.00]), 4/4 tasks ↑; median 0.05 → 0.29
- `verified_before_done` [verification] ↑ — δ 0.58 (CI [+0.17, +0.92]), 3/4 tasks ↑; median 0.00 → 1.00
- `grind_to_cap` [persistence] ↓ — δ -0.58 (CI [-0.83, -0.33]), 2/4 tasks ↓; median 1.00 → 0.00
- `exploration_fraction` [exploration] ↓ — δ -0.57 (CI [-0.88, -0.25]), 4/4 tasks ↓; median 1.00 → 0.47

### Full delta table

| axis | metric | old median | new median | Cliff's δ | 95% CI | tasks agree | n |
|---|---|---:|---:|---:|---|---|---|
| verification | `test_run_rate`** | 0.00 | 0.15 | 0.83 | [+0.50, +1.00] | 4/4 tasks ↑ | 12/12 |
| verification | `tested_before_first_edit` | 0.00 | 0.00 | 0.08 | [+0.00, +0.00] | 0/3 tasks ↑ | 4/12 |
| verification | `verification_loop_rate` | 0.10 | 1.00 | 0.83 | [-0.33, +1.00] | 2/3 tasks ↑ | 4/12 |
| verification | `verified_before_done`** | 0.00 | 1.00 | 0.58 | [+0.17, +0.92] | 3/4 tasks ↑ | 12/12 |
| verification | `green_observed`** | 0.00 | 1.00 | 0.83 | [+0.50, +1.00] | 3/4 tasks ↑ | 12/12 |
| persistence | `recovery_rate` | — | 1.00 | — | — | 0/0 tasks | 0/9 |
| persistence | `retry_verbatim_rate` | 0.00 | 0.00 | 0.00 | [+0.00, +0.00] | 0/3 tasks ↑ | 3/12 |
| persistence | `test_progress_rate` | 0.00 | 0.56 | 0.92 | — | 1/1 tasks ↑ | 1/12 |
| persistence | `gave_up_failing` | 0.00 | 0.00 | 0.25 | [+0.00, +0.33] | 0/2 tasks ↑ | 2/12 |
| persistence | `grind_to_cap`** | 1.00 | 0.00 | -0.58 | [-0.83, -0.33] | 2/4 tasks ↓ | 12/12 |
| persistence | `consecutive_failures_at_end` | 0.00 | 0.00 | 0.25 | [+0.00, +0.50] | 1/4 tasks ↑ | 12/12 |
| exploration | `exploration_fraction`** | 1.00 | 0.47 | -0.57 | [-0.88, -0.25] | 4/4 tasks ↓ | 12/12 |
| exploration | `search_before_edit_rate` | 1.00 | 1.00 | -0.29 | [-1.00, +0.00] | 1/3 tasks ↓ | 3/7 |
| exploration | `exploration_event_share` | 0.24 | 0.23 | 0.17 | [-1.00, +1.00] | 2/3 tasks ↓ | 5/12 |
| exploration | `files_explored`** | 0.00 | 3.50 | 0.83 | [+0.58, +1.00] | 4/4 tasks ↑ | 12/12 |
| exploration | `re_read_rate`** | 0.00 | 0.68 | 1.00 | [+1.00, +1.00] | 3/3 tasks ↑ | 3/12 |
| efficiency | `num_turns` | 100.00 | 27.50 | -0.22 | [-0.67, +0.33] | 2/4 tasks ↑ | 12/12 |
| efficiency | `total_tokens` | 364506.50 | 229913.00 | 0.01 | [-0.21, +0.38] | 3/4 tasks ↑ | 12/12 |
| efficiency | `cost_usd`** | 0.05 | 0.29 | 0.83 | [+0.62, +1.00] | 4/4 tasks ↑ | 12/12 |
| efficiency | `file_edit_count` | 0.00 | 1.00 | 0.45 | [+0.15, +0.83] | 3/4 tasks ↑ | 12/12 |
| efficiency | `turns_to_first_green` | — | 16.50 | — | — | 0/0 tasks | 0/10 |
| efficiency | `diff_size_ratio` | 0.00 | 1.00 | 0.35 | [-0.17, +0.83] | 3/4 tasks ↑ | 12/12 |
| efficiency | `file_jaccard`** | 0.00 | 1.00 | 0.92 | [+0.75, +1.00] | 4/4 tasks ↑ | 12/12 |
| efficiency | `out_of_scope_ratio` | 0.50 | 0.00 | -0.75 | [-1.00, +0.00] | 2/3 tasks ↓ | 4/12 |
| efficiency | `redundancy_rate` | 0.36 | 0.39 | -0.08 | [-1.00, +0.07] | 2/3 tasks ↓ | 4/12 |
| failure_modes | `confabulated_completion` | 0.00 | 0.00 | -0.25 | [-0.50, +0.00] | 1/4 tasks ↓ | 12/12 |
| failure_modes | `malformed_action_rate`** | 1.00 | 0.00 | -0.92 | [-1.00, -0.75] | 4/4 tasks ↓ | 12/12 |

### How runs end

| outcome | old | new |
|---|---:|---:|
| confabulated | 3 | 0 |
| grind_to_cap | 8 | 0 |
| other_fail | 1 | 0 |
| resolved | 0 | 12 |

## openai: `gpt-4.1` → `gpt-5.5`

Runs: 12 old / 12 new (crashes excluded: 8 / 3)

### Solve rate

- **overall**: 3/12 → 12/12 (Δ 0.75 (95% CI [+0.67, +0.92]))
- **swebench-verified**: 3/12 → 12/12 (Δ 0.75 (95% CI [+0.67, +0.92]))

### What changed (headline effects)

- `recovery_rate` [persistence] ↑ — δ 1.00 (CI [+1.00, +1.00]), 2/2 tasks ↑; median 0.00 → 1.00
- `num_turns` [efficiency] ↓ — δ -1.00 (CI [-1.00, -1.00]), 4/4 tasks ↓; median 84.00 → 22.00
- `re_read_rate` [exploration] ↓ — δ -0.93 (CI [-1.00, -0.58]), 4/4 tasks ↓; median 0.95 → 0.70
- `green_observed` [verification] ↑ — δ 0.92 (CI [+0.75, +1.00]), 4/4 tasks ↑; median 0.00 → 1.00
- `file_edit_count` [efficiency] ↓ — δ -0.90 (CI [-1.00, -0.75]), 4/4 tasks ↓; median 7.50 → 2.00
- `total_tokens` [efficiency] ↓ — δ -0.89 (CI [-1.00, -0.67]), 4/4 tasks ↓; median 1021792.00 → 161645.50
- `diff_size_ratio` [efficiency] ↓ — δ -0.83 (CI [-1.00, -0.50]), 4/4 tasks ↓; median 706.00 → 7.00
- `cost_usd` [efficiency] ↓ — δ -0.79 (CI [-1.00, -0.21]), 3/4 tasks ↓; median 2.07 → 0.51
- `redundancy_rate` [efficiency] ↓ — δ -0.76 (CI [-1.00, -0.50]), 4/4 tasks ↓; median 0.74 → 0.33
- `test_progress_rate` [persistence] ↑ — δ 0.74 (CI [+0.25, +1.00]), 3/4 tasks ↑; median 0.20 → 0.75
- `verified_before_done` [verification] ↑ — δ 0.58 (CI [+0.33, +0.83]), 3/4 tasks ↑; median 0.00 → 1.00

### Full delta table

| axis | metric | old median | new median | Cliff's δ | 95% CI | tasks agree | n |
|---|---|---:|---:|---:|---|---|---|
| verification | `test_run_rate` | 0.08 | 0.10 | 0.25 | [-0.33, +0.83] | 2/4 tasks ↑ | 12/12 |
| verification | `tested_before_first_edit` | 0.00 | 0.00 | 0.08 | [+0.00, +0.25] | 1/4 tasks ↑ | 12/12 |
| verification | `verification_loop_rate` | 0.61 | 0.63 | 0.22 | [+0.03, +0.44] | 3/4 tasks ↑ | 12/12 |
| verification | `verified_before_done`** | 0.00 | 1.00 | 0.58 | [+0.33, +0.83] | 3/4 tasks ↑ | 12/12 |
| verification | `green_observed`** | 0.00 | 1.00 | 0.92 | [+0.75, +1.00] | 4/4 tasks ↑ | 12/12 |
| persistence | `recovery_rate`** | 0.00 | 1.00 | 1.00 | [+1.00, +1.00] | 2/2 tasks ↑ | 6/6 |
| persistence | `retry_verbatim_rate` | 0.00 | 0.00 | 0.00 | [+0.00, +0.00] | 0/3 tasks ↑ | 12/9 |
| persistence | `test_progress_rate`** | 0.20 | 0.75 | 0.74 | [+0.25, +1.00] | 3/4 tasks ↑ | 11/9 |
| persistence | `gave_up_failing` | 0.00 | 0.00 | -0.45 | [-0.67, -0.20] | 2/4 tasks ↓ | 11/12 |
| persistence | `grind_to_cap` | 0.00 | 0.00 | -0.42 | [-0.83, -0.08] | 1/4 tasks ↓ | 12/12 |
| persistence | `consecutive_failures_at_end` | 0.00 | 0.00 | -0.42 | [-0.67, -0.17] | 2/4 tasks ↓ | 12/12 |
| exploration | `exploration_fraction` | 0.41 | 0.36 | 0.07 | [-0.50, +0.68] | 2/4 tasks ↑ | 12/12 |
| exploration | `search_before_edit_rate` | 1.00 | 0.80 | -0.33 | [-1.00, +0.00] | 1/3 tasks ↓ | 12/8 |
| exploration | `exploration_event_share` | 0.30 | 0.26 | -0.34 | [-0.47, -0.06] | 3/4 tasks ↓ | 12/12 |
| exploration | `files_explored` | 5.50 | 4.00 | -0.42 | [-0.68, -0.16] | 3/4 tasks ↓ | 12/12 |
| exploration | `re_read_rate`** | 0.95 | 0.70 | -0.93 | [-1.00, -0.58] | 4/4 tasks ↓ | 12/12 |
| efficiency | `num_turns`** | 84.00 | 22.00 | -1.00 | [-1.00, -1.00] | 4/4 tasks ↓ | 12/12 |
| efficiency | `total_tokens`** | 1021792.00 | 161645.50 | -0.89 | [-1.00, -0.67] | 4/4 tasks ↓ | 12/12 |
| efficiency | `cost_usd`** | 2.07 | 0.51 | -0.79 | [-1.00, -0.21] | 3/4 tasks ↓ | 12/12 |
| efficiency | `file_edit_count`** | 7.50 | 2.00 | -0.90 | [-1.00, -0.75] | 4/4 tasks ↓ | 12/12 |
| efficiency | `turns_to_first_green` | 81.00 | 13.50 | -1.00 | — | 1/1 tasks ↓ | 1/12 |
| efficiency | `diff_size_ratio`** | 706.00 | 7.00 | -0.83 | [-1.00, -0.50] | 4/4 tasks ↓ | 12/12 |
| efficiency | `file_jaccard` | 0.23 | 0.50 | 0.33 | [-0.27, +0.79] | 3/4 tasks ↑ | 12/12 |
| efficiency | `out_of_scope_ratio` | 0.78 | 0.50 | -0.33 | [-0.79, +0.27] | 3/4 tasks ↓ | 12/12 |
| efficiency | `redundancy_rate`** | 0.74 | 0.33 | -0.76 | [-1.00, -0.50] | 4/4 tasks ↓ | 12/12 |
| failure_modes | `confabulated_completion` | 0.00 | 0.00 | -0.33 | [-0.58, -0.08] | 1/4 tasks ↓ | 12/12 |
| failure_modes | `malformed_action_rate` | 0.00 | 0.00 | -0.33 | [-0.67, +0.00] | 2/4 tasks ↓ | 12/12 |

### How runs end

| outcome | old | new |
|---|---:|---:|
| confabulated | 4 | 0 |
| grind_to_cap | 5 | 0 |
| resolved | 3 | 12 |

## Pairs

- `deepseek`: openrouter/deepseek/deepseek-chat-v3-0324 → deepseek-v4-pro (deepseek)
- `gpt`: gpt-4.1 → gpt-5.5 (openai)
