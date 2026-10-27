"""Unit 01 demo: read a student's name and three scores, then print a summary.

Run:
    python demo.py

This is a teaching example using synthetic input only.
"""


def calculate_average(scores: list[float]) -> float:
    """Return the arithmetic mean of a non-empty list of scores."""
    if not scores:
        raise ValueError("scores must not be empty")
    return sum(scores) / len(scores)


def format_summary(name: str, scores: list[float]) -> str:
    """Build a readable summary for one student."""
    average = calculate_average(scores)
    return (
        f"{name} 的成绩摘要："
        f"平均分 {average:.1f}，"
        f"最高分 {max(scores):.1f}，"
        f"最低分 {min(scores):.1f}"
    )


def main() -> None:
    name = input("请输入姓名：").strip()
    if not name:
        name = "未命名学生"

    scores: list[float] = []
    for index in range(1, 4):
        raw_value = input(f"请输入第 {index} 门成绩（0-100）：").strip()
        try:
            score = float(raw_value)
        except ValueError as exc:
            raise ValueError("成绩必须是数字") from exc

        if not 0 <= score <= 100:
            raise ValueError("成绩必须在 0 到 100 之间")
        scores.append(score)

    print(format_summary(name, scores))


if __name__ == "__main__":
    main()
