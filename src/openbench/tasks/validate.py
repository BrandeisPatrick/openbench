"""The base-fails/merged-passes validation gate (requires Docker).

Two containers from the task's base image:
  A — stays at the base commit: baseline suite run (PASS_TO_PASS sampling),
      then test.patch applied: F2P candidates must fail and sampled P2P must
      still pass (this is the tree grading sees for an empty agent patch).
  B — checked out at the merge commit: F2P and sampled P2P must pass.
Steps 2-3 repeat `rounds` times; tests that misbehave in any round are dropped
as flaky. Results are written back into task.json.
"""

from __future__ import annotations

import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from unidiff import PatchSet

from openbench import dockerutil, paths
from openbench.models import Task, TaskValidation
from openbench.tasks.tests_split import extract_f2p_candidates, is_test_path, sample_p2p

console = Console()

_JUNIT_PATH = "/repo/.openbench-junit.xml"
_PATCH_PATH = "/repo/.openbench-test.patch"

# Non-test directories whose conftest.py commonly imports doc/benchmark-only deps
# and breaks collection (e.g. scikit-learn's doc/conftest.py). They are never F2P
# targets, so ignore them everywhere pytest collects.
_IGNORE_DIRS = ("doc", "docs", "examples", "benchmarks", "asv_bench", "build")
_IGNORE = " ".join(f"--ignore={d}" for d in _IGNORE_DIRS)


# --- small helpers ----------------------------------------------------------


def _grading_config() -> dict[str, Any]:
    cfg = paths.CONFIGS / "grading.yaml"
    if cfg.exists():
        return yaml.safe_load(cfg.read_text()) or {}
    return {}


def _load_task(task_id: str) -> Task:
    return Task.model_validate_json((paths.task_dir(task_id) / "task.json").read_text())


def _save_task(task: Task) -> None:
    (paths.task_dir(task.task_id) / "task.json").write_text(task.model_dump_json(indent=2))


def _junit_node_id(testcase: ET.Element) -> str:
    """Rebuild a pytest node id from a legacy-family junit <testcase>."""
    file_attr = testcase.get("file") or ""
    classname = testcase.get("classname") or ""
    name = testcase.get("name") or ""
    if file_attr:
        module_dotted = file_attr.removesuffix(".py").replace("/", ".")
        cls = ""
        if classname.startswith(module_dotted) and len(classname) > len(module_dotted):
            cls = classname[len(module_dotted) + 1 :]
        parts = [file_attr, *([p for p in cls.split(".") if p] if cls else []), name]
        return "::".join(p for p in parts if p)
    if classname:  # fallback when file= is missing: dotted path, best effort
        return f"{classname.replace('.', '/')}.py::{name}"
    return name


def _parse_junit(xml_text: str) -> dict[str, str]:
    """junit xml -> {node_id: 'passed' | 'failed' | 'error' | 'skipped'}."""
    results: dict[str, str] = {}
    root = ET.fromstring(xml_text)
    for testcase in root.iter("testcase"):
        status = "passed"
        for child in testcase:
            if child.tag == "failure":
                status = "failed"
            elif child.tag == "error":
                status = "error"
            elif child.tag == "skipped":
                status = "skipped"
        results[_junit_node_id(testcase)] = status
    return results


def _run_tests(
    container: str, task: Task, node_ids: list[str] | None, timeout: int
) -> dict[str, str]:
    """Run pytest (whole suite when node_ids is None) and parse junit results.

    An empty junit report (e.g. collection ImportError before any test ran)
    yields {} — callers treat missing ids as not-passed, which is exactly the
    semantics we want for the must-fail-on-base leg.
    """
    targets = " ".join(f"'{nid}'" for nid in node_ids) if node_ids else ""
    cmd = (
        f"rm -f {_JUNIT_PATH} && {task.test_cmd} --tb=no -q -p no:cacheprovider "
        f"--continue-on-collection-errors {_IGNORE} -o junit_family=legacy "
        f"--junitxml={_JUNIT_PATH} {targets}"
    )
    dockerutil.exec_in(container, cmd, timeout=timeout)
    out = dockerutil.exec_in(container, f"cat {_JUNIT_PATH}", timeout=60)
    if out.exit_code != 0 or not out.stdout.strip():
        return {}
    try:
        return _parse_junit(out.stdout)
    except ET.ParseError:
        return {}


