"""GitHub API client with an on-disk response cache so mining is replayable offline.

Cache key = sha256(method + url + body); value = raw response text, stored under
paths.GH_CACHE. GraphQL is used for PR metadata, REST for file lists and diffs.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

import httpx

from openbench import paths
from openbench.models import PRCandidate

GRAPHQL_URL = "https://api.github.com/graphql"
REST_URL = "https://api.github.com"
TIMEOUT_S = 30.0
MAX_RETRIES = 3
_MAX_RATE_LIMIT_WAIT_S = 120.0


def gh_token() -> str | None:
    """GITHUB_TOKEN env var, else `gh auth token`, else None (unauthenticated)."""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    try:
        proc = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    token = proc.stdout.strip()
    return token if proc.returncode == 0 and token else None


def _cache_path(method: str, url: str, body: str) -> Path:
    digest = hashlib.sha256(f"{method}{url}{body}".encode()).hexdigest()
    return paths.GH_CACHE / digest


def _retry_wait(resp: httpx.Response, attempt: int) -> float:
    """Backoff for 403/5xx, honoring rate-limit reset / Retry-After headers."""
    if resp.headers.get("x-ratelimit-remaining") == "0":
        reset = resp.headers.get("x-ratelimit-reset")
        if reset:
            return min(max(float(reset) - time.time() + 1.0, 1.0), _MAX_RATE_LIMIT_WAIT_S)
    retry_after = resp.headers.get("retry-after")
    if retry_after:
        return min(float(retry_after), _MAX_RATE_LIMIT_WAIT_S)
    return 2.0**attempt


def _request(
    method: str,
    url: str,
    *,
    json_body: dict | None = None,
    accept: str = "application/vnd.github+json",
    use_cache: bool = True,
) -> str:
    body = json.dumps(json_body, sort_keys=True) if json_body is not None else ""
    cache_file = _cache_path(method, url, body)
    if use_cache and cache_file.exists():
        return cache_file.read_text()

    headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
    token = gh_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if json_body is not None:
        headers["Content-Type"] = "application/json"

    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = httpx.request(
                method, url, content=body or None, headers=headers, timeout=TIMEOUT_S
            )
        except httpx.HTTPError as exc:
            last_exc = exc
            time.sleep(2.0**attempt)
            continue
        if resp.status_code == 403 or resp.status_code >= 500:
            last_exc = httpx.HTTPStatusError(
                f"{resp.status_code} from {url}", request=resp.request, response=resp
            )
            time.sleep(_retry_wait(resp, attempt))
            continue
        resp.raise_for_status()
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(resp.text)
        return resp.text
    raise last_exc if last_exc else RuntimeError(f"request failed: {method} {url}")


def graphql(query: str, variables: dict, *, use_cache: bool = True) -> dict:
    """POST to the GitHub GraphQL API; raise if the response carries an errors key."""
    text = _request(
        "POST", GRAPHQL_URL, json_body={"query": query, "variables": variables}, use_cache=use_cache
    )
    payload = json.loads(text)
    if payload.get("errors"):
        raise RuntimeError(f"GraphQL errors: {payload['errors']}")
    return payload["data"]


_PR_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      title
      body
      baseRefOid
      mergeCommit { oid }
      mergedAt
      additions
      deletions
      changedFiles
      commits { totalCount }
      reviewThreads { totalCount }
      comments { totalCount }
      closingIssuesReferences(first: 5) { nodes { number title body } }
    }
  }
}
"""

_SEARCH_QUERY = """
query($q: String!, $first: Int!, $after: String) {
  search(query: $q, type: ISSUE, first: $first, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes { ... on PullRequest { number mergedAt additions deletions changedFiles } }
  }
}
"""


def _top_level_dir(path: str) -> str:
    return path.split("/", 1)[0] if "/" in path else "."


def _is_test_path(path: str) -> bool:
    if path.startswith("tests/"):
        return True
    return any("test" in segment.lower() for segment in path.split("/"))


def _count_added_test_defs(patch: str) -> int:
    return sum(
        1
        for line in patch.splitlines()
        if line.startswith("+") and not line.startswith("+++") and "def test_" in line
    )


