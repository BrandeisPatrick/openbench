# Parked experiments (considered, set aside, and why)

- **PUMA redundancy detector on raw CoT** ([2605.17672](https://arxiv.org/abs/2605.17672),
  detector weights released). Descriptive: every recipe predicts less
  redundant reasoning in newer generations, so the result does not
  discriminate recipes. May return as a *measure* inside exp-05's
  decomposition (redundant tail vs novel content).
- **Overthinking rubric** ([2502.08235](https://arxiv.org/abs/2502.08235),
  judge prompt in Appendix A; repo now 404). Descriptive; useful as an
  external anchor (their o1 scored 2.4–2.8 on SWE-bench Verified) and as a
  covariate, not as a recipe test.
- **Verification claims vs actions** (own design). Kept as a measure
  (unsupported completion rate, claims-per-test) inside exp-04 and exp-06
  rather than as a standalone experiment.