def _passed(results: dict[str, str]) -> set[str]:
    return {nid for nid, status in results.items() if status == "passed"}


def _collected_ids(
    container: str, task: Task, timeout: int, scope: list[str] | None = None
) -> set[str]:
    """Node ids that actually collect in the container's current tree.

    pytest aborts with a usage error (running nothing) if any requested node id
    does not exist, so every id list must be intersected with this set first —
    PRs rename/move tests, making base-sampled ids stale at the merged commit.
    """
    targets = " ".join(f"'{p}'" for p in scope) if scope else ""
    res = dockerutil.exec_in(
        container,
        f"{task.test_cmd} --collect-only -q -p no:cacheprovider "
        f"--continue-on-collection-errors {_IGNORE} {targets}",
        timeout=timeout,
    )
    ids: set[str] = set()
    for line in res.stdout.splitlines():
        line = line.strip()
        if "::" in line and not line.startswith(("=", "<", "ERROR", "warning")):
            ids.add(line)
    return ids


def _scope_paths(container: str, task_dir: Path, task: Task) -> list[str]:
    """Directories to scope baseline/collect runs to, instead of the full suite.

    Whole-suite runs on large repos (sympy: 30+ min) blow the validation
    timeout, and P2P only samples near the touched modules anyway. Scope =
    depth-2 dirs of every file the PR touches (source and test) plus a
    top-level tests/ dir — filtered to paths that exist in the container.
    Empty result means: run the whole suite.
    """
    dirs: set[str] = {"tests"}
    for patch_name in (task.gold_patch_path, task.test_patch_path):
        text = (task_dir / patch_name).read_text()
        if not text.strip():
            continue
        for pf in PatchSet(text):
            parts = pf.path.split("/")
            if len(parts) >= 3:
                dirs.add("/".join(parts[:2]))
            elif len(parts) == 2:
                dirs.add(parts[0])
    existing = [
        d
        for d in sorted(dirs)
        if dockerutil.exec_in(container, f"test -d '{d}'", timeout=30).exit_code == 0
    ]
    return existing


def _expand_ids(ids: set[str], collected: set[str]) -> set[str]:
    """Resolve statically-extracted node ids against actually-collected ones.

    Extraction yields bare ids (`file::test_basics`); parametrized tests
    collect as `file::test_basics[case]`. Junit results report the
    parametrized form, so bare ids must be expanded before any exact matching.
    """
    out: set[str] = set()
    for nid in ids:
        if nid in collected:
            out.add(nid)
        else:
            out |= {c for c in collected if c.startswith(nid + "[")}
    return out


def _reset_repo(container: str, commit: str) -> None:
    res = dockerutil.exec_in(
        container, f"git reset --hard {commit} && git clean -fd", timeout=300
    )
    if res.exit_code != 0:
        raise dockerutil.DockerError(f"git reset to {commit} failed: {res.stderr[-2000:]}")


def _apply_test_patch(container: str, patch_file: Path) -> None:
    dockerutil.copy_in(container, patch_file, _PATCH_PATH)
    res = dockerutil.exec_in(
        container, f"git apply --whitespace=nowarn {_PATCH_PATH}", timeout=120
    )
    if res.exit_code != 0:
        raise dockerutil.DockerError(f"test.patch did not apply: {res.stderr[-2000:]}")


def _protected_test_hashes(container: str) -> dict[str, str]:
    """sha256 of every test file in the (base-commit) working tree."""
    cmd = (
        "find . -path ./.git -prune -o -type f "
        "\\( -name 'conftest.py' -o -name 'test_*.py' -o -name '*_test.py' \\) "
        "-print0 | sort -z | xargs -0 -r sha256sum"
    )
    res = dockerutil.exec_in(container, cmd, timeout=300)
    hashes: dict[str, str] = {}
    for line in res.stdout.splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            digest, path = parts
            hashes[path.removeprefix("./").strip()] = digest
    return hashes


