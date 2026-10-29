# 课堂实训项目包：从业务开发到 AI，再到教学反馈

面向已学过 Python 函数、列表/字典与异常的高职学生。这里是基于实际业务问题设计的**教学模拟**，不是已有学校部署的系统；数据全部合成，没有课堂效果验证。

## 三个项目，同一条教学链

| 项目 | 建议课时（每学时45分钟） | 学生交付 | 入口 |
|---|---:|---|---|
| 实训室设备预约 | 6 | 数据表、预约/取消实现、冲突与并发测试 | [任务书](lessons/01-booking.md) / [参考实现](booking.py) |
| 校园报修工单分类 | 8 | 标注规范、训练与评测脚本、错误分析 | [任务书](lessons/02-tickets.md) / [参考实现](classifier.py) |
| 项目验收与补学计划 | 4 | 证据CSV、幂等导入、学情与待确认计划 | [任务书](lessons/03-feedback.md) / [参考实现](assessment.py) |

课时是建议，不是国家标准或学校考纲。不要把18学时当作从零掌握整个技术栈所需时间。

设备预约 → 学生完成软件实训 → 教师验收并给出能力项分数；报修分类 → 学生完成训练、评价与误差分析 → 教师验收；两类验收证据导入 **原有 CoursePilot Store** → SQL 学情统计 → 先修图补学路径 → 检索课程证据 → 待确认学习计划。

这三个模块是命令行和库级参考实现；**尚未接入 CoursePilot 的 HTTP 页面或 LLM 工具注册表**。不把计划生成功能伪装成真实教务写入能力，也不自动依据模型指标给学生打分。

## 运行（在仓库根目录）

Python 3.10+；只用标准库；不需要 GPU、网络、API Key 或第三方依赖。

```bash
python -m projects.classroom_practice.app booking
python -m projects.classroom_practice.app classify
python -m projects.classroom_practice.app feedback
python -m unittest discover -s projects/classroom_practice -p "test_*.py" -v
```

`booking` 展示预约成功、重叠拒绝、显式取消、另一用户再预约。
`classify` 真正从训练样本估计朴素贝叶斯参数，对验证集和测试集生成报告，并对比手写规则。没有调用大模型。
`feedback` 导入5条教师评分示例；再次导入应显示 imported=0, skipped=5；补学路径为 sql → api → agents，状态保持 pending。
三个默认演示都在内存运行，不写持久化数据库；库接口可传入本地SQLite路径。

## 先学会解决问题，再加 AI

预约冲突由区间规则和事务解决，不交给 LLM 猜；报修分类才使用训练后的模型；不能确定的分类转人工。教师给出的分数才进入学情，生成的学习计划不自动批准。

## 教师与学生使用方式

教师先阅读[课堂组织指南](TEACHER-GUIDE.md)，发任务书、数据与[提交模板](SUBMISSION.md)，让学生先画流程与列验收条件，再看参考实现。每个任务书均包含基础/提高/挑战任务、典型错误与现场答辩问题。代码是参考解，不是学生已经完成的作品。

## 数据与验证边界

数据说明见[data/README.md](data/README.md)。57条工单（训练36/验证9/测试12）仅验证教学流程，不能用于宣称线上性能。分组检查可防止同一group跨集，但无法自动证明同义文本没有泄漏。

身份字符串、`confirmed=True` 都只是本地教学约定，不是身份认证与生产授权。没有真实派单、学生代码执行、个人数据处理或正式成绩发布。

教学设计与工程依据：[SOURCES.md](SOURCES.md)。许可证沿用仓库说明，第三方资料只链接，不复制教材或题库。
