"""Keep the real fault/recovery evidence readable through legacy output pipes.

The complete-cycle check requires the same Node and Git tools as check_fault;
missing prerequisites are failures, not silently skipped verification.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[3]
MODULE = "teacher_reference.robot_map_portfolio.tools.check_fault"


class FaultToolOutputTests(unittest.TestCase):
    def run_tool(self, **changes):
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.update(PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
        env.update(changes)
        # Capture bytes: text=True with an explicit parent encoding could hide
        # the exact encoding delivered to a student's redirected evidence file.
        result = subprocess.run(
            [sys.executable, "-m", MODULE], cwd=ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=150,
        )
        return (result.returncode, result.stdout.decode("utf-8").replace("\r\n", "\n"),
                result.stderr.decode("utf-8").replace("\r\n", "\n"))

    def test_cp1252_pipe_preserves_the_real_fault_and_recovery_cycle(self):
        self.assertIsNotNone(shutil.which("node"), "This check requires Node 20+.")
        self.assertIsNotNone(shutil.which("git"), "This check requires Git.")
        code, output, errors = self.run_tool()
        self.assertEqual(code, 0, output + errors)
        self.assertEqual(errors, "")
        baseline = re.search(r"^基线：(\d+)/(\d+) 通过，0 跳过。$", output, re.MULTILINE)
        restored = re.search(r"^反向补丁后：(\d+)/(\d+) 通过，0 跳过。$", output, re.MULTILINE)
        mutated = re.search(r"^故障副本：指定 A09 用例失败，其余 (\d+) 项通过，0 跳过。$",
                            output, re.MULTILINE)
        self.assertIsNotNone(baseline, output)
        self.assertIsNotNone(restored, output)
        self.assertIsNotNone(mutated, output)
        count = int(baseline[1])
        self.assertGreater(count, 0)
        self.assertEqual(baseline[1], baseline[2])
        self.assertEqual(restored.groups(), baseline.groups())
        self.assertEqual(int(mutated[1]), count - 1)
        self.assertIn("A09 写入失败时保存、覆盖和删除均不伪报成功或改变已有存档", output)
        self.assertIn("来源保持不变：已比较教师项目、学生机器人项目与课程材料", output)
        self.assertIn("故障验证通过；补丁仅在已删除的临时副本中启用。", output)

    def test_cp1252_pipe_keeps_missing_dependency_diagnostics_readable(self):
        code, output, errors = self.run_tool(PATH="")
        self.assertEqual(code, 2, output + errors)
        self.assertEqual(output, "")
        self.assertEqual(errors, "需要 Node 20+ 和 Git；请先安装缺少的工具。\n")


if __name__ == "__main__":
    unittest.main()