def _touched_top_level_dirs(gold_patch_file: Path) -> list[str]:
    """Top-level dirs of non-test files touched by the gold patch (for P2P bias)."""
    dirs: set[str] = set()
    for pf in PatchSet(gold_patch_file.read_text()):
        if not is_test_path(pf.path):
            dirs.add(pf.path.split("/", 1)[0])
    return sorted(dirs)


# --- the gate ----------------------------------------------------------------


def validate_task(task_id: str, rounds: int = 3) -> TaskValidation:
    """Run the base-fails/merged-passes gate; update and persist task.json."""
    task = _load_task(task_id)
    cfg = _grading_config()
    test_timeout = int(cfg.get("test_timeout_s", 1200))
    build_timeout = int(cfg.get("build_timeout_s", 1800))
    min_f2p = int(cfg.get("min_f2p_tests", 3))
    p2p_cap = int(cfg.get("p2p_sample_cap", 500))

    if not task.image_tag or not dockerutil.image_exists(task.image_tag):
        from openbench.envs.builder import build_task_image

        build_task_image(task_id)
        task = _load_task(task_id)

    task_dir = paths.task_dir(task_id)
    suffix = uuid.uuid4().hex[:8]
    name_base = f"openbench-val-base-{suffix}"
    name_merged = f"openbench-val-merged-{suffix}"

    try:
        # --- 1. container A at base: sanity-collect, baseline suite, P2P sample
        container_a = dockerutil.start_container(task.image_tag, name_base)
        scope = _scope_paths(container_a, task_dir, task)
        scope_targets = " ".join(f"'{p}'" for p in scope)
        collect = dockerutil.exec_in(
            container_a,
            f"{task.test_cmd} --collect-only -q {_IGNORE} {scope_targets}",
            timeout=test_timeout,
        )
        if collect.exit_code != 0:
            raise dockerutil.DockerError(
                f"{task_id}: pytest --collect-only failed at base "
                f"({collect.exit_code}):\n{(collect.stdout + collect.stderr)[-2000:]}"
            )
        protected = _protected_test_hashes(container_a)
        baseline = _run_tests(container_a, task, scope or None, test_timeout)
        all_passing = sorted(_passed(baseline))
        touched = _touched_top_level_dirs(task_dir / task.gold_patch_path)
        p2p_keep = set(sample_p2p(all_passing, touched, cap=p2p_cap))
        # Re-derive F2P candidates from test.patch rather than trusting
        # task.json: validation persists its (possibly empty) surviving set
        # there, so a rejected run would otherwise clobber the input of the
        # next one. This keeps validate idempotent.
        f2p_keep = set(
            extract_f2p_candidates((task_dir / task.test_patch_path).read_text())
        )

        # --- container B at the merged state
        container_b = dockerutil.start_container(task.image_tag, name_merged)
        checkout = dockerutil.exec_in(
            container_b, f"git checkout --quiet {task.merge_commit}", timeout=300
        )
        if checkout.exit_code != 0:
            raise dockerutil.DockerError(
                f"{task_id}: cannot checkout merge commit: {checkout.stderr[-2000:]}"
            )
        from openbench.envs.builder import offline_install_cmd

        install = dockerutil.exec_in(
            container_b, offline_install_cmd(task.install_cmd), timeout=build_timeout
        )
        if install.exit_code != 0:
            # The container has no network, so a reinstall that needs to fetch
            # build deps cannot succeed. The base editable install points at
            # /repo source, which covers pure-Python changes; real breakage
            # will surface in the merged-passes leg below.
            console.log(
                f"[yellow]{task_id}: reinstall at merge commit failed "
                f"(continuing with base install): {install.stderr[-300:]}[/yellow]"
            )

        # P2P ids were sampled from the base-commit baseline; drop any that no
        # longer exist at the merged commit (renamed/moved by the PR), and any
        # F2P id that does not collect there either.
        merged_ids = _collected_ids(container_b, task, test_timeout, scope=scope or None)
        if merged_ids:
            stale_p2p = p2p_keep - merged_ids
            if stale_p2p:
                console.log(
                    f"{task_id}: {len(stale_p2p)} P2P ids do not exist at merged; dropped"
                )
            p2p_keep &= merged_ids
            before = len(f2p_keep)
            f2p_keep = _expand_ids(f2p_keep, merged_ids)
            console.log(f"{task_id}: F2P expanded/resolved {before} -> {len(f2p_keep)}")

        # --- 2+3 repeated `rounds` times; misbehaving tests dropped as flaky
        flaky: set[str] = set()
        f2p_runnable_at_base: set[str] | None = None
        for round_idx in range(rounds):
            # 2. base + test.patch (the tree grading sees for an empty agent
            #    patch): every F2P candidate must fail/error, and every sampled
            #    P2P must still pass — a P2P test that needs the gold change is
            #    an F2P mislabel that would veto any agent's resolution.
            _reset_repo(container_a, task.base_commit)
            _apply_test_patch(container_a, task_dir / task.test_patch_path)
            if round_idx == 0 and (f2p_keep or p2p_keep):
                # F2P tests that don't collect at base (ImportError on the
                # not-yet-implemented module) already satisfy fail-on-base —
                # that's the expected failure mode, not staleness. Collect to
                # find which ids CAN run at base, since one unmatched node id
                # makes pytest abort the whole invocation with a usage error.
                base_ids = _collected_ids(
                    container_a, task, test_timeout, scope=scope or None
                )
                f2p_runnable_at_base = f2p_keep & base_ids
                # A P2P id that doesn't collect here needs the gold change to
                # even import; drop it now (and it can't be passed to pytest
                # below without aborting the run).
                if base_ids:
                    uncollected = p2p_keep - base_ids
                    if uncollected:
                        console.log(
                            f"{task_id}: {len(uncollected)} P2P ids do not "
                            f"collect at base+test.patch; dropped"
                        )
                        p2p_keep -= uncollected
                        flaky |= uncollected
            bad_f2p: set[str] = set()
            runnable = f2p_keep & (f2p_runnable_at_base or set())
            if runnable:
                on_base = _run_tests(container_a, task, sorted(runnable), test_timeout)
                bad_f2p |= runnable & _passed(on_base)
            bad_p2p: set[str] = set()
            if p2p_keep:
                p2p_base = _run_tests(container_a, task, sorted(p2p_keep), test_timeout)
                bad_p2p |= {nid for nid in p2p_keep if p2p_base.get(nid) != "passed"}
            # 3. merged: F2P and sampled P2P must pass.
            if f2p_keep:
                on_merged = _run_tests(container_b, task, sorted(f2p_keep), test_timeout)
                bad_f2p |= {nid for nid in f2p_keep if on_merged.get(nid) != "passed"}
            if p2p_keep:
                p2p_res = _run_tests(container_b, task, sorted(p2p_keep), test_timeout)
                bad_p2p |= {nid for nid in p2p_keep if p2p_res.get(nid) != "passed"}
            f2p_keep -= bad_f2p
            p2p_keep -= bad_p2p
            flaky |= bad_f2p | bad_p2p

        # --- 4/5. verdict + persist
        # The surviving sets satisfied their gate in every round by construction.
        p2p_ok = bool(p2p_keep) or not all_passing
        validation = TaskValidation(
            validated_at=datetime.now(timezone.utc),
            rounds=rounds,
            f2p_fail_on_base=bool(f2p_keep),
            f2p_pass_on_merged=bool(f2p_keep),
            p2p_pass_on_base=p2p_ok,
            p2p_pass_on_merged=p2p_ok,
            flaky_tests_dropped=sorted(flaky),
            accepted=len(f2p_keep) >= min_f2p and p2p_ok,
        )
        task.fail_to_pass = sorted(f2p_keep)
        task.pass_to_pass = sorted(p2p_keep)
        task.protected_test_files = protected
        task.validation = validation
        _save_task(task)
        return validation
    finally:
        dockerutil.remove_container(name_base)
        dockerutil.remove_container(name_merged)
