import json
import unittest
from types import SimpleNamespace

from agent import execute_tool, run_agent, safe_calculate


def api_response(message):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def make_tool_call(name, arguments, call_id="call_1"):
    raw = json.dumps(arguments, ensure_ascii=False)
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=raw),
    )


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("没有剩余的模拟响应")
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.chat = SimpleNamespace(completions=FakeCompletions(responses))


class TestToolSafety(unittest.TestCase):
    def test_safe_calculation(self):
        self.assertEqual(safe_calculate("12 * (3 + 4)"), 84)

    def test_reject_unknown_tool(self):
        with self.assertRaises(ValueError):
            execute_tool("shell", '{"command": "echo unsafe"}')

    def test_reject_invalid_json(self):
        with self.assertRaises(ValueError):
            execute_tool("calculator", "not-json")

    def test_reject_expression_with_names(self):
        with self.assertRaises(ValueError):
            execute_tool("calculator", '{"expression": "x + 1"}')


class TestAgentLoop(unittest.TestCase):
    def test_tool_call_then_final_answer(self):
        tool_message = SimpleNamespace(
            role="assistant",
            content=None,
            tool_calls=[make_tool_call("calculator", {"expression": "2 + 3"})],
            model_dump=lambda exclude_none=True: {
                "role": "assistant",
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "calculator",
                        "arguments": '{"expression": "2 + 3"}',
                    },
                }],
            },
        )
        final_message = SimpleNamespace(role="assistant", content="结果是 5。", tool_calls=None)
        client = FakeClient([api_response(tool_message), api_response(final_message)])

        result = run_agent(client, "fake-model", "计算 2+3")

        self.assertEqual(result, "结果是 5。")
        self.assertEqual(len(client.chat.completions.calls), 2)
        second_messages = client.chat.completions.calls[1]["messages"]
        self.assertTrue(any(message.get("role") == "tool" for message in second_messages))

    def test_stops_at_max_turns(self):
        tool_message = SimpleNamespace(
            role="assistant",
            content=None,
            tool_calls=[make_tool_call("calculator", {"expression": "2 + 3"})],
            model_dump=lambda exclude_none=True: {
                "role": "assistant",
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "calculator",
                        "arguments": '{"expression": "2 + 3"}',
                    },
                }],
            },
        )
        client = FakeClient([api_response(tool_message)])
        result = run_agent(client, "fake-model", "计算 2+3", max_turns=1)
        self.assertIn("最大模型调用轮数", result)
        self.assertEqual(len(client.chat.completions.calls), 1)


if __name__ == "__main__":
    unittest.main()
