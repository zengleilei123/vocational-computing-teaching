# 教学与工程依据

检索日期：2026-10-28。以下是课程设计参考，不表示官方背书；教学项目、数据和代码为独立示例。

1. [教育部：深化职业教育教学关键要素改革的意见（2026-02-12发布）](https://www.moe.gov.cn/srcsite/A07/zcs_zhgg/202602/t20260212_1428773.html)。参考其从典型任务拆解知识/技能、课程综合化与项目化、工作手册和评价标准的设计方向。本包不是该文件配套的官方教材。
2. [教育部：758项新版职业教育专业教学标准发布（2025-02-11）](https://www.moe.gov.cn/jyb_xwfb/gzdt_gzdt/s5987/202502/t20250211_1178746.html)。用于理解职业教育专业标准背景，不把本包建议课时说成统一标准。
3. [SQLite事务文档](https://www.sqlite.org/lang_transaction.html)。参考BEGIN IMMEDIATE与读写事务行为；本包在同一事务中检查冲突和写入，不把教学测试视为生产压力测试。
4. [scikit-learn：常见错误与数据泄漏](https://scikit-learn.org/stable/common_pitfalls.html)。先划分数据，再仅从训练部分学习特征处理参数。本包用标准库实现同样的数据隔离原则，并非使用其Pipeline。
5. [scikit-learn：Multinomial Naive Bayes](https://scikit-learn.org/stable/modules/naive_bayes.html#multinomial-naive-bayes)。参考计数、平滑与文本分类原理；朴素贝叶斯得分不能不经校准就当成可信置信度。
6. [Python unittest](https://docs.python.org/3/library/unittest.html)。参考测试组织、异常断言和自动发现命令。

这些资料支持设计方法与工程原理，不支持“本课程已提升就业率/学习效果”等尚未验证的结论。
