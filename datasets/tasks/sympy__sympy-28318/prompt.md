# [GSoC] Adding Discrete-Time TransferFunction

<!-- Your title above should be a short description of what
was changed. Do not include the issue number in the title. -->

#### References to other Issues or PRs
<!-- If this pull request fixes an issue, write "Fixes #NNNN" in that exact
format, e.g. "Fixes #1234" (see
https://tinyurl.com/auto-closing for more information). Also, please
write a comment on that issue linking back to this pull request once it is
open. -->

#### Brief description of what is fixed or changed
This PR lays the groundwork for extending the lti module to discrete time. It implements the `TransferFunctionBase` class, which is inherited by both `TransferFunction` and `DiscreteTransferFunction`. It also extends the ability to create interconnections between discrete-time systems.

Note: This PR is a clone of #28115. See that PR for the complete history.

#### Other comments

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
* physics.control
  * Added a new class for discrete time transfer functions.
  * Added a general method for creating both discrete-time and continuous-time transfer functions
<!-- END RELEASE NOTES -->

---

## Deliverable

Implement the change described above as a complete, mergeable contribution:

- Deliver a working end-to-end change; all existing tests must keep passing.
- Stay in scope: only change what is needed to satisfy the requirements.
- Do not modify existing tests.
