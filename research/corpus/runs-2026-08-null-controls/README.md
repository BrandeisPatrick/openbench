# Null-control runs (August 2026)

Specificity controls for the grading pipeline, run 2026-08-20: the empty
patch graded on each of the 4 active verified tasks. Expected result per
task: NOT RESOLVED with all P2P tests green (301/301 across the four
tasks). Grading a null patch as resolved, or P2P failures on an unmodified
workspace, would indicate a grading-environment defect.

These are measurement-validation evidence, not model runs — never include
them in any behavioral or solve-rate analysis. Companion sensitivity
controls (gold patches must resolve) are exercised by `openbench
golden-gate` against the golden fixtures.
