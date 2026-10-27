import unittest

from rag_demo import answer_with_sources, retrieve


class TestRetrieval(unittest.TestCase):
    def test_retrieves_tool_safety_document(self):
        results = retrieve("智能体工具调用安全白名单")
        self.assertTrue(results)
        self.assertIn("工具调用", results[0].document.keywords)

    def test_answer_contains_source(self):
        answer = answer_with_sources("Python 学习顺序和 SQL 数据库")
        self.assertIn("来源：", answer)
        self.assertIn("Python 课程学习顺序", answer)

    def test_unknown_query_refuses_without_fabricated_source(self):
        answer = answer_with_sources("火星天气和海底火山")
        self.assertIn("没有检索到足够依据", answer)
        self.assertNotIn("来源：", answer)

    def test_top_k_validation(self):
        with self.assertRaises(ValueError):
            retrieve("Python", top_k=0)


if __name__ == "__main__":
    unittest.main()
