# CoursePilot：贯穿式智能课程助教

不是另一个孤立 RAG Demo。本项目把**同一名合成学习者、同一套课程、同一份学习记录**贯穿数据处理、数据库、算法、工具调用、工作流、HTTP、测试和部署。面向高职/专科计算机与人工智能相关课程，不绑定具体地区或院校。

## 一条业务主线

> 我已经学过 Python，想学习智能体。还缺哪些先修知识？请结合课程资料给我一份计划，确认后再保存为已批准状态。

```text
CSV 练习记录 → 校验与事务导入 → SQLite 学情统计
                                 ↓
课程先修图 → 拓扑排序 → 过滤达标知识点 → 学习计划草稿
                                 ↑
课程资料 → 关键词检索 → 原文与来源
                                 ↓
应用工具层 ← 固定工作流 / 可选大模型工具选择
                                 ↓
pending 计划 → 用户显式确认 → approved → 审计与回归评测
```

SQLite 保存的是合成练习记录，不是学校真实成绩。70 分阈值只为展示规则，不是经过验证的掌握度模型。先修图也是本项目的教学设计，不代表所有院校的标准。

## 快速运行：默认完全离线

Python 3.10+；默认只用标准库。在**仓库根目录**运行：

```bash
python projects/coursepilot/app.py --db :memory: demo
python projects/coursepilot/app.py evaluate
python -m unittest discover -s projects/coursepilot -p "test_*.py" -v
```

第一条命令输出 Python 90、SQL 40、算法 50 的合成学情，待补课程顺序为：

```text
algorithms → sql → api → agents
status: pending
```

SQL、算法、API 之间没有互相先修关系，因此它们也可能存在其他合法拓扑顺序；当前实现采用稳定的输入顺序。这里的输出只是规则规划，不是 LLM 推理。

## 数据、计划、确认共用同一个数据库

```bash
python projects/coursepilot/app.py --db coursepilot.db demo
python projects/coursepilot/app.py --db coursepilot.db import-csv projects/coursepilot/sample-records.csv
python projects/coursepilot/app.py --db coursepilot.db progress
python projects/coursepilot/app.py --db coursepilot.db approve PLAN_ID_FROM_DEMO --confirm
python projects/coursepilot/app.py --db coursepilot.db events
```

将 `PLAN_ID_FROM_DEMO` 替换为第一步输出的 `plan.id`。不带 `--confirm` 会拒绝批准；重复批准不会重复产生批准事件。批准只改变计划状态，**不会改动成绩**。演示初始化是幂等的；CSV 导入是追加操作，重复导入会增加练习次数，暂未实现来源记录去重。

## 可选真实模型入口

先安装已有实训 02 的依赖，使用你有权限使用的服务；调用可能收费并向服务商发送合成学情和检索材料。不要使用真实学生信息。

```bash
python -m pip install -r curriculum/ai-agent-development/02-llm-tool-calling/requirements.txt
# 设置 OPENAI_API_KEY 与 OPENAI_MODEL；可选 OPENAI_BASE_URL 必须是 HTTPS API 根地址。
# SDK 的 base_url 例如以 /v1 结尾，不是完整的 /chat/completions 请求路径。
python projects/coursepilot/app.py --db coursepilot.db chat "查看我的学情，检索工具调用资料，并创建 agents 学习计划草稿"
```

真实适配器使用 Chat Completions 工具调用格式，默认无重试、20 秒超时。模型可调用 `progress`、`search`、`draft`，**没有 approve 工具**；学习者身份由宿主绑定，不接受模型指定其他学习者。默认最多 4 次模型请求、6 次工具执行，最后一轮不再执行无法回传结果的工具。

离线测试使用注入式假客户端验证消息协议和控制流。它不证明真实 API 兼容性、引用真实性、推理质量或提示注入防护完整有效。最终自然语言可能出错，仍需独立核验。

## 本地 HTTP API

只有合成 `demo` 身份；无生产级登录、角色管理或 TLS。Python `http.server` 不用于生产部署；本例强制监听 127.0.0.1，不要改为公网监听。

```bash
# macOS/Linux 示例；令牌仅在你的本地生成，不写进仓库。
export COURSEPILOT_TOKEN="$(python -c 'import secrets; print(secrets.token_hex(24))')"
python projects/coursepilot/app.py --db coursepilot.db serve
```

另一个终端设置相同令牌后：

```bash
curl http://127.0.0.1:8000/health
curl -H "Authorization: Bearer $COURSEPILOT_TOKEN" -H 'Content-Type: application/json' \
  -d '{"goal":"agents","query":"工具调用参数校验"}' http://127.0.0.1:8000/api/run
```

| 接口 | 作用 | 权限与边界 |
|---|---|---|
| GET /health | 健康检查 | 无需令牌，无数据 |
| GET /api/progress | 读取 demo 学情 | 需要令牌 |
| POST /api/run | 执行离线工作流，创建 pending 计划 | 需要令牌，只允许 goal/query |
| POST /api/approve | `{ "id": "...", "confirmed": true }` | 需要令牌及布尔真值；不是模型工具 |

令牌是本机演示的基本访问限制，不等同于生产环境教师/学生权限隔离。

## 文件如何串起来

| 文件 | 责任 | 教学知识点 |
|---|---|---|
| core.py | 共享数据与业务规则 | CSV、类型校验、SQL、事务、DAG、检索、状态转换 |
| agents.py | 共用工具的两类控制器 | 函数接口、JSON Schema、工具白名单、预算、依赖注入 |
| api.py | HTTP 适配器 | 请求/响应、状态码、令牌、分层架构 |
| app.py | CLI 与可重复评测 | 命令行、配置、实验统计、失败退出码 |
| test_coursepilot.py | 单元与集成测试 | 假客户端、临时数据库、实际 HTTP、回归 |

检索资料是 `core.py` 中原创教学条目，不是自动爬取的院校政策。每条证据携带条目 id、正文、来源文件与匹配分数。

## 评测口径

`evaluate` 使用 8 个固定合成回归场景，每个场景重建内存数据库。通过率 = 满足预期断言的场景数 / 8；包含命中、拒答、路径规划、待确认状态、非法确认、越权工具、非法数据和合法批准。**8/8 不代表模型准确率 100%，更不代表教学有效性。**

## 可选容器实验

```bash
docker build -t coursepilot-demo projects/coursepilot
docker run --rm coursepilot-demo
```

该 Dockerfile 只执行离线内存数据库演示，不开放网络端口、不包含密钥。容器构建结果与 Python 测试结果分别验证，不能互相替代。

## 课程主线与后续扩展

完整映射见 [贯穿式课程设计](../../docs/INTEGRATED-COURSE.md)，课堂流程见 [TEACHING.md](TEACHING.md)。前端、传统机器学习训练、Embedding/Rerank、MCP、语音视觉尚未集成，不作为本版本的完成项。
