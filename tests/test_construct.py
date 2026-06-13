"""Offline unit tests for openbench.tasks.construct (no network, no docker).

The mining module is provided by a parallel workstream, so it is faked via
sys.modules; construct.build_task imports it lazily inside the function.
"""

from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timezone

import pytest

from openbench.models import HardnessTier, PRCandidate, Task
from openbench.tasks.construct import MIN_BODY_CHARS, derive_prompt, llm_rewrite_pass

REQUIREMENT_SENTENCES = (
    "This change adds a configurable retry policy to the HTTP client so that "
    "transient failures are retried with exponential backoff. The retry count "
    "must be configurable and default to three attempts. Connection errors and "
    "5xx responses should trigger a retry, while 4xx responses must fail "
    "immediately without retrying. The backoff delay doubles after each attempt "
    "and is capped at thirty seconds. A jitter fraction is applied to every "
    "delay to avoid thundering herds. The policy must be sharable across client "
    "instances and safe to use from multiple threads at the same time."
)

LEAKY_BODY = f"""{REQUIREMENT_SENTENCES}

Fixed in 0123456789abcdef0123456789abcdef01234567 by @alice, see
https://github.com/acme/widget/pull/42 and
https://github.com/acme/widget/commit/0123456789abcdef0123456789abcdef01234567

```diff
+def retry_with_backoff(attempts=3):
-def retry(attempts):
@@ -1,3 +1,9 @@
```

+    delay = min(delay * 2, 30)
-    delay = delay * 2

Files changed:
- pkg/http/client.py
- pkg/http/retry.py
- tests/test_client.py
"""


def make_candidate(**overrides) -> PRCandidate:
    fields = dict(
        repo="acme/widget",
        pr_number=42,
        title="Add retry policy to HTTP client",
        body=LEAKY_BODY,
        linked_issues=[],
        base_commit="a" * 40,
        merge_commit="b" * 40,
        merged_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
        additions=700,
        deletions=120,
        changed_files=12,
        commits=6,
        review_comments=11,
    )
    fields.update(overrides)
    return PRCandidate(**fields)


# --- derive_prompt ------------------------------------------------------------


def test_derive_prompt_strips_leakage_and_keeps_requirements():
    prompt = derive_prompt(make_candidate())

    # requirements survive
    assert "exponential backoff" in prompt
    assert "capped at thirty seconds" in prompt
    # leakage is gone
    assert "```diff" not in prompt
    assert "retry_with_backoff" not in prompt  # inside the diff fence
    assert "0123456789abcdef" not in prompt  # 40-char SHAs
    assert "github.com" not in prompt  # pull/commit URLs
    assert "@alice" not in prompt and "alice" not in prompt  # @mentions
    assert "pkg/http/client.py" not in prompt  # file-path bullet list
    assert "Files changed" not in prompt
    assert "delay = min(delay * 2, 30)" not in prompt  # bare diff hunk lines
    # deliverable block appended
    assert "Do not modify existing tests." in prompt
    assert "mergeable" in prompt


def test_derive_prompt_prefers_linked_issue():
    issue_body = "The client must retry transient failures with backoff. " * 5
    cand = make_candidate(
        body="tiny",
        linked_issues=[{"number": 7, "title": "Retries needed", "body": issue_body}],
    )
    prompt = derive_prompt(cand)
    assert "Retries needed" in prompt
    assert "retry transient failures" in prompt
    assert "tiny" not in prompt


def test_derive_prompt_rejects_short_body_without_issue():
    cand = make_candidate(body="too short", linked_issues=[])
    assert len(cand.body) < MIN_BODY_CHARS
    with pytest.raises(ValueError, match="cannot derive a prompt"):
        derive_prompt(cand)


def test_llm_rewrite_pass_is_identity_for_now():
    assert llm_rewrite_pass("keep me intact") == "keep me intact"


def test_derive_prompt_is_deterministic():
    cand = make_candidate()
    assert derive_prompt(cand) == derive_prompt(cand)


# --- build_task round trip ------------------------------------------------------

ROUND_TRIP_DIFF = """\
diff --git a/pkg/core.py b/pkg/core.py
index 1111111..2222222 100644
--- a/pkg/core.py
+++ b/pkg/core.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
diff --git a/tests/test_core.py b/tests/test_core.py
index 3333333..4444444 100644
--- a/tests/test_core.py
+++ b/tests/test_core.py
@@ -1,1 +1,7 @@
 from pkg.core import add
+
+def test_add():
+    assert add(1, 2) == 3
+
+class TestMath:
+    def test_add_negative(self):
"""


def test_build_task_round_trip(monkeypatch, tmp_path):
    from openbench import paths

    monkeypatch.setattr(paths, "TASKS", tmp_path)

    candidate = make_candidate()
    fake_github = types.ModuleType("openbench.mining.github")
    fake_github.fetch_pr = lambda repo, pr_number: candidate
    fake_github.fetch_pr_diff = lambda repo, pr_number: ROUND_TRIP_DIFF
    monkeypatch.setitem(sys.modules, "openbench.mining.github", fake_github)

    from openbench.tasks.construct import build_task

    task = build_task("acme/widget", 42)

    assert task.task_id == "acme__widget-42"
    task_dir = tmp_path / task.task_id
    assert (task_dir / "gold.patch").read_text() == ROUND_TRIP_DIFF  # full diff kept
    test_patch = (task_dir / "test.patch").read_text()
    assert "tests/test_core.py" in test_patch
    assert "pkg/core.py" not in test_patch  # source files excluded from test.patch

    prompt = (task_dir / "prompt.md").read_text()
    assert "exponential backoff" in prompt
    assert "Do not modify existing tests." in prompt

    assert task.fail_to_pass == [
        "tests/test_core.py::TestMath::test_add_negative",
        "tests/test_core.py::test_add",
    ]
    assert task.pass_to_pass == []  # filled later by validate
    assert task.protected_test_files == {}  # filled later by build-env/validate
    assert task.tier is HardnessTier.MAIN  # default without mining
    assert task.hardness_score == 0.0
    assert task.image_tag is None

    # task.json round-trips through the pydantic model
    on_disk = json.loads((task_dir / "task.json").read_text())
    assert Task.model_validate(on_disk) == task


def test_build_task_respects_mined_tier(monkeypatch, tmp_path):
    from openbench import paths

    monkeypatch.setattr(paths, "TASKS", tmp_path)

    candidate = make_candidate(tier=HardnessTier.DIAMOND, hardness_score=0.91)
    fake_github = types.ModuleType("openbench.mining.github")
    fake_github.fetch_pr = lambda repo, pr_number: candidate
    fake_github.fetch_pr_diff = lambda repo, pr_number: ROUND_TRIP_DIFF
    monkeypatch.setitem(sys.modules, "openbench.mining.github", fake_github)

    from openbench.tasks.construct import build_task

    task = build_task("acme/widget", 42)
    assert task.tier is HardnessTier.DIAMOND
    assert task.hardness_score == 0.91
