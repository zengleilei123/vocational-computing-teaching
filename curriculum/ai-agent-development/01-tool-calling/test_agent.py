import unittest

from agent import run_agent, safe_calculate


class TestSafeCalculate(unittest.TestCase):
    def test_arithmetic(self):
        self.assertEqual(safe_calculate("12 * (3 + 4)"), 84)

    def test_division(self):
        self.assertEqual(safe_calculate("8 / 2"), 4)

    def test_rejects_function_calls(self):
        with self.assertRaises(ValueError):
            safe_calculate("__import__('os').system('echo unsafe')")

    def test_rejects_names(self):
        with self.assertRaises(ValueError):
            safe_calculate("x + 1")

    def test_rejects_large_exponent(self):
        with self.assertRaises(ValueError):
            safe_calculate("2 ** 100")


class TestAgent(unittest.TestCase):
    def test_calculator_tool(self):
        result = run_agent("计算 12 * (3 + 4)")
        self.assertTrue(result.ok)
        self.assertEqual(result.tool_name, "calculator")
        self.assertEqual(result.output, "84")

    def test_faq_tool(self):
        result = run_agent("查询 Python 课程需要哪些先修知识")
        self.assertTrue(result.ok)
        self.assertEqual(result.tool_name, "course_faq")
        self.assertIn("基本电脑操作", result.output)

    def test_faq_variants_route_to_tool(self):
        for query in ("什么是智能体", "我零基础应该怎么学", "课程顺序是什么"):
            with self.subTest(query=query):
                result = run_agent(query)
                self.assertEqual(result.tool_name, "course_faq")

    def test_unknown_request_does_not_call_tool(self):
        result = run_agent("帮我删除所有文件")
        self.assertFalse(result.ok)
        self.assertEqual(result.tool_name, "none")

    def test_bad_calculation_returns_error(self):
        result = run_agent("计算 1 / 0")
        self.assertFalse(result.ok)
        self.assertEqual(result.tool_name, "calculator")


if __name__ == "__main__":
    unittest.main()
