# 学生作品验收：来源与实现边界

**最后核对：2026-10-30。** 以下为工具选择和验收设计依据，不代表已经取得学生学习效果。运行器沿用仓库现有 Python `unittest` 与 Playwright 1.57.0；官方网页会更新，实际使用的 API 与浏览器兼容性仍需在固定依赖上验证。

## S1：隔离每个测试的浏览器状态

[Playwright Python：Isolation](https://playwright.dev/python/docs/browser-contexts)

核对位置：`What is Test Isolation?`、`How Playwright Achieves Test Isolation`、`Multiple Contexts in a Single Test`。官方说明浏览器上下文分别持有本地存储、会话存储和 cookies；直接使用库时可以自行创建上下文。

**采用方式：** 每个 A 编号使用新上下文，A12 在另一空上下文完成作品交换。故障注入只发生在验收浏览器中，避免前一测试或学生日常浏览器的历史数据污染结果。测试库提供隔离能力，不自动证明所有测试都正确使用了它。

## S2：以语义定位适配不同学生界面

[Playwright Python：Locators](https://playwright.dev/python/docs/locators)

核对位置：`Quick Guide`、`Locate by role`、`Locate by test id`、`Locate by CSS or XPath`。官方优先推荐用户可见属性及明确的测试契约，也说明依赖 DOM 层级的长 CSS／XPath 更容易随界面变化失效。

**采用方式：** JSON 适配允许 role＋名称、label、test id 或 CSS；业务断言不绑定教师按钮 ID 或内部 JavaScript 全局变量。role 定位只提供早期可访问性反馈，不替代 A10 的真实键盘操作、视觉焦点检查或全面合规审计。

## S3：在应用初始化前制造可重复故障

[Playwright Python：BrowserContext.add_init_script](https://playwright.dev/python/docs/api/class-browsercontext#browser-context-add-init-script)

核对位置：`add_init_script` 的执行时机与注意事项。初始化脚本在文档创建后、页面脚本执行前运行；官方不保证多个 context／page 初始化脚本之间的顺序。

**采用方式：** 对坏历史的检查在页面初始化前准备；需要依赖先后顺序的设置放在同一脚本中。故障只针对本题声明的存储键，不要求填满磁盘、关闭浏览器保护或清除日常数据。探针改变的是测试环境，不应成为学生产品实现的一部分。

## S4：用页面断言判断就绪

[Playwright Python：Page.goto](https://playwright.dev/python/docs/api/class-page#page-goto)；[Navigations](https://playwright.dev/python/docs/navigations)

核对位置：`wait_until`、`Basic navigation` 与 `When is the page loaded?`。`load` 还会等待图片、iframe 等依赖资源；应用在它之前或之后都可能尚需不同的就绪判断。官方不建议以 `networkidle` 作为测试就绪依据，而应使用页面断言判断所需状态。

**采用方式：** 首次导航与刷新等待 `domcontentloaded`，再检查实际 URL、所需控件和地图；动作完成仍由具体状态断言确认。用一张故意挂起的同源图片检验必要控件可用时不必等待整页 `load`。不把“暂时没有网络请求”等同于地图已保存，也不通过固定长睡眠让测试碰运气。可配置超时用于适应机器速度，不能替代功能完成证据。

## S5：分别检查执行数量、失败与跳过

[Python 3.10：unittest](https://docs.python.org/3.10/library/unittest.html)

核对位置：`TestSuite.countTestCases`、`TestResult` 的 `testsRun`、`errors`、`failures`、`skipped` 和 `wasSuccessful`。这些字段分别描述计划执行的测试、实际执行与结果，不能只凭一个总状态代替覆盖核对。

**采用方式：** 报告保留全体 A 编号与本次所选范围，检查预期集合、实际数量、错误、失败和跳过；子集通过不代表全套通过。不同 Python 版本的空测试 CLI 提示和退出行为可能不同，本工具直接核对覆盖条件，不依赖“零测试会怎样退出”的假设。

## S6：严格 UTF-8 与替换字符不是同一个条件

[WHATWG Encoding Standard：TextDecoder](https://encoding.spec.whatwg.org/#interface-textdecoder)

核对位置：`TextDecoderOptions`、`decode` 和解码错误处理。`fatal` 默认值为 false；替换模式可用 U+FFFD 表示解码错误，严格模式在坏字节时抛错。因此，解码后的文本能通过 JSON 解析，不能证明原始字节满足 UTF-8 契约。

**采用方式：** A05 增加只破坏名称字节编码的导入反例，其他字段和地图均合法；另以合法 UTF-8 编码的 U+FFFD 名称作正对照。测试约束的是文件行为，不规定学生必须使用哪个解码 API。课堂 ZIP 保留原始坏字节，避免通过编辑器重新保存而改变反例。

## S7：将可选浏览器依赖安装到虚拟环境

[Python：venv](https://docs.python.org/3/library/venv.html)；[Python Packaging：Externally Managed Environments](https://packaging.python.org/en/latest/specifications/externally-managed-environments/)

核对位置：虚拟环境的独立包目录、直接调用环境解释器，以及由外部包管理器维护的系统 Python 的安装限制。

**采用方式：** Windows 与 macOS/Linux 分别给出 `.venv` 内解释器的完整调用方式，安装和运行使用同一解释器，不依赖激活脚本或修改 PowerShell 执行策略。基础课堂程序仍使用标准库；虚拟环境仅隔离可选验收依赖，不改变作品功能或评分。

## 本仓库自己的选择

回环 URL 限制、显式源码资产映射、学生／参考目标区分、新目录输出和不自动给分，都是针对本项目误测教师答案、证据混淆及学生起点隔离的工程决定；上述来源并未替本仓库制定评分规则。完整学生契约见 [CAPSTONE](../../curriculum/ai-assisted-development/CAPSTONE.md)。

当前适配范围为普通表单、原生存档列表及 DOM／原生确认，并保留原地图行列／地形标签语义。A07 主上下文解析探针之外的路径、A10 的视觉焦点与原生窗口键盘操作、学生个人理解仍需人工证据。测试通过证明的是所运行检查的结果，不是学习效果、原创性或整个应用安全性的认证。
