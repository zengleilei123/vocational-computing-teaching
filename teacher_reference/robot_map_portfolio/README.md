# 教师参考：我的地图作品集（V1 / V2）

这是 [综合作业](../../curriculum/ai-assisted-development/CAPSTONE.md) 的教师参考实现与独立验收材料。它在原机器人挑战场上增加地图命名、本地存档、加载、确认覆盖、确认删除，以及单张地图的 JSON 导入和导出。学生起点仍是 `projects/robot_playground/`；原来的学生源码、任务书和课程验收要求不因本目录的加入而改变。

`teacher_reference/` 是教学材料的组织边界，不是访问控制。公开 GitHub 仓库中的参考答案和教师说明都可以被阅读；需要延后发放答案时，应由教师另行安排材料发放。不要声称目录名称能保密。

## 启动与体验

从仓库根目录，用 Python 3.10+ 启动：

```bash
python -m teacher_reference.robot_map_portfolio.server --port 8766
```

打开 **http://127.0.0.1:8766**，用 Ctrl+C 退出。教师服务默认使用 8766，原学生服务仍使用 8765；两者只监听本机回环地址。不要双击 HTML，也不要将此教学服务直接部署到公网。

建议按这个顺序体验：

1. 编辑一张合法地图并应用，输入作品名称后保存。
2. 刷新，选择存档并加载，检查名称和网格。
3. 修改同名地图并再次保存，分别试取消与明确确认覆盖；再试取消删除。
4. 导出一张地图，在独立浏览器配置或无痕窗口中打开同一服务并导入。
5. 导入一个坏文件，确认当前地图、已有存档和原始存储字符串都没有改变。

运行时只使用当前浏览器与本机 HTTP 服务，不需要云账号、API Key、外部 CDN 或联网 AI。Python 服务处理原有的地图求解、回放和符号分类请求；地图存档写在浏览器中，服务端不维护数据库。安装浏览器测试工具可能需要联网，完成安装后应用可以离线使用。

## 持久化范围与数据契约

唯一使用的存储键是 **`robot-map-portfolio:v1`**，其值是 JSON **数组**。数组的每一项以及交换文件中的单个地图都严格遵守下面的对象契约：

```json
{
  "version": 1,
  "name": "我的配送地图",
  "grid": ["S..", ".#.", "..G"]
}
```

| 字段或边界 | 规则 |
|---|---|
| 顶层 | 单张地图必须是对象，字段恰好为 `version`、`name`、`grid`；缺字段、多字段、顶层数组或 `null` 均拒绝 |
| `version` | JSON 数值的整数 1；拒绝 `true`、`"1"` 和其他版本 |
| `name` | 字符串，去除首尾空白后为 1–40 个 Unicode 码点；按码点计数，不能将 JavaScript UTF-16 代码单元数当作码点数 |
| `grid` | 3–20 行字符串，每行等宽且为 3–20 列；只允许 `# . S G 2 3 4 5 6 7 8 9`，恰好一个 `S` 和一个 `G`；与原 `engine.parse_grid` 的规则一致 |
| 文件 | UTF-8 JSON，最多 16 KiB（16,384 字节）；先检查文件字节数再读取、解码和解析；这与原 HTTP 接口的 64 KiB 请求上限不同 |
| 存储容器 | 正常写入为一个有效且名称不重复的地图对象数组；历史数据的损坏恢复策略见下文；不能把旧版整个页面或整个实验对象当成地图导入 |
| 重名 | 名称修剪后比较；同名保存或导入必须明确选择取消、改名或确认覆盖；确认覆盖只更改对应记录 |
| 删除 | 用户明确确认后才删除；取消不改变存档 |

仅 `version/name/grid` 进入这个存档。机器人路线、算法对比、分类训练与测试样本、预测结果和页面临时状态不进入存档。已有“导出我的实验”是另一种实验证据格式，不能当成这里的地图交换文件。

所有失败的修改，包括校验拒绝、取消操作、文件读取错误和存储写入异常，都必须保留操作前的当前地图、已有存档及该键的原始存储字符串。页面只能在真实写入完成后报告保存或删除成功。名称通过文本节点显示；`<b>地图</b>` 也是普通文字。

## 浏览器存储的边界

浏览器存档按来源区分，来源包含协议、主机和端口。因此 `http://127.0.0.1:8766`、`http://localhost:8766`、`http://127.0.0.1:8765` 不是同一份存档。更换浏览器、配置文件、端口或使用无痕会话也可能看到不同的存档。交换文件靠用户主动导出和导入；没有自动云同步。

本版面向单人、单标签页使用，不保证多个标签页同时修改时的一致性。浏览器清理站点数据或无痕会话结束可能移除本地数据，请主动导出需要保留的地图。本地存储不适合保存密钥或真实个人信息。

### 存储损坏时怎样处理

