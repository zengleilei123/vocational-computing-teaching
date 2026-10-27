# 实训 02：真实大模型驱动的工具调用

## 学习目标

在实训 01 的确定性路由基础上，学习如何让模型决定是否调用工具，并在应用侧执行工具、把结果回传给模型。

完成后应能解释：

- 模型生成工具调用请求，不等于工具已经执行
- 应用负责验证工具名、参数和权限
- 工具结果必须以正确的 tool_call_id 回传
- 多轮工具调用必须设置步数上限
- API 失败、参数错误和工具错误应可控处理

## 与实训 01 的区别

| 实训 01 | 实训 02 |
|---|---|
| 规则路由选择工具 | LLM 生成工具调用请求 |
| 不需要 API Key | 需要兼容 OpenAI Chat Completions 工具调用的服务 |
| 离线运行 | 需要配置模型 API |
| 用于讲清控制流 | 用于理解真实模型集成的基本结构 |

## 环境配置

Python 3.10+。安装依赖：

    python -m pip install -r curriculum/ai-agent-development/02-llm-tool-calling/requirements.txt

配置环境变量，不要把密钥写入代码或提交到 Git：

    export OPENAI_API_KEY="你的 API Key"
    export OPENAI_MODEL="你的工具调用模型名称"

可选：若使用兼容 OpenAI API 的服务，设置 OPENAI_BASE_URL 为服务商提供的兼容接口地址。

运行：

    python curriculum/ai-agent-development/02-llm-tool-calling/agent.py

## 安全边界

- 只注册 calculator 和 course_faq 两个低风险工具。
- 工具名必须在白名单内。
- 参数必须是合法 JSON 对象，并经应用侧校验。
- 单次请求最多执行 3 轮模型调用。
- 计算器使用 AST 白名单解析，不使用 eval。
- 不允许执行任意 shell、访问任意文件、发送消息或修改外部系统。
- 自动测试使用假客户端，不会访问网络，也不需要 API Key。

## 学生任务

### 基础任务

1. 配置一个支持工具调用的模型。
2. 运行一次计算器调用和一次课程 FAQ 调用。
3. 观察模型返回的工具名与参数。
4. 故意传入不合法参数，观察应用如何拒绝。

### 提高任务

1. 增加一个只读工具，并补齐 JSON Schema 和测试。
2. 记录模型请求次数、工具调用次数和失败原因。
3. 对同一组输入重复运行，比较工具选择是否稳定。

### 挑战任务

设计一个“不应调用工具”的负例集合，并分析模型是否过度调用工具。不要只保留容易成功的案例。

## 测试

从仓库根目录运行：

    python -m unittest discover -s curriculum/ai-agent-development/02-llm-tool-calling -p "test_*.py" -v

测试使用假客户端，不需要网络或 API Key。
