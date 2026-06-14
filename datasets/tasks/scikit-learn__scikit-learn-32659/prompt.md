# DEP parameter penalty in LogisticRegression and LogisticRegressionCV

#### Reference Issues/PRs
Partially solves #28711.

This is the the no-brainer of

#### What does this implement/fix? Explain your changes.
This PR
  - for class LogisticRegression
        deprecates the parameters penalty
        changes the default of l1_ratio from None to 0
        l1_ratio=None is deprecated and forbidden as of 1.10
  - for class LogisticRegressionCV
        deprecates the parameters penalty
        changes the default of l1_ratios from None to "warn" (=deprecation of None)
        default of l1_ratios will change to (0,) in 1.10
        l1_ratios=None is deprecated and forbidden as of 1.10

#### Any other comments?

---

## Deliverable

Implement the change described above as a complete, mergeable contribution:

- Deliver a working end-to-end change; all existing tests must keep passing.
- Stay in scope: only change what is needed to satisfy the requirements.
- Do not modify existing tests.
