# Task dataset

Each subdirectory is one **task** — a real, self-contained coding problem taken from an
actual merged pull request, packaged so an agent can attempt it and be graded objectively.
A task folder holds: `prompt.md` (the problem the agent sees, leakage-stripped), `gold.patch`
(the human reference solution), `test.patch` (the hidden tests), and `task.json` (metadata +
the `fail_to_pass` / `pass_to_pass` test lists that define "solved"). The repo is pinned at
`base_commit` (the broken state) via a per-task Docker image.

## Provenance

Tasks come from **two sources**:

- **SWE-bench Verified** — imported 1:1 via `openbench import-swebench` (human-curated,
  known-solvable; older PRs).
- **Mined from GitHub** — built by openbench's own pipeline (`openbench mine → build-task →
  validate`) from recent, long PRs merged on/after the `min_merged_at` cutoff (2025-06-01;
  see `configs/mining.yaml`).

| task_id | repo | PR | source | PR merged | F2P / P2P |
|---|---|---:|---|---|---:|
| `sympy__sympy-13757` | sympy/sympy | [13757](https://github.com/sympy/sympy/pull/13757) | SWE-bench Verified | (pre-2023) | 1 / 166 |
| `sympy__sympy-22914` | sympy/sympy | [22914](https://github.com/sympy/sympy/pull/22914) | SWE-bench Verified | (pre-2023) | 1 / 17 |
| `sympy__sympy-23534` | sympy/sympy | [23534](https://github.com/sympy/sympy/pull/23534) | SWE-bench Verified | (pre-2023) | 1 / 11 |
| `sympy__sympy-23950` | sympy/sympy | [23950](https://github.com/sympy/sympy/pull/23950) | SWE-bench Verified | (pre-2023) | 1 / 4 |
| `pydantic__pydantic-11991` | pydantic/pydantic | [11991](https://github.com/pydantic/pydantic/pull/11991) | mined (GitHub) | 2025-07-10 | 0 / 0 |
| `scikit-learn__scikit-learn-32659` | scikit-learn/scikit-learn | [32659](https://github.com/scikit-learn/scikit-learn/pull/32659) | mined (GitHub) | 2025-11-26 | 8 / 0 |
| `sympy__sympy-28109` | sympy/sympy | [28109](https://github.com/sympy/sympy/pull/28109) | mined (GitHub) | 2025-07-27 | 44 / 500 |
| `sympy__sympy-28318` | sympy/sympy | [28318](https://github.com/sympy/sympy/pull/28318) | mined (GitHub) | 2025-08-20 | 12 / 500 |
| `sympy__sympy-28325` | sympy/sympy | [28325](https://github.com/sympy/sympy/pull/28325) | mined (GitHub) | 2025-08-28 | 11 / 500 |
| `sympy__sympy-28326` | sympy/sympy | [28326](https://github.com/sympy/sympy/pull/28326) | mined (GitHub) | 2025-09-18 | 11 / 498 |
| `sympy__sympy-29112` | sympy/sympy | [29112](https://github.com/sympy/sympy/pull/29112) | mined (GitHub) | 2026-02-08 | 1 / 177 |
| `sympy__sympy-29263` | sympy/sympy | [29263](https://github.com/sympy/sympy/pull/29263) | mined (GitHub) | 2026-02-28 | 1 / 417 |

**Summary:** 4 SWE-bench Verified · 8 mined from GitHub = 12 in the table above.

> **Note:** this table predates the repo-diversity import and is partial — many more
> SWE-bench Verified tasks (astropy, matplotlib, xarray, pytest, sphinx, scikit-learn,
> sympy) now live in this directory. Use `openbench list-tasks` for the authoritative
> current inventory.

### How source was determined (and a caveat)

`task.json` has **no explicit `source` field**, so the table above is reconstructed from:
- SWE-bench imports carry a `task.json` `merged_at` equal to the *import* date, not the
  real PR merge — a tell of import;
- mined tasks carry authentic 2025–2026 merge dates ≥ the mining cutoff, high PR numbers, and
  long-PR profiles (large `pass_to_pass` suites).

> **Recommended:** add a `source` field to `Task`/`task.json` (e.g. `"swebench-verified"` /
> `"mined"`) at import/build time so provenance is authoritative rather than inferred.
> This README should then be regenerated from that field.
