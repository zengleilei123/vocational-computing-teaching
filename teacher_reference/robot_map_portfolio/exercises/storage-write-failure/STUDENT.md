# 故障任务：保存结果与刷新结果一致吗？

## 任务与交付

你接到一个失败报告：“正常保存似乎没有问题，但浏览器存储写入失败时，页面显示与刷新后的结果可能不一致。”请在隔离环境复现，记录预期和实际结果，定位原因，完成小范围修复，并证明其他地图操作仍正常。

本题只修改教师练习副本。不要修改 `projects/robot_playground/`、课程任务书或已有验收断言，不要将测试改成跳过。提交你的失败记录、最小修复 diff、验证输出和一段个人解释；使用 AI 时另附脱敏的使用记录。教师解析应在独立分析后再阅读。

## 1. 建立隔离副本

需要 Python 3.10+、Node 20+ 和 Git。运行浏览器验收时还需要 [README](../../README.md) 中的 Playwright 与 Chromium。下面两种隔离方式任选其一，均从仓库根目录开始；目标目录已存在时换一个新名称，不要覆盖旧练习。

**已经有包含教师材料的干净基线提交：使用独立工作树。**

```bash
git worktree add -b lab/map-storage-fault ../robot-map-fault-lab HEAD
cd ../robot-map-fault-lab
```

工作树来自 `HEAD`；如果教师材料尚未提交，它不会自动带上当前未提交的文件，此时使用下面的复制方式。

**需要保留当前未提交材料，或不使用工作树：复制完整项目。**

```bash
python -c "from pathlib import Path; import shutil; src = Path.cwd(); shutil.copytree(src, src.parent / 'robot-map-fault-lab', ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc', '.venv', 'node_modules'))"
cd ../robot-map-fault-lab
```

复制方式没有 Git 历史，但 `git apply` 可以在副本目录中应用本题补丁。先运行基线，保存输出：

```bash
node --test-reporter=tap teacher_reference/robot_map_portfolio/tests/core.test.cjs
```

基线全部通过后，**仅在这个隔离目录**启用题目：

```bash
git apply --check teacher_reference/robot_map_portfolio/exercises/storage-write-failure/fault.patch
git apply teacher_reference/robot_map_portfolio/exercises/storage-write-failure/fault.patch
```

补丁在正常参考实现中默认不启用。教师若已发放启用过补丁的副本，不要重复应用；先请教师说明基线及已应用的故障编号。

## 2. 用自动测试稳定复现

```bash
node --test-reporter=tap teacher_reference/robot_map_portfolio/tests/core.test.cjs
```

记录失败测试的完整名称、断言、预期和实际。这个题目预期暴露 A09 写入失败的行为问题；若出现语法错误、文件缺失或其他测试失败，先记录并排除环境或准备步骤的问题，不能把任意红色输出当成题目复现成功。

## 3. 在页面上复现用户报告

在练习副本根目录启动独立端口，避免与日常教师参考服务共用存档：

```bash
python -m teacher_reference.robot_map_portfolio.server --port 18766
```

打开 **http://127.0.0.1:18766**。使用专门的测试浏览器配置或无痕会话，只放虚构地图。原理需要你自己追踪；下面的控制台片段仅用于可重复制造“浏览器拒绝写入”的条件，不会修改文件或清理已有存档。

1. 输入并应用合法地图 `S..` / `.#.` / `..G`，命名为“操场 A”并保存。刷新后加载它，确认准备步骤成功。
2. 在开发者工具的 Local Storage 中记录 `robot-map-portfolio:v1` 的**完整原始字符串**，同时记录名称、当前地图和列表。
3. 在页面控制台执行下面的故障注入。它只影响本页对本题存储键的写入：

