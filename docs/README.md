# 文档导航

从当前问题进入一个主题，再按页尾链接查看参数、实现或历史背景；无需先读完全部文档。

## 使用指南

| 问题 | 从这里开始 |
| --- | --- |
| 如何启动并接入生图服务？ | [安装与接入](guides/getting-started.md) |
| 如何让手机访问或添加主屏幕应用？ | [局域网与主屏幕应用](guides/access.md) |
| 提示词怎么产生，固定词和共现参数怎么用？ | [提示词与共现预设](guides/prompts.md) |
| 漫游、播放、锚点和推荐力度怎么用？ | [漫游](guides/roam.md) |
| 如何批量生成、筛选喜欢和浏览评分？ | [生成与喜欢](guides/images.md) |
| 语言主题、任务记录和清理在哪里？ | [设置与清理](guides/settings.md) |

## 架构与参考

| 主题 | 概览 | 进一步查阅 |
| --- | --- | --- |
| 模块与调用 | [架构与边界](architecture.md) | [调用和数据流](architecture/flows.md)、[推荐模块](architecture/recommendation.md) |
| HTTP 接口 | [API 索引与通用约定](api.md) | 按操作进入专题接口页 |
| 数据 | [目录与备份](data-layout.md) | [SQLite 存储参考](reference/storage.md) |

## 开发与维护

- [开发流程](development.md)：开始任务 → 准备环境 → 验证 → 集成发布。
- [页面设计规范](design-system.md)：术语、视觉、组件、布局和交互。
- [Web 代码入口](../web/README.md)：页面、控制器和共享组件。
- [设计模板](design-template.md)：提交需求设计时使用。

## 需求与功能记录

[需求目录](issues/README.md)按候选、推荐、漫游、界面和任务分类保存设计决定与验证记录。它们保留历史版本语境；当前使用看指南，接口看 API，职责看架构。

## 文档维护

入口只保留摘要和下一步；使用步骤放 `guides/`，接口与数据细节放 `reference/`，架构细节放 `architecture/`，需求与交付记录放 `issues/`。一个规则只保留一个当前说明，其他页面链接引用；专题页先说明用途，再展开细节。行为变更同步对应主题，旧决定留在需求记录并标明历史语境。
