"""Unit tests for the first teaching demo. Run: python -m unittest.""" 

import unittest

from demo import calculate_average, format_summary


class TestScoreSummary(unittest.TestCase):
    def test_calculate_average(self):
        self.assertEqual(calculate_average([80.0, 90.0, 100.0]), 90.0)

    def test_empty_scores_raise(self):
        with self.assertRaises(ValueError):
            calculate_average([])

    def test_format_summary(self):
        summary = format_summary("小林", [80.0, 90.0, 100.0])
        self.assertIn("小林", summary)
        self.assertIn("平均分 90.0", summary)
        self.assertIn("最高分 100.0", summary)
        self.assertIn("最低分 80.0", summary)


if __name__ == "__main__":
    unittest.main()