当整个存储字符串不是合法 JSON，或解析结果不是数组时，本参考实现**阻止存档修改并显示警告**，保留原始字符串，不用空数组覆盖。若容器是数组、其中仅部分记录无效或名称重复，则显示有效记录并警告：忽略无效记录，同名保留第一条有效记录，读取过程不改写原始字符串。之后一次用户明确发起且写入成功的保存或删除，会把恢复后的有效记录连同本次修改重新写入；届时被忽略的条目不会保留。因此，要研究或恢复坏条目，必须在下一次成功修改前备份原始值。

单纯刷新或回退 Git 代码不会修复浏览器里的坏数据。

若要检查或恢复，先确认浏览器地址正是出问题的来源，再打开开发者工具的 Application / Storage → Local Storage，选择该来源：

1. 找到准确的键 `robot-map-portfolio:v1`，将它的完整原始值复制到本地文本文件；这份备份可能是非法 JSON，不要先格式化或“修正”它。
2. 记录来源地址、时间和错误提示。需要挽救地图时，在副本上检查和修复，保留原始备份。
3. 只有明确决定放弃当前容器、且已经保存备份后，才在开发者工具中删除**这一项**并刷新。也可以在该页面控制台中明确执行 `localStorage.removeItem('robot-map-portfolio:v1')`。
4. 重新导入已经校验的单张地图。不要用 `localStorage.clear()` 清空同一来源的全部数据，也不要将删数据当作修复代码的证据。

如果浏览器禁止存储访问，先在允许本地存储的独立测试配置中重试；删除键不能解除浏览器的权限限制。程序不会替用户自动执行上述恢复删除。

## 自动验证

从仓库根目录运行。应用本身仅使用 Python 标准库与原生浏览器 API；下面的 Node 测试使用 Node 内置测试器，不需要 npm 安装。

```bash
python -m unittest discover -s projects/robot_playground -p "test_*.py" -v
node --check projects/robot_playground/static/app.js
node --test teacher_reference/robot_map_portfolio/tests/core.test.cjs
```

浏览器验收需要 Node 20+（核心测试）、Python 3.10+，以及固定的 Python Playwright 版本与 Chromium：

```bash
python -m pip install "playwright==1.57.0"
python -m playwright install chromium
python -m unittest discover -s teacher_reference/robot_map_portfolio/tests -p "test_*.py" -v
```

已经有兼容 Chromium 的环境可以设置 `PLAYWRIGHT_CHROMIUM_EXECUTABLE` 指向其可执行文件。验收代码会启动随机空闲端口的真实本机 HTTP 服务，并由真实浏览器导航；无需先启动 8766 服务。缺少依赖、浏览器或浏览器无法连接本机服务时，应记录为环境阻塞或失败，不应改成跳过后声称全部通过。

只重跑一个验收点，例如 A09：

```bash
python -m unittest teacher_reference.robot_map_portfolio.tests.test_acceptance -v -k A09
```

完整的 A01–A12 映射、各项命令、人工检查与证据要求见 [ACCEPTANCE.md](ACCEPTANCE.md)。原项目的离线 DOM 模式不等于这里的真实 HTTP 浏览器验收，本套验收不靠它替代浏览器导航。

## 故障练习与材料索引

| 材料 | 用途 |
|---|---|
| [ACCEPTANCE.md](ACCEPTANCE.md) | 独立验收、逐项命令、记录方式与覆盖边界 |
| [VERIFICATION.md](VERIFICATION.md) | 实际测试环境、运行结果、审查修复与未覆盖范围 |
| [exercises/storage-write-failure/STUDENT.md](exercises/storage-write-failure/STUDENT.md) | 学生故障任务、复现、分层提示、提交记录 |
| [exercises/storage-write-failure/TEACHER.md](exercises/storage-write-failure/TEACHER.md) | 精确根因、修复、评分检查和数据回退说明 |
| `exercises/storage-write-failure/fault.patch` | 仅在隔离副本中手动启用的故障补丁；默认不生效 |
| `tools/check_fault.py` | 在临时副本中验证“基线通过 → 指定回归失败 → 反向补丁后通过” |

教师发布故障题前运行：

```bash
python teacher_reference/robot_map_portfolio/tools/check_fault.py
```

完成浏览器依赖安装后，可追加真实 HTTP 浏览器 A09 的相同三阶段验证：

```bash
python teacher_reference/robot_map_portfolio/tools/check_fault.py --browser
```

该命令不修改当前参考实现，也不修改学生源码。测试通过只表示这些程序行为满足测试断言，不构成课堂效果、学习主动性或教学因果效果的证据；课堂效果仍需按照原课程的评价设计收集实际材料。

故障补丁工具还需要 Git，只调用本机的 `git apply`，不访问远端仓库。正常启动与核心测试不需要 Git。
