# Vocational Computing Teaching

[![Teaching repository checks](https://github.com/zengleilei123/vocational-computing-teaching/actions/workflows/teaching-checks.yml/badge.svg)](https://github.com/zengleilei123/vocational-computing-teaching/actions/workflows/teaching-checks.yml)

面向高职计算机类专业的课程设计、编程教学、算法训练、软件工程实训与人工智能应用开发资源库。

本仓库以“能讲清、能运行、能练习、能评价”为原则，持续沉淀可复用的教学材料与小型工程项目。它不是某所学校的官方课程，也不替代具体院校的人才培养方案。

## 新增可玩项目：校园机器人挑战场

[项目与启动说明](projects/robot_playground/README.md) · [四学时教学设计](projects/robot_playground/TEACHING.md) · [学生自选挑战](projects/robot_playground/CHALLENGES.md)

设计地图让机器人送达，对比 BFS 的最少步数与 Dijkstra 的最低成本；画自己的方向符号，用 k-NN 教机器人识别，再用独立样本测试。支持网页操作、地图编辑、路线回放、实验导出，不需要 API Key 或 GPU。没有真实机器人控制、公开排行榜或自动成绩写入。

```bash
python -m projects.robot_playground.server --port 8765
# 浏览器打开 http://127.0.0.1:8765
```

学生从“运行老师的代码”走向“设计自己的关卡、策略和数据”。[教学动机与项目总览](docs/PLAYFUL-PROJECTS.md)明确区分设计依据和真实课堂验证，不能用通关分数推断学习效果。

## 贯穿式主项目：CoursePilot

从“我想学智能体，需要补什么？”出发，用同一套合成数据串起 **Python → CSV 数据处理 → SQL → 图算法 → 检索 → 工具调用 → 人工确认 → HTTP → 测试与部署**。RAG 只是其中一个环节。

- [项目说明与运行](projects/coursepilot/README.md)
- [完整课程映射：技术为什么需要、在哪实现、如何验收](docs/INTEGRATED-COURSE.md)
- [90 分钟教学脚本与分层练习](projects/coursepilot/TEACHING.md)

```bash
python projects/coursepilot/app.py --db :memory: demo
python projects/coursepilot/app.py evaluate
python -m unittest discover -s projects/coursepilot -p "test_*.py" -v
```

默认完全离线，Python 3.10+ 标准库即可；可选真实模型入口须另配服务。CoursePilot 主流程尚无网页工作台、向量检索或分类工具接入；下面的课堂项目包已另行实现可训练的报修分类实验，不混淆独立模块与已集成能力。

## 可直接布置的课堂实训

[三项目总入口与课时安排](docs/CLASSROOM-PROJECTS.md) · [教师组织指南](projects/classroom_practice/TEACHER-GUIDE.md) · [学生提交模板](projects/classroom_practice/SUBMISSION.md)

| 项目 | 训练重点 | 教学任务 |
|---|---|---|
| 实训室设备预约 | SQL、区间冲突、事务、幂等和并发 | [任务书](projects/classroom_practice/lessons/01-booking.md) |
| 校园报修工单分类 | 标签、特征、朴素贝叶斯训练、指标与错例 | [任务书](projects/classroom_practice/lessons/02-tickets.md) |
| 实训验收与补学计划 | 证据CSV、去重、回滚、原有Store与先修图 | [任务书](projects/classroom_practice/lessons/03-feedback.md) |

```bash
python -m projects.classroom_practice.app booking
python -m projects.classroom_practice.app classify
python -m projects.classroom_practice.app feedback
python -m unittest discover -s projects/classroom_practice -p "test_*.py" -v
```

数据全部合成；参考实现已配测试，不代表真实课堂效果。教师人工验收的能力项证据可以接回 CoursePilot；不会自动把模型准确率当作学生成绩，也不实际派单或修改教务系统。

## 建设目标

- **基础课程**：Python 程序设计、数据结构与算法、SQL 与数据库。
- **工程能力**：需求分析、模块化开发、Git、测试、日志、部署和文档。
- **AI 应用开发**：大模型 API、结构化输出、工具调用、RAG、智能体工作流、评测与安全。
- **教学设计**：每个模块尽可能提供学习目标、教案、示例代码、分层练习、测试用例和评价标准。
- **实践导向**：综合项目负责贯通，独立实训用于拆解知识点，避免只有代码或提示词合集。

## 课程路线

| 路线 | 主要内容 | 当前入口 |
|---|---|---|
| Python 程序设计 | 基础语法、函数、数据结构、文件、异常与测试 | [课程单元 01](curriculum/python-programming/01-basics/README.md) |
| 数据结构与算法 | 图、拓扑排序、复杂度与边界测试 | [CoursePilot 课程映射](docs/INTEGRATED-COURSE.md) |
| 数据库与数据处理 | CSV、SQL、数据建模、聚合与事务 | [CoursePilot 业务服务](projects/coursepilot/core.py) |
| 软件工程实训 | 分层接口、依赖注入、HTTP、配置与测试 | [CoursePilot](projects/coursepilot/README.md) |
| AI 智能体开发 | 工具调用、RAG、工作流、评测与安全 | [AI 智能体课程](curriculum/ai-agent-development/README.md) |
| 检索入门 | 关键词基线、来源、拒答 | [RAG 实训 03](curriculum/ai-agent-development/03-rag/README.md) |
| 机器学习实训 | 字符特征、训练与验证/测试隔离、分类与误差分析 | [报修分类](projects/classroom_practice/lessons/02-tickets.md) |
| 综合教学 | 同一业务逐层深化 | [课程映射](docs/INTEGRATED-COURSE.md) / [路线图](ROADMAP.md) |

## 目标学习者与使用方式

面向高职计算机类学生和初学者。零基础先学 Python，再进入综合项目；不要直接要求学生一次读完所有代码。教师可先使用 [教案模板](docs/templates/lesson-plan-template.md)，再按项目的分层任务组织课堂。

AI 实训 01 是确定性脚手架；[实训 02](curriculum/ai-agent-development/02-llm-tool-calling/README.md)演示真实模型工具调用接口、通过假客户端离线测试；实训 03 为关键词检索。CoursePilot 将这些概念接到同一业务与数据上，而不是重复增加孤立 Demo。

## 质量与安全

示例必须有运行方法、输入输出、约束和测试；参考答案解释原因。智能体需要工具权限、失败处理、预算和人工确认边界。只提交公开或自行构造的数据，不提交真实学生信息、商业机密、密钥或未经授权材料。完整规范见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 自动检查与验证范围

GitHub Actions 保留 Python 基础课、两类工具调用、检索和 JSON 检查，并加入 CoursePilot 编译、单元/集成测试与离线回归，以及课堂三项目的业务测试和命令行演示。机器人挑战场增加 Python/HTTP 测试、JavaScript 语法检查及独立 Chromium 浏览器作业。通过状态看具体提交对应的 [Actions](https://github.com/zengleilei123/vocational-computing-teaching/actions)，不能仅以文件存在宣称功能通过。

代码测试通过、真实模型 API 验证、容器运行成功和真实课堂有效是四种不同证据。当前项目以合成数据和教学场景验证；真实 API、容器构建与课堂效果仍需分别验证。

## 许可与引用

原创代码许可见 [LICENSE-CODE](LICENSE-CODE)；原创教学文档说明见 [LICENSE-DOCS.md](LICENSE-DOCS.md)。第三方资料遵守原始许可。研究依据见 [课程映射](docs/INTEGRATED-COURSE.md#研究与设计依据2026-10-28-核对)、[课堂项目依据](projects/classroom_practice/SOURCES.md) 与 [可玩项目依据](projects/robot_playground/SOURCES.md)。
