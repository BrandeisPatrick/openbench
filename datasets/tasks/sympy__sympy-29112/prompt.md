# Group operations optimization

<!-- Your title above should be a short description of what
was changed. Do not include the issue number in the title. -->

#### References to other Issues or PRs
<!-- If this pull request fixes an issue, write "Fixes #NNNN" in that exact
format, e.g. "Fixes #1234" (see
https://tinyurl.com/auto-closing for more information). Also, please
write a comment on that issue linking back to this pull request once it is
open. -->
This follows discussion in #29106.

#### Brief description of what is fixed or changed
This PR optimizes `FreeGroupElement.__pow__` and introduces fast product `.prod` method. These are quick benchmark results:
```text
Benchmark: FreeGroupElement.__pow__ old vs new
n=200000, repeats=9

word: x*y*x
  old median: 64.422 ms
  new median: 3.266 ms
  speedup old/new: 19.73x

word: x*y**2*x*y**3*x**-1
  old median: 69.311 ms
  new median: 14.877 ms
  speedup old/new: 4.66x
```

```text
Benchmark: naive product vs FreeGroupElement.prod
terms=4000, max_exp=20, repeats=7

word: x*y*x
  naive median: 208.694 ms
  prod  median: 53.048 ms
  speedup naive/prod: 3.93x

word: x*y**2*x*y**3*x**-1
  naive median: 469.886 ms
  prod  median: 307.221 ms
  speedup naive/prod: 1.53x
```

#### Other comments

#### AI Generation Disclosure
Some code is written by codex, inspected and edited by me.
<!-- If this pull request includes AI-generated code or text, please disclose
the tool used and specify which lines were generated. Disclosure is not
required for minor assistive tasks, such as spell-checking or code reviewing,
in primarily human-authored work. Otherwise, leave this area blank. Read our
Policy on AI Generated Code and Communication at
https://docs.sympy.org/dev/contributing/ai-generated-code-policy.html. -->

#### Release Notes

<!-- Write the release notes for this release below between the BEGIN and END
statements. The basic format is a bulleted list with the name of the subpackage
and the release note for this PR. For example:

* solvers
  * Added a new solver for logarithmic equations.

* functions
  * Fixed a bug with log of integers. Formerly, `log(-x)` incorrectly gave `-log(x)`.

* physics.units
  * Corrected a semantical error in the conversion between volt and statvolt which
    reported the volt as being larger than the statvolt.

or if no release note(s) should be included use:

NO ENTRY

See https://github.com/sympy/sympy/wiki/Writing-Release-Notes for more
information on how to write release notes. The bot will check your release
notes automatically to see if they are formatted correctly. -->

<!-- BEGIN RELEASE NOTES -->
* combinatorics
  * Optimized `FreeGroupElement.__pow__` which is now up to 20x faster.
  * Added `FreeGroupElement.prod` method to efficiently compute the product of a list of group elements.
<!-- END RELEASE NOTES -->

---

## Deliverable

Implement the change described above as a complete, mergeable contribution:

- Deliver a working end-to-end change; all existing tests must keep passing.
- Stay in scope: only change what is needed to satisfy the requirements.
- Do not modify existing tests.