def fetch_pr_files(repo: str, pr_number: int, *, use_cache: bool = True) -> list[dict]:
    """All changed-file entries from the REST files endpoint (paginated, per_page=100)."""
    files: list[dict] = []
    page = 1
    while True:
        url = f"{REST_URL}/repos/{repo}/pulls/{pr_number}/files?per_page=100&page={page}"
        batch = json.loads(_request("GET", url, use_cache=use_cache))
        files.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return files


def fetch_pr(repo: str, pr_number: int, *, use_cache: bool = True) -> PRCandidate:
    """Hydrate one merged PR into a PRCandidate (hardness/tier left unset)."""
    owner, name = repo.split("/", 1)
    data = graphql(
        _PR_QUERY, {"owner": owner, "name": name, "number": pr_number}, use_cache=use_cache
    )
    pr = data["repository"]["pullRequest"]
    files = fetch_pr_files(repo, pr_number, use_cache=use_cache)
    filenames = [f["filename"] for f in files]
    linked = [
        {"number": n["number"], "title": n["title"], "body": n.get("body") or ""}
        for n in pr["closingIssuesReferences"]["nodes"]
        if n
    ]
    return PRCandidate(
        repo=repo,
        pr_number=pr_number,
        title=pr["title"],
        body=pr.get("body") or "",
        linked_issues=linked,
        base_commit=pr["baseRefOid"],
        merge_commit=(pr.get("mergeCommit") or {}).get("oid", ""),
        merged_at=pr["mergedAt"],
        additions=pr["additions"],
        deletions=pr["deletions"],
        changed_files=pr["changedFiles"],
        commits=pr["commits"]["totalCount"],
        review_comments=pr["reviewThreads"]["totalCount"] + pr["comments"]["totalCount"],
        top_level_dirs=sorted({_top_level_dir(p) for p in filenames}),
        test_files_changed=[p for p in filenames if _is_test_path(p)],
        test_functions_changed=sum(_count_added_test_defs(f.get("patch") or "") for f in files),
        dependency_depth=0,  # computed later from the diff; never from a clone
    )


def fetch_pr_diff(repo: str, pr_number: int, *, use_cache: bool = True) -> str:
    """Full unified diff of a PR via REST with the diff media type."""
    url = f"{REST_URL}/repos/{repo}/pulls/{pr_number}"
    return _request("GET", url, accept="application/vnd.github.diff", use_cache=use_cache)


def search_long_prs(
    repo: str,
    merged_after: str,
    limit: int,
    *,
    prescreen: dict | None = None,
    max_scanned: int = 1000,
    use_cache: bool = True,
) -> list[PRCandidate]:
    """Merged PRs in repo merged on/after merged_after, newest-first, hydrated.

    `limit` bounds the number of *hydrated* candidates returned. Hydration
    (GraphQL detail + paginated REST files) is the expensive step, so when
    `prescreen` is given (the mining config's `filters` section), PRs failing
    the size thresholds already visible in search results (loc, changed files)
    are skipped before hydration. Pages are scanned until `limit` survivors
    are found or `max_scanned` PRs have been examined.
    """
    q = f"repo:{repo} is:pr is:merged merged:>={merged_after} sort:created-desc"
    found: list[tuple[int, str]] = []  # (number, mergedAt)
    scanned = 0
    after: str | None = None
    while len(found) < limit and scanned < max_scanned:
        data = graphql(_SEARCH_QUERY, {"q": q, "first": 50, "after": after}, use_cache=use_cache)
        search = data["search"]
        for node in search["nodes"]:
            if not node or node.get("number") is None:
                continue
            scanned += 1
            if prescreen is not None:
                loc = int(node.get("additions") or 0) + int(node.get("deletions") or 0)
                if not (
                    prescreen.get("min_loc_changed", 0)
                    <= loc
                    <= prescreen.get("max_loc_changed", 10**9)
                    and int(node.get("changedFiles") or 0)
                    >= prescreen.get("min_changed_files", 0)
                ):
                    continue
            found.append((node["number"], node.get("mergedAt") or ""))
        if not search["pageInfo"]["hasNextPage"]:
            break
        after = search["pageInfo"]["endCursor"]
    found.sort(key=lambda t: t[1], reverse=True)
    return [fetch_pr(repo, number, use_cache=use_cache) for number, _ in found[:limit]]
