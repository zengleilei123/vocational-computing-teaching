"""Prove the inactive storage fault is caught, only inside a temporary copy.

Requires Python 3.10+, Node 20+ and Git. The optional --browser check additionally
requires the documented Playwright/Chromium setup. No network, repository
commits or changes to the source checkout are needed while running the checks.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


PROJECT = Path(__file__).resolve().parents[1]
REPOSITORY = PROJECT.parents[1]
PROJECT_RELATIVE = Path("teacher_reference/robot_map_portfolio")
TARGET = PROJECT_RELATIVE / "static/portfolio-core.js"
TESTS = PROJECT_RELATIVE / "tests/core.test.cjs"
PATCH = PROJECT / "exercises/storage-write-failure/fault.patch"
REGRESSION = "A09 写入失败时保存、覆盖和删除均不伪报成功或改变已有存档"
BROWSER_MODULE = "teacher_reference.robot_map_portfolio.tests.test_acceptance"
BROWSER_METHOD = "test_A09_storage_failure_and_corruption"


class VerificationError(RuntimeError):
    """A required verification condition was not satisfied."""


@dataclass(frozen=True)
class TestReport:
    names: tuple[str, ...]
    failures: tuple[str, ...]
    total: int
    passed: int
    output: str
    returncode: int


def manifest(root: Path) -> dict[str, str]:
    """Fingerprint files; interpreter caches are not source or test evidence."""
    result = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_file():
            result[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def source_manifest() -> dict[str, str]:
    result = {}
    for relative in (PROJECT_RELATIVE, Path("projects/robot_playground"),
                     Path("curriculum/ai-assisted-development")):
        for name, digest in manifest(REPOSITORY / relative).items():
            result[(relative / name).as_posix()] = digest
    return result


def changed_files(before: dict[str, str], after: dict[str, str]) -> set[str]:
    return {name for name in before.keys() | after.keys() if before.get(name) != after.get(name)}


def execute(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise VerificationError(f"不能完成命令 {command[0]}：{error}") from error


def run_tests(node: str, root: Path, verbose: bool) -> TestReport:
    # Calling the node:test file directly avoids a second test-isolation process.
    # A forced TAP reporter provides individual results on all supported Nodes.
    process = execute([node, "--test-reporter=tap", str(TESTS)], root)
    output = process.stdout + process.stderr
    if verbose:
        print(output, end="" if output.endswith("\n") else "\n")
    entries = re.findall(r"^(ok|not ok) \d+ - (.+)$", process.stdout, re.MULTILINE)
    counts = {name: int(value) for name, value in re.findall(
        r"^# (tests|suites|pass|fail|cancelled|skipped|todo) (\d+)\s*$",
        process.stdout, re.MULTILINE)}
    expected_counts = {"tests", "suites", "pass", "fail", "cancelled", "skipped", "todo"}
    names = tuple(name for _status, name in entries)
    failures = tuple(name for status, name in entries if status == "not ok")
    valid = (counts.keys() == expected_counts and counts["tests"] > 0
             and len(entries) == counts["tests"] and len(set(names)) == len(names)
             and counts["suites"] == counts["cancelled"] == counts["skipped"] == counts["todo"] == 0
             and counts["pass"] + counts["fail"] == counts["tests"]
             and counts["fail"] == len(failures) and names.count(REGRESSION) == 1)
    if not valid:
        if not verbose:
            print(output, file=sys.stderr)
        raise VerificationError("测试报告不完整、存在跳过/取消，或找不到唯一指定回归用例。")
    return TestReport(names, failures, counts["tests"], counts["pass"], output,
                      process.returncode)


def require_pass(report: TestReport, label: str) -> None:
    if report.returncode != 0 or report.failures or report.passed != report.total:
        print(report.output, file=sys.stderr)
        raise VerificationError(f"{label}未全部通过，不能验证故障补丁。")
    print(f"{label}：{report.passed}/{report.total} 通过，0 跳过。")


def run_browser(root: Path, label: str, expect_fault: bool, verbose: bool) -> None:
    arguments = [sys.executable, "-m", "unittest", BROWSER_MODULE, "-v", "-k", "A09"]
    # A broken delete can remove an option from the visible list, contaminating
    # later subtest setup. Stop at the first intended assertion in the mutant;
    # baseline and restored runs still execute the complete A09 method.
    if expect_fault:
        arguments.append("--failfast")
    process = execute(arguments, root)
    output = process.stdout + process.stderr
    if verbose:
        print(output, end="" if output.endswith("\n") else "\n")
    case = f"{BROWSER_METHOD} ({BROWSER_MODULE}.PortfolioAcceptanceTests.{BROWSER_METHOD})"
    failures = re.findall(r"^(FAIL|ERROR): (.+)$", output, re.MULTILINE)
    ran_one = re.search(r"^Ran 1 test in [0-9.]+s$", output, re.MULTILINE) is not None
    correct_case = case + " ..." in output
    if expect_fault:
        expected = [("FAIL", f"{case} (action='save')")]
        valid = (ran_one and correct_case and process.returncode == 1
                 and failures == expected
                 and re.search(r"^FAILED \(failures=1\)$", output, re.MULTILINE))
        message = "指定 A09 的保存子测试失败（预期；failfast），未将后续未执行子测试计为通过。"
    else:
        valid = (ran_one and correct_case and process.returncode == 0 and not failures
                 and re.search(r"^OK$", output, re.MULTILINE))
        message = "A09 通过，0 跳过。"
    if not valid:
        if not verbose:
            print(output, file=sys.stderr)
        raise VerificationError(f"浏览器{label}未满足指定结果；环境错误、意外失败或跳过不能计为通过。")
    print(f"真实 HTTP 浏览器{label}：{message}")


def check_patch_scope() -> None:
    patch = PATCH.read_text(encoding="utf-8")
    target = TARGET.as_posix()
    files = re.findall(r"^diff --git a/(\S+) b/(\S+)$", patch, re.MULTILINE)
    old = re.findall(r"^--- (.+)$", patch, re.MULTILINE)
    new = re.findall(r"^\+\+\+ (.+)$", patch, re.MULTILINE)
    if files != [(target, target)] or old != ["a/" + target] or new != ["b/" + target]:
        raise VerificationError("故障补丁必须且只能修改教师 portfolio-core.js，不能修改测试或学生源码。")


def apply_patch(git: str, root: Path, reverse: bool = False) -> None:
    arguments = [git, "apply"] + (["--reverse"] if reverse else [])
    patch_path = str(root / PROJECT_RELATIVE / "exercises/storage-write-failure/fault.patch")
    for options in (["--check"], []):
        process = execute(arguments + options + [patch_path], root)
        if process.returncode != 0:
            print(process.stdout + process.stderr, file=sys.stderr)
            raise VerificationError("临时副本中的补丁无法应用或反向应用。")


def verify(node: str, git: str, verbose: bool, browser: bool) -> None:
    check_patch_scope()
    original = source_manifest()
    try:
        with tempfile.TemporaryDirectory(prefix="robot-map-fault-") as directory:
            temporary = Path(directory)
            shutil.copytree(PROJECT, temporary / PROJECT_RELATIVE,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
            if browser:
                shutil.copytree(REPOSITORY / "projects/robot_playground",
                                temporary / "projects/robot_playground",
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
                for name in ("teacher_reference/__init__.py", "projects/__init__.py"):
                    original_init = REPOSITORY / name
                    if original_init.is_file():
                        shutil.copy2(original_init, temporary / name)
            pristine_copy = manifest(temporary)

            baseline = run_tests(node, temporary, verbose)
            require_pass(baseline, "基线")
            if browser:
                run_browser(temporary, "基线", False, verbose)

            apply_patch(git, temporary)
            if changed_files(pristine_copy, manifest(temporary)) != {TARGET.as_posix()}:
                raise VerificationError("补丁修改范围超出唯一允许的教师源码文件。")
            mutated = run_tests(node, temporary, verbose)
            if (mutated.names != baseline.names or mutated.returncode != 1
                    or mutated.failures != (REGRESSION,)
                    or mutated.passed != baseline.total - 1):
                if not verbose:
                    print(mutated.output, file=sys.stderr)
                raise VerificationError("故障没有被指定 A09 用例抓住，或出现了意外失败。")
            print(f"故障副本：指定 A09 用例失败，其余 {mutated.passed} 项通过，0 跳过。")
            print(f"  {REGRESSION}")
            if browser:
                run_browser(temporary, "故障副本", True, verbose)

            apply_patch(git, temporary, reverse=True)
            if manifest(temporary) != pristine_copy:
                raise VerificationError("反向补丁后副本未恢复到原始字节。")
            repaired = run_tests(node, temporary, verbose)
            if repaired.names != baseline.names:
                raise VerificationError("反向补丁后的测试集合发生变化。")
            require_pass(repaired, "反向补丁后")
            if browser:
                run_browser(temporary, "反向补丁后", False, verbose)
    finally:
        difference = changed_files(original, source_manifest())
        if difference:
            paths = ", ".join(sorted(difference))
            raise VerificationError(f"验证期间来源文件发生变化，不能确认源码未动：{paths}")
    print(f"来源保持不变：已比较教师项目、学生机器人项目与课程材料共 {len(original)} 个文件。")
    print("故障验证通过；补丁仅在已删除的临时副本中启用。")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="显示三次运行的完整 TAP 报告")
    parser.add_argument("--browser", action="store_true",
                        help="同时用真实 HTTP 浏览器 A09 验证基线、故障与反向补丁")
    args = parser.parse_args()
    node = shutil.which("node")
    git = shutil.which("git")
    if not node or not git:
        print("需要 Node 20+ 和 Git；请先安装缺少的工具。", file=sys.stderr)
        return 2
    try:
        verify(node, git, args.verbose, args.browser)
    except (VerificationError, OSError) as error:
        print(f"故障验证失败：{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
