"""Teaching scaffold for tool-using agents.

This is a deterministic router, NOT an autonomous LLM agent. It demonstrates
tool registration, allowlisting, validation, execution, and bounded control flow
without network access or third-party dependencies.
"""

from __future__ import annotations

import ast
import operator
import re
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    tool_name: str
    output: str


def safe_calculate(expression: str) -> float | int:
    """Evaluate a small arithmetic expression using an AST allowlist."""
    if not expression or len(expression) > 80:
        raise ValueError("expression is empty or too long")

    binary_ops: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }
    unary_ops: dict[type[ast.unaryop], Callable[[Any], Any]] = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }

    def visit(node: ast.AST) -> float | int:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            if abs(node.value) > 1_000_000_000:
                raise ValueError("number is too large")
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in binary_ops:
            left = visit(node.left)
            right = visit(node.right)
            if isinstance(node.op, ast.Pow) and not 0 <= abs(right) <= 6:
                raise ValueError("exponent is outside the allowed range")
            value = binary_ops[type(node.op)](left, right)
            if isinstance(value, (int, float)) and abs(value) > 1e12:
                raise ValueError("result is too large")
            return value
        if isinstance(node, ast.UnaryOp) and type(node.op) in unary_ops:
            return unary_ops[type(node.op)](visit(node.operand))
        raise ValueError("unsupported expression")

    try:
        tree = ast.parse(expression, mode="eval")
        return visit(tree)
    except (SyntaxError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError("invalid arithmetic expression") from exc


def calculator_tool(arguments: dict[str, Any]) -> str:
    expression = arguments.get("expression")
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("expression must be a non-empty string")
    return str(safe_calculate(expression.strip()))


FAQ: dict[str, str] = {
    "python先修知识": "建议先会基本电脑操作；编程零基础也可以从本课程的第一个单元开始。",
    "课程学习顺序": "建议顺序：Python 基础、数据结构与算法、SQL 与数据库、API 与软件工程、AI 应用开发。",
    "智能体是什么": "智能体是围绕模型组织指令、状态、工具和控制流程的应用系统；并非每个任务都需要智能体。",
}


def course_faq_tool(arguments: dict[str, Any]) -> str:
    query = arguments.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    normalized = query.strip().lower()
    for key, answer in FAQ.items():
        if key.lower() in normalized or normalized in key.lower():
            return answer
    return "课程资料中没有找到匹配条目，请补充资料或转人工核对。"


TOOLS: dict[str, Callable[[dict[str, Any]], str]] = {
    "calculator": calculator_tool,
    "course_faq": course_faq_tool,
}

MAX_STEPS = 1


def route_request(user_text: str) -> tuple[str, dict[str, Any]] | None:
    """A transparent rule-based planner for the introductory lesson."""
    text = user_text.strip()
    if not text:
        return None

    match = re.match(r"^(?:计算|算一下|calculate)\s*(.+)$", text, re.IGNORECASE)
    if match:
        return "calculator", {"expression": match.group(1)}

    if any(keyword in text for keyword in ("先修知识", "学习顺序", "智能体是什么")):
        return "course_faq", {"query": text}

    return None


def run_agent(user_text: str) -> ToolResult:
    """Run at most one allowlisted tool and return a normalized result."""
    plan = route_request(user_text)
    if plan is None:
        return ToolResult(False, "none", "暂时无法识别请求。请尝试计算表达式或查询课程 FAQ。")

    tool_name, arguments = plan
    if tool_name not in TOOLS:
        return ToolResult(False, tool_name, "工具不在允许列表中。")

    if MAX_STEPS < 1:
        return ToolResult(False, tool_name, "超过最大执行步数。")

    try:
        output = TOOLS[tool_name](arguments)
        return ToolResult(True, tool_name, output)
    except (ValueError, TypeError) as exc:
        return ToolResult(False, tool_name, f"工具执行失败：{exc}")


def main() -> None:
    print("教学示例：本地工具调用助手（输入 q 退出）")
    print("示例：计算 12 * (3 + 4)；查询 Python 课程需要哪些先修知识")
    while True:
        request = input("\n你：").strip()
        if request.lower() in {"q", "quit", "exit"}:
            print("已退出。")
            break
        result = run_agent(request)
        print(f"工具：{result.tool_name}")
        print(f"状态：{'成功' if result.ok else '未完成'}")
        print(f"结果：{result.output}")


if __name__ == "__main__":
    main()
