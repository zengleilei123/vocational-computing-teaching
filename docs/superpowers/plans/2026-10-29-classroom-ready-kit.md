# Classroom Ready Kit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让教师可复现地发放不含答案的学生包，让学生能诊断环境、完成先修任务并按证据交付 V1/V2。

**Architecture:** 标准库 CLI 对明确白名单打包，保留现有模块路径，生成哈希清单和验收输入。学生学习单与教师组织说明分别维护；现有产品代码和契约不改。

**Tech Stack:** Python 3.10+ 标准库、unittest、Markdown、现有 GitHub Actions。

**Spec:** `docs/superpowers/specs/2026-10-29-classroom-ready-kit-design.md`

## Global Constraints

- `projects/robot_playground/` 和 `curriculum/ai-assisted-development/CAPSTONE.md` 与基线逐字节一致。
- 教师实现和故障答案不得进入学生包；不能使用目录递归复制代替白名单。
- 不增加运行依赖；诊断不自动安装、不联网、不修改配置。
- 教师参考验收与学生作品验收须明确区分。
- Git 管理的交付留在仓库，不重复保存到其他文件存储。

## Review Focus

- 工作目录错误：工具能定位根目录并给下一条可运行命令。
- 无 Git 的 ZIP：来源信息明确为未知或包清单信息，不能读取外层无关仓库冒充来源。
- 已存在目标/缺文件/源符号链接：拒绝且不改原文件；可捕获的写入异常或中断不遗留可误发的半包。
- 学生修改代码之后：环境检查不把“偏离起始哈希”当作作业错误或成绩。
- 边界输入：16384/16385 按 UTF-8 字节生成，输入清单不把人工验证写成自动验证。

## Task 1: 环境诊断与学生包

**Files:** Create `tools/robot_classroom.py`, `tools/test_robot_classroom.py`.

**Interfaces:** CLI `doctor --port N [--json]`, `bundle --output FILE.zip`; 同时可从完整仓库和解压后的包运行 doctor。学生文件路径与 Task 2 保持一致。

- [x] 先写独立行为测试，观察缺少入口导致的失败：可运行包、白名单隔离、哈希与可重复输出、真实端口占用、已存在输出和缺文件/符号链接拒绝。
- [x] 实现最小工具与输入样例；核心功能仅使用标准库。
- [x] 独立审查回归：真实写入部分字节后抛出 `KeyboardInterrupt` / `OSError`，确认新输出被清理；非 UTF-8 重定向下 doctor 与 bundle 正常退出并输出可读结果。
- [x] 解压后运行 `python -m unittest discover -s projects/robot_playground -p 'test_*.py' -v`，断言 37 项且成功，启动真实 HTTP 检查原页面没有作品集控件。
- [x] 使用 `python -m unittest discover -s tools -p 'test_*.py' -v` 验证行为，报告实际结果。

## Task 2: 学生路径与证据

**Files:** Create `classroom/robot_portfolio/student/START.md`, `DIAGNOSTIC.md`, `WORKBOOK.md`, `SUBMISSION.md`.

**Interfaces:** 所有链接从当前目录计算，完整仓库及同结构学生包均可用；包内输入位于根 `fixtures/`。

- [x] 写首次成功路径及 Windows/macOS/Linux 命令选择，区分基础运行与可选浏览器测试。
- [x] 将四项先修要求变成可做的题目与补学出口，不公开教师解析。
- [x] 写五阶段任务卡及 A01–A12 对应关系，保留全部质量约束和个人解释。
- [x] 写提交模板，记录被测对象、四种运行状态、三个独立反例及失败/修复/回归；不自动评分。
- [x] 模板以同目录 `MY-SUBMISSION.md` 复制，保持相对链接，避免 Windows 仅改大小写覆盖原模板。
- [x] 按实际打包路径检查全部命令与内部链接。

## Task 3: 教师组织、入口与 CI

**Files:** Create `classroom/robot_portfolio/README.md`, `SOURCES.md`, `.github/workflows/classroom-kit.yml`; update root/course README、ASSESSMENT、LESSONS、ROADMAP 和教师 ACCEPTANCE 中的入口或验收对象说明。

- [x] 引用已核实的一手来源，编写两学时首次活动、先修反馈和已有评分量规的证据映射。
- [x] 修正过时状态说明，显著指出教师测试并非学生工程通用评分器。
- [x] CI 设置 Ubuntu/3.11 与 Windows/3.10，实际生成/解压/测试学生包；保留其他工作流。
- [x] 独立审查新工具、发包隔离、中文学习路径和文档链接；修复具体发现。
- [ ] 核对学生源码和 CAPSTONE 无改动，提交 PR，等待对应 CI 并合入 main，核对最终树与主分支检查。

## 本地交付前核对

- 2026-10-29：工具 24 项测试全部通过、0 跳过；其中独立解压运行原 37 项测试及真实 HTTP。
- 独立审查发现的中断半包、非 UTF-8 输出和模板复制路径问题已修复并复核。
- 12 份入口/课堂文档的 117 条相对链接有效；学生代码与 CAPSTONE 对基线无差异。
- 本计划保留发布前状态；最后一项的远端 CI 与合并结果以关联 PR 和 Actions 记录为准。
