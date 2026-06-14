# [Ring Series]: New series module supporting truncated power series rings over ZZ and QQ with Python and FLINT backends.

### References to other Issues or PRs
Issue #26957 ||  #26100

This PR introduces a new power series ring implementation into SymPy’s polys module. It provides a unified framework for truncated power series arithmetic over domains like **ZZ** and **QQ**, with both high-performance FLINT-based and pure Python implementations.

### sympy/polys/series Structure

The module is modularly structured into four key components:
- `base.py:` Defines the abstract interface and base logic for power series rings.
- `ringpython.py:` Pure Python implementation ensuring full functionality on platforms without native extensions.
- `ringflint.py:` Optimized backend leveraging FLINT (via python-flint) for high-performance arithmetic over **ZZ** and **QQ**.
- `ring.py:` A factory system that automatically selects the best available backend based on the execution environment.

### Current Methods and Features
- Arithmetic Operations:
	- Addition, subtraction, multiplication, division
	- composition, Inversion(multiplicative inverse) and reversion(compositional  inverse)
- Calculus Support:
	- Differentiation and integration (over QQ)

### Quick Notes
- The pure Python implementation uses dup_* functions from the dense polynomial module for efficient arithmetic operations.
- Operations in the series ring automatically decide the return type:
	-	If the result fits exactly in the polynomial ring (no truncation needed), an exact polynomial is returned.
	-	If the operation requires truncation due to precision limits, a truncated power series is returned.

#### Release Notes

<!-- BEGIN RELEASE NOTES -->
* polys
  * Added a new `series` module supporting truncated power series ring operation over **ZZ** and **QQ**, with both pure Python and FLINT-based backends.
<!-- END RELEASE NOTES -->

---

## Deliverable

Implement the change described above as a complete, mergeable contribution:

- Deliver a working end-to-end change; all existing tests must keep passing.
- Stay in scope: only change what is needed to satisfy the requirements.
- Do not modify existing tests.
