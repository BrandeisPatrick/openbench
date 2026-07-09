# unhandled by integration routines: `integrate(sqrt(a - x) / (x * sqrt(a + x)), x)`

sympy version: 1.14.0
python version: 3.12.3
OS: Ubuntu 24.04.4 LTS

reproduce
```python
import sympy as sp

# define symbols with assumptions
a = sp.symbols("a", positive=True)
x = sp.symbols("x", real=True)

f = sp.sqrt((a - x) / (a + x)) / x

integral = sp.integrate(f, x)
integral_simplified = sp.simplify(integral)

print(integral_simplified)
```
output:
```
Integral(sqrt((a - x)/(a + x))/x, x)
```
expected result
a closed-form expression

my calculations

<img width="2109" height="719" alt="Image" src="https://github.com/user-attachments/assets/0e78f65a-014b-492b-9b71-c2bc7b51ee07" />

---

## Deliverable

Implement the change described above as a complete, mergeable contribution:

- Deliver a working end-to-end change; all existing tests must keep passing.
- Stay in scope: only change what is needed to satisfy the requirements.
- Do not modify existing tests.
