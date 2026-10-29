# 验证记录（2026-10-29）

本记录只描述代码验证，不代表已经进行真实课堂试教或证明学习效果。

## 范围与环境

- 基线：`feat/coursepilot-integrated-learning` 的 `940ba7ee616d160e47d6e41d5473792105ac6470`。
- Python 3.12.14、Node 24.22.1、Python Playwright 1.57.0。
- 真实 Chromium 143.0.7499.0 导航到随机端口的 `http://127.0.0.1` 服务；本次没有使用离线 DOM 代替 HTTP。
- 环境通过仓库已有的 `PLAYWRIGHT_CHROMIUM_EXECUTABLE` 选项使用兼容浏览器。默认浏览器下载返回了无效压缩包，因此仅在测试环境使用 `@sparticuz/chromium@143.0.4` 提供的 Chromium；它不属于应用依赖，也未加入仓库。
- 桌面 1440×1100 与手机 390×844 检查；截图环境补充了 Noto Sans CJK SC 字体，避免缺字影响中文界面检查。应用无需联网加载字体。

## 已运行的检查

| 检查 | 结果与覆盖 |
|---|---|
| 原有七组 Python 测试 | 109 项通过：基础 3、确定性 agent 10、工具调用 6、RAG 4、CoursePilot 23、课堂项目 26、机器人 37 |
| 教师独立服务 | 6 项通过：独立入口、路由白名单、本机同源限制、旧资产原样复用、旧 API 及端口校验 |
| 地图契约与存储核心 | 23 项通过：码点/字节边界、结构、版本、几何、坏历史恢复、异常写入与重复命名 |
| A01—A12 独立浏览器验收 | 12 个独立方法全部通过；每个方法使用独立浏览器上下文；A11 内部还执行原有机器人测试，不重复累计测试数量 |
| 原版浏览器 smoke | 真实 HTTP 下 14 类操作通过，包括求解、回放、分类、显式确认、导出和手机宽度检查 |
| 教师页面视觉与交互 | 标题及内容正确，保存→加载→取消删除可操作；两种宽度无横向溢出；没有页面脚本错误和控制台错误/警告 |
| 故障补丁核心验证 | 原版 23 通过 → 补丁版指定 A09 失败、其余 22 通过 → 反向补丁后 23 通过 |
| 故障补丁真实浏览器验证 | 原版 A09 通过 → 故障版 A09 的 save 子场景断言失败 → 修复后完整 A09 通过；故障阶段用 failfast 防止坏状态导致级联报错 |
| 学生起始工程隔离 | `projects/robot_playground/` 及 `CAPSTONE.md` 对基线没有差异；旧测试未删除或改写 |

## 独立审查发现并修复的边界

审查发现：契约允许的内部 LF/CR/CRLF 换行在单行文本输入框中丢失，使合法导入名称在再次导出时改变。新增 A12 反例先得到四个失败，然后修复为多行名称控件与“实际编辑前保留原始规范名称”的绑定。相同反例及完整 A01—A12 随后全部通过。

回归覆盖 `A\nB`、`A\rB`、`A\r\nB`、`A\r\nB\rC` 的真实文件下载、加载、再次保存的重名确认，以及用户后续修改名称的行为。

额外审查复现还检查了两种异步情况：旧分类响应在导入新地图后返回时不恢复旧预测；文件读取未完成时锁住地图与存档控件，失败后恢复控件且不改变地图和原始存储值。

## 重跑

```bash
node --test teacher_reference/robot_map_portfolio/tests/core.test.cjs
python -m unittest teacher_reference.robot_map_portfolio.tests.test_server -v
python -m unittest teacher_reference.robot_map_portfolio.tests.test_acceptance -v
python -m projects.robot_playground.tools.browser_smoke
python -m teacher_reference.robot_map_portfolio.tools.check_fault --browser
```

CI 工作流为 `.github/workflows/teacher-map-portfolio.yml`，分别执行核心/隔离/故障检查和真实浏览器验收。远端 CI 是否通过应以该次提交的实际 Actions 结果为准；这份记录不预先宣称远端运行成功。

## 保留的限制

只实测上述 Chromium，未声称覆盖 Firefox、Safari 或真实课堂设备；本地存储按浏览器来源区分，多标签页并发一致性不保证。整个存储容器损坏时保留原始字节并阻止写入，恢复须先备份再显式操作。V3、云同步、账号与多人服务不在本次范围内。
