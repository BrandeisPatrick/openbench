# Add initial support for Python 3.14

<!-- Thank you for your contribution! -->
<!-- Unless your change is trivial, please create an issue to discuss the change before creating a PR -->

## Change Summary

Fixes (partially) https://github.com/pydantic/pydantic/issues/11613.

~~The remaining failing tests require:~~
- https://github.com/python/cpython/issues/135646
-

~~both to be available in 3.14a4.~~

This PR adds basic support for Python 3.14. More 3.14 specific features (e.g. ) will be added in follow up PRs.

## Remaining issues

### Using `Field()` in dataclasses

To support the following:

```python
from pydantic import Field

from pydantic.dataclasses import dataclass  # Also with stdlib dataclasses

class A:
    a: int = Field(default=1)
```

We currently have a somewhat hacky solution, which involves wrapping `Field(default=1)` into `dataclasses.field(default=Field(default=1))`, and more importantly directly writing into the `__annotations__` dict (L184):

https://github.com/pydantic/pydantic/blob//pydantic/dataclasses.py#L153-L184

In 3.14, writing/accessing `__annotations__` is no longer safe, as a `NameError` can be raised if a an unresolvable annotation is used. In other words, this now raises:

```python
from pydantic import Field

from pydantic.dataclasses import dataclass

class A:  # raises at declaration
    a: Forward = Field(default=1)

Forward = int
```

Unfortunately, I've tried hard to see if this could be supported somehow, and came to the conclusion that there is no way to do so without an unreasonable amount of workarounds. Such usage of forward references (_without_ using stringified annotations) is only going to get more popular as 3.14 adoption grows, but it is hard to know how common this issue will be encountered. A couple notes:

- This can be mitigated if we only want to support using `Field()` on the class being decorated (in which case we don't need to write to `__annotations__`) but not on any super-classes.
- To support the case where `Field()` is defined on a super-class, this super-class needs to be a Pydantic dataclass (in which case the previous point would have handled it). If the super-class is a stdlib dataclass, it will not be possible to reasonably support this without too much hassle:

    ```python
    _dataclass
    class A:
         a: int = pydantic.Field(kw_only=True)

    .dataclasses.dataclass
    class B(A):
        b: int
    ```

Here are the options we have:
- Deprecate support for `repr` and `kw_only` support together with `Field()` for dataclasses. I'm not a fan of this approach, as the issue only arises when using forward references as a deferred annotation, and works fine in other cases.
- Catch any `NameError` exceptions when trying to write to `__annotations__`, and raise a user warning saying the usage of `Field()` won't be supported if we catch one. Not a fan of this either, as the end user will only get a warning without any real explanation as to why it happened (they don't have to be aware of the Pydantic internals implemented to support `Field()`).

I don't have any satisfactory answers for now. I have added an xfailing test for this, and we can revisit later.

Edit: tracked in https://github.com/pydantic/pydantic/issues/12045, a different implementation will be used.

### Real deferred annotations

PEP 649/749 should now allow use cases like this:

```python
def outer():
    def inner():
        class Model(BaseModel):
            ann: Annotated[List[Dict[str, str]], MaxLen(1)]

        Dict = dict

        return Model

    List = list

    Model = inner()

    return Model

Model = outer()

Model.__annotations__['ann']
#> Annotated[list[dict[str, str]], MaxLen(1)]
```

However, trying to rebuild `Model` after getting it from `outer()` will raise an exception. This is because when we rebuild model fields, we do so individually by using `typing._eval_type()`. In reality, we should try accessing `__annotations__` again to let CPython internals resolve the references for us. This is far from trivial to implement, so deferred for a follow-up PR.

---

## Deliverable

Implement the change described above as a complete, mergeable contribution:

- Deliver a working end-to-end change; all existing tests must keep passing.
- Stay in scope: only change what is needed to satisfy the requirements.
- Do not modify existing tests.
