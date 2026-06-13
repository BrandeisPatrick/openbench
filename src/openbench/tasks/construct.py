"""Task construction: turn one merged PR into datasets/tasks/<task_id>/.

Writes prompt.md (leakage-stripped requirements), gold.patch (full hidden
solution diff), test.patch (test-only subset), and task.json. pass_to_pass and
protected_test_files are left empty here — validate.py fills them because they
need a runnable checkout.
"""

from __future__ import annotations

import re

from openbench import paths
from openbench.models import HardnessTier, PRCandidate, Task
from openbench.tasks.tests_split import extract_f2p_candidates, split_patch

# Mirrors filters.min_body_chars in configs/mining.yaml; enforced again here so
# direct `openbench build-task` calls cannot produce an unanswerable prompt.
MIN_BODY_CHARS = 500

DELIVERABLE_BLOCK = """\
---

## Deliverable

Implement the change described above as a complete, mergeable contribution:

- Deliver a working end-to-end change; all existing tests must keep passing.
- Stay in scope: only change what is needed to satisfy the requirements.
- Do not modify existing tests.
"""

# --- leakage stripping ------------------------------------------------------

_DIFF_FENCE_RE = re.compile(r"```(?:diff|patch)\b.*?(?:```|\Z)", re.DOTALL)
_SHA_RE = re.compile(r"\b[0-9a-f]{40}\b")
_GH_URL_RE = re.compile(
    r"https?://(?:www\.)?github\.com/[^\s()<>]+/(?:pull|pulls|commit|commits|compare)\b[^\s()<>]*"
)
_MENTION_RE = re.compile(r"(?<![\w.])@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?")
# Lines that look like raw diff hunks: ---/+++/@@ headers, or +/- immediately
# followed by code (no space, so "- markdown bullet" survives), or +/- followed
# by deep indentation (diff of indented code).
_DIFF_LINE_RE = re.compile(r"^(?:\+\+\+ |--- |@@ )|^[+-](?!\s)|^[+-]\s{3,}")
_FILES_CHANGED_RE = re.compile(r"^[#>\s*]*files?\s+changed\b.*$", re.IGNORECASE)
_PATH_TOKEN_RE = re.compile(r"[\w.\-/]+")


def _is_path_only_line(line: str) -> bool:
    """A (possibly bulleted) line whose only content is a file path."""
    stripped = line.strip()
    stripped = re.sub(r"^[-*+•]\s+", "", stripped).strip().strip("`").strip()
    if not stripped or " " in stripped:
        return False
    if not _PATH_TOKEN_RE.fullmatch(stripped):
        return False
    return "/" in stripped or stripped.endswith(".py")


def _strip_leakage(text: str) -> str:
    text = _DIFF_FENCE_RE.sub("", text)
    text = _GH_URL_RE.sub("", text)  # before SHA stripping mutilates commit URLs
    text = _SHA_RE.sub("", text)
    text = _MENTION_RE.sub("", text)
    kept: list[str] = []
    for line in text.splitlines():
        if _DIFF_LINE_RE.match(line):
            continue
        if _FILES_CHANGED_RE.match(line) and "changed" in line.lower():
            continue
        if _is_path_only_line(line):
            continue
        kept.append(line.rstrip())
    out = "\n".join(kept)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def llm_rewrite_pass(text: str) -> str:
    """HOOK: optional LLM rewrite of the prompt for fluency/leakage removal.

    Identity for the MVP — derive_prompt must stay deterministic. Swap this
    for a model call when prompt polishing is wired up.
    """
    return text


def derive_prompt(candidate: PRCandidate) -> str:
    """Deterministic prompt derivation from issue(s) or PR body.

    Prefers linked issue title+body (the problem statement); falls back to the
    PR title+body, rejecting bodies too thin to specify the work.
    """
    if candidate.linked_issues:
        sections = []
        for issue in candidate.linked_issues:
            title = str(issue.get("title") or "").strip()
            body = str(issue.get("body") or "").strip()
            sections.append(f"# {title}\n\n{body}".strip())
        raw = "\n\n".join(sections)
    else:
        body = candidate.body or ""
        if len(body) < MIN_BODY_CHARS:
            raise ValueError(
                f"{candidate.repo}#{candidate.pr_number}: no linked issue and PR body "
                f"has {len(body)} chars (< {MIN_BODY_CHARS}); cannot derive a prompt"
            )
        raw = f"# {candidate.title}\n\n{body}"

    text = llm_rewrite_pass(_strip_leakage(raw))
    return f"{text}\n\n{DELIVERABLE_BLOCK}"


# --- task building ----------------------------------------------------------


def build_task(repo: str, pr_number: int) -> Task:
    """Construct datasets/tasks/<task_id>/ from a merged PR and return the Task."""
    # Imported lazily so task construction stays importable without the miner.
    from openbench.mining.github import fetch_pr, fetch_pr_diff

    candidate = fetch_pr(repo, pr_number)
    diff_text = fetch_pr_diff(repo, pr_number)

    gold_patch, test_patch = split_patch(diff_text)
    prompt = derive_prompt(candidate)

    task_dir = paths.task_dir(candidate.task_id)
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "gold.patch").write_text(gold_patch)
    (task_dir / "test.patch").write_text(test_patch)
    (task_dir / "prompt.md").write_text(prompt)

    # Direct build-task without mining: no hardness signal computed here, so
    # default to MAIN / 0.0; the mining pipeline scores these over the pool.
    tier = candidate.tier or HardnessTier.MAIN
    hardness = candidate.hardness_score if candidate.hardness_score is not None else 0.0

    task = Task(
        task_id=candidate.task_id,
        repo=candidate.repo,
        pr_number=candidate.pr_number,
        base_commit=candidate.base_commit,
        merge_commit=candidate.merge_commit,
        merged_at=candidate.merged_at,
        tier=tier,
        hardness_score=hardness,
        fail_to_pass=extract_f2p_candidates(test_patch),
        pass_to_pass=[],  # filled by validate (needs to run the suite)
        protected_test_files={},  # filled by build-env/validate (needs a checkout)
    )
    (task_dir / "task.json").write_text(task.model_dump_json(indent=2))
    return task
