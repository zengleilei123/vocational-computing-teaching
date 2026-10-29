# 教师独立验收：A01–A12

本文件将 [CAPSTONE.md](../../curriculum/ai-assisted-development/CAPSTONE.md) 的编号映射到可重复执行的测试。请保留编号，便于把失败记录、修复 diff 和 [ASSESSMENT.md](../../curriculum/ai-assisted-development/ASSESSMENT.md) 的评分证据关联起来。测试面向行为结果，不以“出现了某行源码”或“函数被调用过”作为通过依据。

**验收对象是教师参考实现。** 下列命令固定启动 `teacher_reference.robot_map_portfolio.server`，并使用教师页面的控件及存储约定；它不是能自动检测任意学生工程的通用评分器。即使学生尚未实现任何存档功能，教师套件也可以通过。这里的“独立”指测试输入、预期与断言独立于被测校验器，不代表自动选中了学生代码。

验收学生作品时，使用其实际启动入口和 URL，按同一 A01—A12 契约编写或执行对应检查，并填写[学生交付证据](../../classroom/robot_portfolio/student/SUBMISSION.md)。修改选择器或测试适配层时保留原要求及反例，不要把界面命名差异判为业务功能失败，也不要静默切回教师服务。

已有独立的[学生作品验收入口](../../acceptance/robot_portfolio/README.md)：显式传入 URL 和界面适配，不自动启动教师服务；支持的普通表单／原生列表、人工复核范围及报告含义均在该页说明。以下教师套件继续验证参考实现的扩展约定，例如数组存储格式与 A07 读取前拒绝；学生运行器按 CAPSTONE 的要求检查，不把这些教师内部选择强加给学生。校准运行器时，教师配置还须与 `--allow-reference` 同时使用，报告标为参考对象。

### 校准学生验收运行器

完整仓库提供 `acceptance-adapter.json` 作为教师 UI 的显式适配，学生包不包含该配置。先在一个终端启动参考服务：

```bash
python -m teacher_reference.robot_map_portfolio.server --port 8766
```

再在另一个终端的仓库根目录运行；输出目录须是新目录：

```bash
python -m acceptance.robot_portfolio --url http://127.0.0.1:8766 --adapter teacher_reference/robot_map_portfolio/acceptance-adapter.json --source-root . --output reports/reference-calibration-001 --allow-reference
```

此报告明确标为 `reference`，只用于验证运行器与参考实现之间的适配。学生作品必须使用自己的配置、URL 和源码资产；不要把校准结果写入学生作品通过记录。原教师专用套件及故障补丁仍按下方命令运行，保持各自验证范围。

## 环境与执行

在仓库根目录使用 Python 3.10+、Node 20+，安装浏览器测试依赖：

```bash
python -m pip install "playwright==1.57.0"
python -m playwright install chromium
node --test teacher_reference/robot_map_portfolio/tests/core.test.cjs
python -m unittest discover -s teacher_reference/robot_map_portfolio/tests -p "test_*.py" -v
python -m unittest discover -s projects/robot_playground -p "test_*.py" -v
```

浏览器测试支持 `PLAYWRIGHT_CHROMIUM_EXECUTABLE`，每项测试使用隔离的浏览器上下文，向随机空闲端口上的真实回环 HTTP 服务导航。服务和浏览器均由测试负责启动、关闭。`ROBOT_OFFLINE_DOM` 不用于本套浏览器验收。

缺少 Playwright、缺少 Chromium、端口访问受环境限制、脚本异常或断言失败，都不能计为通过。保存原始输出，区分程序缺陷与环境阻塞后再处理；不要修改断言、禁用浏览器保护、跳过用例或伪造截图来取得“全绿”。

## 验收映射

每个编号对应 `tests/test_acceptance.py` 中一个独立 `test_Axx_*` 方法。核心测试补充纯逻辑边界，原项目测试验证共用后端。浏览器测试通过页面动作、文件选择、下载、存储字节与真实 HTTP 响应来判断结果。