```javascript
window.restorePortfolioWrite = (() => {
  const original = Storage.prototype.setItem;
  Storage.prototype.setItem = function (key, value) {
    if (this === window.localStorage && key === 'robot-map-portfolio:v1') {
      throw new DOMException('练习用：写入被拒绝', 'QuotaExceededError');
    }
    return original.call(this, key, value);
  };
  return () => {
    Storage.prototype.setItem = original;
    delete window.restorePortfolioWrite;
  };
})();
```

4. 将名称改为“操场 B”并点击保存。记录页面提示、存档列表及开发者工具中的原始存储值；不要只看页面是否弹出了报错。
5. 刷新页面，检查可以加载的存档，比较刷新前与刷新后结果。刷新会移除上述临时注入；也可以在刷新前执行 `window.restorePortfolioWrite()` 恢复正常写入。
6. 用同样的方法分别检查同名覆盖和确认删除。每轮先恢复正常写入、准备已知记录并快照，再注入失败；不要让上一轮状态混入下一轮。

按契约，写入失败时应该有可读错误，操作前的当前地图、存档列表和原始存储字符串应保持不变，不能显示保存或删除成功。请自己填写实际结果，不要把这段预期当作运行证据。

## 4. 失败记录模板

| 观察项 | 操作前 | 预期 | 实际结果与证据 |
|---|---|---|---|
| 环境与版本 | 提交 / diff、Python、Node、浏览器、来源端口 | 可在另一台设备按步骤复现 | |
| 操作 | 新建保存 / 同名覆盖 / 确认删除 | 明确记录所选动作及确认选择 | |
| 当前地图与名称 | 完整名称与三行网格 | 失败不意外切换地图 | |
| 存档列表 | 所有条目 | 失败不新增、替换或删除 | |
| 页面消息 | 原消息 | 明确说明写入未完成 | |
| 原始存储字符串 | 原样复制，不重新序列化 | 与操作前字节一致 | |
| 刷新后加载 | 可加载的条目 | 与真正保存的数据一致 | |
| 自动测试 | 命令及完整测试名 | 对应 A09 报出行为错误 | |

写出至少一个可以被验证或推翻的原因假设，再用断点、变量观察或小范围日志收集证据。避免把“浏览器坏了”“AI 写错了”当作定位结论。

## 5. 分层提示

按需逐层使用，并在记录中说明用了哪一层。

**提示 1：先分清状态。** 页面当前显示的地图、存档列表、浏览器已写入的字符串是否来自同一份数据？刷新后哪些值会重新构建？

**提示 2：沿着一次操作追踪。** 从保存按钮出发，列出输入校验、重名处理、实际持久化、更新页面和显示消息的先后顺序。在哪一步可以确认数据真正写入？

**提示 3：比较两条执行路径。** 分别画出写入成功与写入异常时的返回或错误传播路径。调用方依据什么区分两种结果？用自动测试的失败断言核对你的判断。

这些提示不指定修复行。你的修复应恢复契约，且能解释为什么其他操作也受到保护。

## 6. 修复后验证

先重跑核心套件，要求所有实际执行的测试都通过：

```bash
node --test-reporter=tap teacher_reference/robot_map_portfolio/tests/core.test.cjs
```

再用真实浏览器检查 A09，并回归完整地图验收和原机器人功能：

```bash
python -m unittest teacher_reference.robot_map_portfolio.tests.test_acceptance -v -k A09
python -m unittest teacher_reference.robot_map_portfolio.tests.test_acceptance -v
python -m unittest discover -s projects/robot_playground -p "test_*.py" -v
```

重新进行第 3 节的页面操作，补齐修复后证据。环境暂时不能运行浏览器时，如实写“浏览器验收未运行 / 环境阻塞”，不能用核心测试代替完整端到端结论。

最终解释需回答：失败如何跨层到达页面？为什么正常保存仍可用？原始存储为什么没有变化？回退源码是否会回退已经保存的地图？清理测试数据前先备份，只能由你明确删除本题的准确存储键，不能清空浏览器的所有数据。
