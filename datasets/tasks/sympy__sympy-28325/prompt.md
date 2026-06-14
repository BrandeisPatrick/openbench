# [Ring Series]: Add high-level Power Series Ring API with domain and element classes

### Reference
Issue: #26957
Extend and wrap the lower class: #28109

### Brief Description

This implementation introduces a higher-level representation for the Power Series Ring, providing a structured way to represent both the ring itself and its elements, along with a proper domain.
 - Ring (PowerSeriesRingRing, PowerSeriesRIngField)
	- PowerSeriesRingRing - Provides core power series ring operations (add, multiply, invert, compose, differentiate, revert) over a base ring. Additionally, this class extends functionality with methods for converting or constructing ring elements from various types (e.g., expressions, lists, integers).
	- PowerSeriesRingField - Extends PowerSeriesRingRing for fields, adding functions like sqrt, integration, log, exp, and transcendental operations.
 - Element (PowerSeriesElement)
The PowerSeriesElement class provides a structured representation of ring elements, supporting standard arithmetic operations (+, -, /, …). This implementation also supports an explicit Order term. If the external order term exceeds the precision of the ring, it is truncated to the ring’s precision.
 - Domain (SeriesRing)
The Series domain class includes the associated ring (self.ring) as metadata, which can be extracted for ring-specific operations. It provides methods for converting elements from other domains into its own data type.

### Other Comments

The factory function `power_series_ring` has been updated to return a tuple of the PowerSeriesRing and its generator, rather than lower-level rings. This makes it similar to  `ring` function used for polynomials (**PolyRing**).

```python
>>> from sympy import QQ
>>> from sympy.polys.series import power_series_ring
>>> R, y = power_series_ring("y", QQ, 10)
>>> R.inverse(1 + y)
1 - y + y**2 - y**3 + y**4 - y**5 + y**6 - y**7 + y**8 - y**9 + O(y**10)
```

### Release Notes

<!-- BEGIN RELEASE NOTES -->
* polys
   * A new Power Series module (polys/series) introduces **PowerSeriesRing** for working with univariate power series truncated to finite precision. It provides two ring types:
   		* **PowerSeriesRingRing** for ring domains such as ZZ, and
   		* **PowerSeriesRingField** for field domains such as QQ. 	Current implementation for QQ supports Taylor expansions at `x = 0` for functions such as exp, log, sin, cos, and others with well-defined series of rational coefficients.
   * A helper function power_series_ring automatically selects the appropriate series ring based on the ground domain.
<!-- END RELEASE NOTES -->

---

## Deliverable

Implement the change described above as a complete, mergeable contribution:

- Deliver a working end-to-end change; all existing tests must keep passing.
- Stay in scope: only change what is needed to satisfy the requirements.
- Do not modify existing tests.