| ID | 独立输入 / 操作 | 必须观察的结果 | 主要证据 |
|---|---|---|---|
| A01 | 合法地图命名、保存、刷新、重新加载 | 名称与网格原样恢复，持久化仅含三个允许字段；临时路线等状态不进入地图存档 | 页面、原始存储 JSON、刷新后的加载 |
| A02 | 空白名、41 码点名、40 码点名、含辅助平面字符的名称 | 无效名称拒绝；有效边界接受；按 Unicode 码点计数；拒绝时当前地图、列表及原始存储不变 | 页面错误、核心边界断言、存储快照 |
| A03 | 同名再次保存 / 导入，取消，再明确确认覆盖 | 无静默覆盖；取消保持所有状态；确认只替换对应地图，不影响其他存档 | 确认选择、两条记录前后对照 |
| A04 | 删除已有地图，先取消再确认 | 取消后记录仍在；只有明确确认后删除目标项 | 可见列表和原始存储 |
| A05 | 非法 JSON、数组、`null`、缺 / 多字段、未知或错误类型的版本 | 可读错误；拒绝非法顶层和版本；无半条存档，不破坏当前状态或原始存储 | 文件导入、错误信息、前后快照 |
| A06 | 缺 S/G、重复 S/G、不等宽、2 / 21 行或列、非法字符；3 / 20 的合法边界 | 与 `engine.parse_grid` 一致地接受或拒绝；失败不改变当前地图和存档 | 核心校验、真实页面、后端测试 |
| A07 | 16 KiB 边界和超出 1 字节的文件，使用多字节文字 | 按 UTF-8 字节计量；超限在读取和解析之前拒绝；失败状态不变 | 文件输入、读取前拒绝的行为探针、存储快照 |
| A08 | 名称含 `<b>地图</b>` 与类似 HTML 的文本 | 普通文本可见，没有新增名称派生的 HTML 元素或脚本执行 | 实际 DOM、页面与存储 |
| A09 | 存储读 / 写抛异常；历史值为非法 JSON、非数组，或数组含坏记录 / 重复名称 | 不崩溃、不伪报成功；失败的保存、覆盖、删除、导入均不改变状态或原始字节；整个容器不可解析或非数组时阻止修改；混合坏记录时展示有效项并警告，读取不改写原始值 | 故障注入、前后快照、刷新、独立故障练习 |
| A10 | 仅用键盘操作保存、选择并加载存档、取消 / 确认对话框；窄屏 | 控件有可识别标签，焦点可见，可完成主要操作；地图快捷键不抢表单按键 | 实际键盘事件、焦点与布局检查 |
| A11 | 原求解、路线回放、分类 / 样本操作；地图加载后的状态 | 旧行为仍可用；改变地图清空旧对比；分类预测后仍需明确确认才移动；不得将样本放入地图存档 | 浏览器、原项目 Python 测试、真实 HTTP |
| A12 | 导出 A，在空浏览器上下文中导入 A，再加载；名称含内部换行时再保存和导出 | 文件为严格单地图对象；精确保留契约允许的名称和网格，包括名称内部的换行字符；不带训练样本、页面状态或云同步假设 | 真下载文件、另一上下文的真实导入、名称往返 |

## 逐项重跑命令

`-k Axx` 按测试名筛选对应编号。下面每条命令都从仓库根目录执行；筛选运行只证明所执行的那一项，不能据此声称完整套件通过。

