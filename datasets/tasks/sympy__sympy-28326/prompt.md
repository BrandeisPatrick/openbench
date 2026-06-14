# Bug in Series.doit()

I found a bug here:

https://github.com/sympy/sympy/blob//sympy/physics/control/lti.py#L1757-L1769

The `return` statement is wrongly indented inside the for loop, so it returns after converting only the first system.
I tested with python-control, and moving the return outside the loop fixes the issue.

I'm currently working on the state-space code, so I'll include this fix when I open the PR.

---

## Deliverable

Implement the change described above as a complete, mergeable contribution:

- Deliver a working end-to-end change; all existing tests must keep passing.
- Stay in scope: only change what is needed to satisfy the requirements.
- Do not modify existing tests.
