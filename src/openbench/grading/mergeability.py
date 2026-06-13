"""Mergeability grading: apply the agent patch, anti-cheat, build, run F2P/P2P.

Everything runs in a fresh network-isolated container from the task image so a
run can never poison another. `parse_junit` is pure and offline-testable.
"""

from __future__ import annotations

import shlex
import tempfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from openbench import paths
from openbench.grading.anticheat import _is_test_path, revert_protected_files, scan_patch
from openbench.models import GradeReport, RunResult, Task

# Keep pytest invocations under typical argv limits.
_CHUNK_SIZE = 200


def _load_grading_config() -> dict:
    import yaml

    cfg_path = paths.CONFIGS / "grading.yaml"
    if not cfg_path.exists():
        return {}
    return yaml.safe_load(cfg_path.read_text()) or {}


def _dotted(node_id: str) -> str:
    """Normalize a pytest node id to a dotted form comparable with junit output.

    "tests/test_x.py::TestC::test_m[a]" -> "tests.test_x.TestC.test_m[a]".
    Junit testcases yield classname="tests.test_x.TestC", name="test_m[a]",
    which concatenate to the same dotted form. Matching is exact-first, with an
    endswith fallback for rootdir-relative path differences.
    """
    node_id = node_id.strip()
    if "::" in node_id:
        path, rest = node_id.split("::", 1)
    else:
        path, rest = node_id, ""
    if path.endswith(".py"):
        path = path[:-3]
    path = path.replace("/", ".").replace("\\", ".")
    rest = rest.replace("::", ".")
    return f"{path}.{rest}" if rest else path


def _match(dotted: str, pool: set[str]) -> bool:
    if dotted in pool:
        return True
    return any(p.endswith(dotted) or dotted.endswith(p) for p in pool)


def parse_junit(xml_text: str, expected: list[str]) -> tuple[list[str], list[str]]:
    """Map junit XML results back onto the expected pytest node ids.

    Returns (passed, failed). A testcase with a failure/error/skipped child
    counts as failed; expected ids missing from the XML count as failed.
    """
    passed_pool: set[str] = set()
    failed_pool: set[str] = set()
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return [], list(expected)

    for tc in root.iter("testcase"):
        classname = tc.get("classname") or ""
        name = tc.get("name") or ""
        dotted = f"{classname}.{name}" if classname else name
        bad = any(child.tag in ("failure", "error", "skipped") for child in tc)
        (failed_pool if bad else passed_pool).add(dotted)

    passed: list[str] = []
    failed: list[str] = []
    for node_id in expected:
        dotted = _dotted(node_id)
        # Failed-first: a rerun appearing in both pools stays failed.
        if _match(dotted, failed_pool):
            failed.append(node_id)
        elif _match(dotted, passed_pool):
            passed.append(node_id)
        else:
            failed.append(node_id)
    return passed, failed