| 编号 | 命令 |
|---|---|
| A01 | `python -m unittest teacher_reference.robot_map_portfolio.tests.test_acceptance -v -k A01` |
| A02 | `python -m unittest teacher_reference.robot_map_portfolio.tests.test_acceptance -v -k A02` |
| A03 | `python -m unittest teacher_reference.robot_map_portfolio.tests.test_acceptance -v -k A03` |
| A04 | `python -m unittest teacher_reference.robot_map_portfolio.tests.test_acceptance -v -k A04` |
| A05 | `python -m unittest teacher_reference.robot_map_portfolio.tests.test_acceptance -v -k A05` |
| A06 | `python -m unittest teacher_reference.robot_map_portfolio.tests.test_acceptance -v -k A06` |
| A07 | `python -m unittest teacher_reference.robot_map_portfolio.tests.test_acceptance -v -k A07` |
| A08 | `python -m unittest teacher_reference.robot_map_portfolio.tests.test_acceptance -v -k A08` |
| A09 | `python -m unittest teacher_reference.robot_map_portfolio.tests.test_acceptance -v -k A09` |
| A10 | `python -m unittest teacher_reference.robot_map_portfolio.tests.test_acceptance -v -k A10` |
| A11 | `python -m unittest teacher_reference.robot_map_portfolio.tests.test_acceptance -v -k A11` |
| A12 | `python -m unittest teacher_reference.robot_map_portfolio.tests.test_acceptance -v -k A12` |

只运行浏览器验收的全部 12 项：

```bash
python -m unittest teacher_reference.robot_map_portfolio.tests.test_acceptance -v
```

## 独立验收怎么记录

学生先自查；同学或教师至少另选 3 个反例独立执行，优先包含一个无效文件、一个取消操作和一个存储失败。人工步骤应使用清楚记录的浏览器来源和隔离测试数据，不能靠之前已保存的记录碰巧通过。

| 记录项 | 填写内容 |
|---|---|
| 环境 | 日期、代码提交或 diff、Python / Node / 浏览器版本、运行命令、来源地址 |
| 验收编号 | Axx；若扩展要求，明确写出新增标准 |
| 操作前 | 当前地图、名称、可见存档列表、`robot-map-portfolio:v1` 原始字符串 |
| 输入与步骤 | 可复制的 JSON / 地图 / 文件大小、确认或取消的选择、故障注入方式 |
| 预期 | 与上表哪条可观察结果对应 |
| 实际 | 输出、报错、截图或录屏、是否刷新后再次检查 |
| 结论 | 通过 / 失败 / 未运行或环境阻塞；不要把未运行写成通过 |
| 修复与回归 | 小范围 diff、修复后命令和结果、与其他功能的回归检查 |

存储快照应保存原始字符串，而不只保存解析后的对象；重新序列化会隐藏字节变化。截图可以支持记录，但不能代替检查存储或断言。测试记录也不能证明课程提升了学习主动性；教学效果需要另行开展课堂评价。

## 故障补丁的独立验证

```bash
python teacher_reference/robot_map_portfolio/tools/check_fault.py
```

运行器复制教师项目到临时目录，先要求核心套件全部通过，再在副本上应用唯一故障补丁，要求**仅指定名称的 A09 回归用例失败**，随后反向应用补丁并要求核心套件全部通过。无预期失败、出现其他失败、跳过、取消、补丁不能应用或源码被意外改变都会令运行器非零退出。它验证的是测试确实能抓住这一个故障，不能代替真实浏览器的 A01–A12。

增加 `--browser` 可在临时副本中同时运行真实 HTTP 浏览器 A09 的通过—失败—通过过程。基线和恢复后执行完整 A09；故障阶段追加 `--failfast`，要求恰好出现 A09 内 `save` 子测试的断言失败，避免故障造成的虚假列表污染后续子测试准备。后续未执行子测试不计为通过。浏览器配置沿用同一环境的 Playwright 与 `PLAYWRIGHT_CHROMIUM_EXECUTABLE`。这个选项仍不能代替全部 12 项验收。

故障在参考实现中默认不启用；[学生任务](exercises/storage-write-failure/STUDENT.md) 和 [教师解析](exercises/storage-write-failure/TEACHER.md) 分开提供。只在隔离副本或工作树启用补丁，不改学生起点，不把坏实现提交到参考实现的正常分支。
