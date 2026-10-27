"""LLM-driven tool-calling lesson using the OpenAI-compatible Chat Completions API.

The model may request a tool, but this application validates and executes it.
Only two low-risk tools are registered. Never pass arbitrary model output to eval,
a shell, filesystem, or an unrestricted external action.
"""
from __future__ import annotations

import ast
import json
import operator
import os
from typing import Any, Callable

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore[assignment,misc]

MAX_MODEL_TURNS = 3

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "计算一个简单的算术表达式。",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "course_faq",
            "description": "查询本地内置的课程 FAQ；未找到时应如实说明。",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
]


def safe_calculate(expression: str) -> int | float:
    if not expression or len(expression) > 80:
        raise ValueError("表达式为空或过长")

    binary_ops: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
        ast.Add: operator.add, ast.Sub: operator.sub,
        ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }
    unary_ops: dict[type[ast.unaryop], Callable[[Any], Any]] = {
        ast.UAdd: operator.pos, ast.USub: operator.neg,
    }

    def visit(node: ast.AST) -> int | float:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            if abs(node.value) > 1_000_000_000:
                raise ValueError("数字超出允许范围")
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in binary_ops:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 6:
                raise ValueError("指数超出允许范围")
            result = binary_ops[type(node.op)](left, right)
            if isinstance(result, (int, float)) and abs(result) > 1e12:
                raise ValueError("结果超出允许范围")
            return result
        if isinstance(node, ast.UnaryOp) and type(node.op) in unary_ops:
            return unary_ops[type(node.op)](visit(node.operand))
        raise ValueError("表达式包含不支持的语法")

    try:
        return visit(ast.parse(expression, mode="eval"))
    except (SyntaxError, ZeroDivisionError, OverflowError, RecursionError) as exc:
        raise ValueError("算术表达式无效") from exc


def calculator_tool(arguments: dict[str, Any]) -> str:
    expression = arguments.get("expression")
    if not isinstance(expression, str):
        raise ValueError("expression 必须是字符串")
    return str(safe_calculate(expression))


FAQ = {
    "python先修知识": "建议先会基本电脑操作；编程零基础也可以从本课程第一个单元开始。",
    "课程学习顺序": "建议顺序：Python 基础、数据结构与算法、SQL 与数据库、API 与软件工程、AI 应用开发。",
    "智能体是什么": "智能体应用会组合模型、指令、工具、状态和控制流程；并非所有任务都需要智能体。",
}


def course_faq_tool(arguments: dict[str, Any]) -> str:
    query = arguments.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query 必须是非空字符串")
    normalized = query.strip().lower()
    for key, answer in FAQ.items():
        if key.lower() in normalized or normalized in key.lower():
            return answer
    return "本地课程 FAQ 没有找到匹配内容，请补充资料或转人工核对。"


TOOLS: dict[str, Callable[[dict[str, Any]], str]] = {
    "calculator": calculator_tool,
    "course_faq": course_faq_tool,
}


def execute_tool(name: str, raw_arguments: str) -> str:
    """Validate tool name and JSON arguments before calling an allowlisted tool."""
    if name not in TOOLS:
        raise ValueError(f"工具不在白名单中：{name}")
    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        raise ValueError("工具参数不是合法 JSON") from exc
    if not isinstance(arguments, dict):
        raise ValueError("工具参数必须是 JSON 对象")
    return TOOLS[name](arguments)


def run_agent(client: Any, model: str, user_text: str, max_turns: int = MAX_MODEL_TURNS) -> str:
    """Run a bounded tool-calling loop with an injected client for testability."""
    if max_turns < 1 or max_turns > 5:
        raise ValueError("max_turns 必须在 1 到 5 之间")

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "你是一个教学用助手。只有确实需要时才调用已提供的只读工具。"
                "如果工具未找到资料，应如实说明。不要声称执行了未调用的工具。"
            ),
        },
        {"role": "user", "content": user_text},
    ]

    for _ in range(max_turns):
        response = client.chat.completions.create(
            model=model, messages=messages, tools=TOOL_SCHEMAS, tool_choice="auto"
        )
        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            return getattr(message, "content", None) or "模型未返回文本内容。"

        messages.append(message.model_dump(exclude_none=True))
        for call in tool_calls:
            try:
                output = execute_tool(call.function.name, call.function.arguments)
            except (ValueError, TypeError) as exc:
                output = json.dumps({"error": str(exc)}, ensure_ascii=False)
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": output,
            })

    return "已达到最大模型调用轮数，任务未继续执行。请缩小任务范围或增加人工检查。"


def main() -> None:
    if OpenAI is None:
        raise SystemExit(
            "缺少 openai 依赖。请先安装 curriculum/ai-agent-development/02-llm-tool-calling/requirements.txt"
        )
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL")
    base_url = os.getenv("OPENAI_BASE_URL")
    if not api_key or not model:
        raise SystemExit("请设置 OPENAI_API_KEY 和 OPENAI_MODEL 环境变量。")

    client = OpenAI(api_key=api_key, base_url=base_url or None)
    print("教学用 LLM 工具调用助手。输入 q 退出。")
    while True:
        text = input("\n你：").strip()
        if text.lower() in {"q", "quit", "exit"}:
            break
        try:
            print("助手：" + run_agent(client, model, text))
        except Exception as exc:
            print(f"请求失败：{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