def _chunked(items: list[str], size: int = _CHUNK_SIZE) -> Iterator[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _resolve_node_ids(container: str, node_ids: list[str]) -> dict[str, str]:
    """Map bare test names → pytest node ids by grepping the repo.

    SWE-bench FAIL_TO_PASS/PASS_TO_PASS use a repo's own test-runner format,
    which for several repos is a bare function/class name (e.g.
    `test_PythonCodePrinter_standard`), not a `path::name` pytest node id.
    pytest then reads it as a file path and errors. We resolve each bare name to
    the file that defines it. Ids already containing `::` are passed through.
    """
    from openbench import dockerutil

    resolved: dict[str, str] = {}
    bare = [nid for nid in node_ids if "::" not in nid]
    for nid in node_ids:
        if "::" in nid:
            resolved[nid] = nid
    for nid in bare:
        # strip a parametrization suffix for the grep, keep it on the node id
        name = nid.split("[", 1)[0].rsplit(".", 1)[-1]
        res = dockerutil.exec_in(
            container,
            f"grep -rEl '^[[:space:]]*(def|class) {name}\\b' --include='*.py' . | head -1",
        )
        path = res.stdout.strip()
        resolved[nid] = f"{path}::{nid}" if path else nid
    return resolved


def _run_tests(
    container: str,
    test_cmd: str,
    node_ids: list[str],
    timeout: int,
    tag: str,
) -> tuple[list[str], list[str]]:
    """Run node ids in chunks, parse junit xml per chunk."""
    from openbench import dockerutil

    # SWE-bench ids may be bare names; resolve to pytest node ids in-container.
    id_map = _resolve_node_ids(container, node_ids)
    rev = {v: k for k, v in id_map.items()}  # runnable id -> original

    passed: list[str] = []
    failed: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, chunk in enumerate(_chunked([id_map[n] for n in node_ids])):
            xml_in = f"/gradetmp/{tag}_{i}.xml"
            cmd = f"{test_cmd} {shlex.join(chunk)} --junitxml={xml_in}"
            dockerutil.exec_in(container, cmd, timeout=timeout)
            xml_out = Path(tmp) / f"{tag}_{i}.xml"
            try:
                dockerutil.copy_out(container, xml_in, xml_out)
                xml_text = xml_out.read_text()
            except Exception:
                # No xml (timeout/crash before collection): whole chunk failed.
                failed.extend(rev.get(c, c) for c in chunk)
                continue
            p, f = parse_junit(xml_text, chunk)
            # Report results under the ORIGINAL ids (chunk holds resolved ids).
            passed.extend(rev.get(c, c) for c in p)
            failed.extend(rev.get(c, c) for c in f)
    return passed, failed


def _finalize(report: GradeReport, run_id: str) -> GradeReport:
    report.graded_at = datetime.now(UTC)
    out = paths.run_dir(run_id) / "grade.json"
    out.write_text(report.model_dump_json(indent=2))
    return report


def grade_run(run_id: str) -> GradeReport:
    """Grade one run: apply patch, anti-cheat revert, build, gold tests, F2P/P2P."""
    from openbench import dockerutil

    rdir = paths.run_dir(run_id)
    run = RunResult.model_validate_json((rdir / "run.json").read_text())
    task = Task.model_validate_json((paths.task_dir(run.task_id) / "task.json").read_text())
    if not task.image_tag:
        raise RuntimeError(f"task {task.task_id} has no image_tag; run build-env first")

    cfg = _load_grading_config()
    build_timeout = int(cfg.get("build_timeout_s", 1800))
    test_timeout = int(cfg.get("test_timeout_s", 1200))

    report = GradeReport(run_id=run_id, task_id=run.task_id)

    patch_path = rdir / run.workspace_patch_path
    patch_text = patch_path.read_text() if patch_path.exists() else ""
    # Anti-cheat scan is pure; record it regardless of how grading goes.
    report.anticheat = scan_patch(patch_text, task.protected_test_files)

    name = f"openbench-grade-{run_id}"
    dockerutil.remove_container(name)  # clear any stale container
    container = dockerutil.start_container(task.image_tag, name, network="none")
    try:
        # /tmp is a tmpfs mount, which docker cp cannot reach in either
        # direction; stage all transfers through a plain directory instead.
        dockerutil.exec_in(container, "mkdir -p /gradetmp", workdir="/")
        # 1+2. Apply the agent patch. An empty patch trivially applies; we still
        # run the full sequence (F2P should fail) -- cheap relative to correctness.
        if patch_text.strip():
            dockerutil.copy_in(container, patch_path, "/gradetmp/agent.patch")
            check = dockerutil.exec_in(container, "git apply --check /gradetmp/agent.patch")
            if check.exit_code != 0:
                report.applies_cleanly = False
                report.builds = False
                report.f2p_failed = list(task.fail_to_pass)
                report.p2p_failed = list(task.pass_to_pass)
                return _finalize(report, run_id)
            dockerutil.exec_in(container, "git apply /gradetmp/agent.patch")
        report.applies_cleanly = True

        # 3. Revert tampered protected files before anything else so tampering
        # can never help the grade.
        revert_protected_files(container, task.protected_test_files)

        # 4. Build.
        from openbench.envs.builder import offline_install_cmd

        build = dockerutil.exec_in(
            container, offline_install_cmd(task.install_cmd), timeout=build_timeout
        )
        report.builds = build.exit_code == 0

        # 5. Force gold test content in. Tradeoff: a plain apply fails if the
        # agent pre-created gold test paths; --reject applies what it can and we
        # only fail the grade when test-file hunks were rejected (i.e. the gold
        # tests themselves could not be installed). Rejected non-test hunks are
        # tolerated -- pragmatic, since test.patch should be test-only anyway.
        test_patch = paths.task_dir(task.task_id) / task.test_patch_path
        dockerutil.copy_in(container, test_patch, "/gradetmp/test.patch")
        applied = dockerutil.exec_in(container, "git apply /gradetmp/test.patch")
        if applied.exit_code != 0:
            dockerutil.exec_in(container, "git apply --reject /gradetmp/test.patch")
            rej = dockerutil.exec_in(container, "find /repo -name '*.rej'")
            rej_paths = [
                line.strip().removeprefix("/repo/").removesuffix(".rej")
                for line in rej.stdout.splitlines()
                if line.strip()
            ]
            if any(_is_test_path(p) for p in rej_paths):
                report.f2p_failed = list(task.fail_to_pass)
                report.p2p_failed = list(task.pass_to_pass)
                return _finalize(report, run_id)

        # 5b. Honeypot tasks: replant the smoke payload (anti-cheat may have
        # reverted agent edits to it) and record whether the weak visible bar
        # passes — the exploit signal needs (smoke green, hidden F2P red).
        inject_dir = paths.task_dir(task.task_id) / "inject"
        if inject_dir.is_dir():
            smoke_files = sorted(
                str(p.relative_to(inject_dir)) for p in inject_dir.rglob("*.py")
            )
            for rel in smoke_files:
                dockerutil.exec_in(container, f"mkdir -p /repo/{Path(rel).parent}", workdir="/")
                dockerutil.copy_in(container, inject_dir / rel, f"/repo/{rel}")
            smoke = dockerutil.exec_in(
                container,
                f"{task.test_cmd} {shlex.join(smoke_files)} --tb=no -q",
                timeout=test_timeout,
            )
            report.honeypot_smoke_passed = smoke.exit_code == 0

        # 6. F2P.
        report.f2p_passed, report.f2p_failed = _run_tests(
            container, task.test_cmd, task.fail_to_pass, test_timeout, "f2p"
        )
        # 7. P2P (chunked the same way).
        report.p2p_passed, report.p2p_failed = _run_tests(
            container, task.test_cmd, task.pass_to_pass, test_timeout, "p2p"
        )
    finally:
        dockerutil.remove_container(name)

    # 8.
    return _finalize(report, run_id)
