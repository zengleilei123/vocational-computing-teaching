# 课堂发放与首次活动：来源和设计决定

**最后核对：2026-10-29。** 本页只说明本轮课堂材料如何使用来源，不把设计依据写成已经取得的课堂效果。课程尚未试教；自动测试能检查程序和发包流程，不能据此推断学生理解、学习主动性或长期迁移能力。

## S1：教育部软件技术专业教学标准（2025）

[《软件技术专业教学标准（高等职业教育专科，510203）》官方 PDF](https://hudong.moe.gov.cn/s78/A07/zcs_ztzl/2017_zt06/17zt06_bznr/bznr_zyjyzyjxbz/gdzyjy_zk/zk_dzyxxdl/dzxxdl_jsjl/202502/P020250207533323690137.pdf)

核对位置：§8.1.2（第 3 页）提出以真实生产项目、典型工作任务开展项目式、情境式教学；软件测试课程表（第 4–5 页）包含测试计划、用例设计、缺陷报告及质量分析；§11.1（第 8 页）要求强化过程评价，并利用评价结果改进教学。

**本轮采用：** 学生提交不仅包含成品，还包括用户需求、实际运行环境、预期与实际结果、缺陷复现、修复 diff、回归和同学验收；教师按已有量规观察过程证据。这些条款支持任务与证据的安排，没有指定本仓库、Vibe Coding 工具或某一种自动评分办法。

## S2：PRIMM 的活动顺序

[Raspberry Pi Foundation：PRIMM: encouraging talk in programming lessons](https://www.raspberrypi.org/blog/primm-talk-in-programming-lessons-research-seminar/)（2020-11-13）

该研究介绍将 PRIMM 展开为 Predict、Run、Investigate、Modify、Make：先阅读与预测，再运行比较，随后追踪、解释代码，逐步进入修改与创作；它也强调学习者谈论程序如何工作。

**本轮采用：** 首次活动从能够运行的机器人和短程序开始；学生先留下自己的预测，再与同伴运行、解释，最后完成小改动与独立输入。教师提供逐步减少的帮助，不直接把整套地图存档答案交给学生。文中介绍的是既有研究情境，不能直接当作本高职课程使用 AI 后的效果证据。

## S3：形成性反馈与代码理解

[Raspberry Pi Foundation：Our computing pedagogy](https://www.raspberrypi.org/teach/pedagogy)

重点核对 `Challenge misconceptions`、`Foster program comprehension`、`Read and explore code first`、`Structure lessons` 和 `Work together`：通过提问发现误解，安排追踪、调试和解释，采用 PRIMM / Use-Modify-Create，组织结对与同伴讨论。

**本轮采用：** 四项先修诊断记录“独立完成／提示后完成／尚未完成”，每项都有补练与复查；教师反馈指出一个具体误解及下一步动作。两人小组轮换操作与复核角色，每人仍需独立说明自己的结果。诊断用于决定支持方式，不另造一套分数。

## S4：普通仓库的测试反馈与证据保留

[GitHub Docs：Building and testing Python](https://docs.github.com/en/actions/tutorials/build-and-test-code/python)

核对 `Specifying a Python version`、`Testing your code`、`Packaging workflow data as artifacts`：普通仓库可以配置 CI 测试、明确 Python 环境，并将测试结果等保存为 artifacts；文档示例在测试失败时也保留结果。

**本轮采用：** CI 验证发包工具、实际解压的学生包和旧功能，并提供包文件用于检查；课堂保留等价的本地命令。自动结果用于提供反馈和定位问题，学生新增功能仍须针对实际作品独立验收。

## S5：GitHub Classroom 的服务变化

[GitHub 官方公告：Thank you for being part of the GitHub Classroom journey](https://github.com/orgs/community/discussions/205975)（2026-08-27 发布，注明 2026-08-28 退役）

公告说明 GitHub Classroom 服务已经退役，原有账户、仓库和组织不受该服务退役影响。

**本轮采用：** 发包和上课不依赖 Classroom 账号或其分发、评分界面；继续使用普通仓库、ZIP、本地 Python 和已有 GitHub Actions。无需为了完成本单元先购买或迁移到其他教学平台。

## 后续怎样记录教学证据

试教时分别保留环境与程序运行证据、学生独立任务表现、反馈后的修改以及简短学习体验记录。需要研究学习进步时，再使用难度相近、题目不同的前后任务；不要把测试全绿、提交次数或一次课后自评直接写成教学因果效果。
