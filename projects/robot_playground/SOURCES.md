# 设计来源与边界（2026-10-28 核对）

以下是设计参考，不是本项目已经改善学习动机的证据，也不表示机构合作。所有关卡、代码与教学文本为本项目编写；未复制第三方游戏素材、教材或课程代码。

1. Center for Self-Determination Theory, Education：https://selfdeterminationtheory.org/topics/application-education/ 。参考自主性、胜任感和关系支持；落实为可选角色、小步成功、同伴互测，不采用强制公开排名。
2. PBLWorks, Gold Standard Project Design：https://www.pblworks.org/gold-standard/pbl-project-design 。参考挑战问题、学生选择、反馈修订、作品展示；落实为先预测、改地图/数据、解释失败和分享作品。
3. Google Research, Teachable Machine (2020)：https://research.google/pubs/teachable-machine-approachable-web-based-tool-for-exploring-machine-learning-classification/ 。参考用自己采集的数据构建交互式分类器的教学方式。本项目是自写的二值像素 k-NN，不使用其服务或模型。
4. scikit-learn, Nearest Neighbors：https://scikit-learn.org/stable/modules/neighbors.html 。用于核对近邻学习的定义、距离与投票；本项目未依赖 scikit-learn。
5. Python, http.server：https://docs.python.org/3/library/http.server.html 。该模块不适合生产部署；本例仅监听 127.0.0.1，加入输入/Host/Origin 限制也不使其成为生产服务。
6. Playwright Python：https://playwright.dev/python/docs/library 。仅用作可选开发验证，学生运行不需要安装。

最短路与机器学习是不同机制。地图能耗是模拟格子成本；k-NN票数不是概率；测试拒绝完全相同图像不证明没有数据泄漏。本项目暂无真实课堂试教或对照实验。
