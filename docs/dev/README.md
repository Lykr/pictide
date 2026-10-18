# 开发文档

[项目首页](../../README.md) · [用户文档](../README.md#用户文档)

开发前先了解[产品定位与体验目标](../guides/about.md)，再按任务展开技术细节。首次检出先按[开发流程](development.md#首次准备检出目录)准备环境，再按任务查阅架构、接口或界面规范。

## 架构与参考

| 主题 | 概览 | 进一步查阅 |
| --- | --- | --- |
| 模块与调用 | [架构与边界](architecture.md) | [调用和数据流](architecture/flows.md)、[推荐模块](architecture/recommendation.md) |
| HTTP 接口 | [API 索引与通用约定](api.md) | 按操作进入专题接口页 |
| 数据 | [目录与职责](data-layout.md) | [SQLite 存储参考](reference/storage.md) |

## 开发与维护

- [数据处理工具](corpus.md)：下载、统计导入、裁剪记录与验证入口。
- [开发流程](development.md)：开始任务 → 准备环境 → 验证 → 集成发布。
- [页面设计规范](design-system.md)：术语、视觉、组件、布局和交互。
- [Web 代码入口](web.md)：页面、控制器和共享组件。
- [设计模板](design-template.md)：提交需求设计时使用。

## 需求与功能记录

[需求目录](issues/README.md)按候选、推荐、漫游、界面和任务分类保存设计决定与验证记录。它们保留历史版本语境；当前使用看指南，接口看 API，职责看架构。

## 文档维护

README 用户指南在前，开发者入口在后，通过链接展开技术内容。入口只保留摘要和下一步；用户步骤放根目录 `docs/guides/`，开发文档集中在 `docs/dev/`，其中接口与数据细节放 `reference/`、架构细节放 `architecture/`、需求与交付记录放 `issues/`。一个规则只保留一个当前说明，其他页面链接引用；专题页先说明用途，再展开细节。行为变更同步对应主题，旧决定留在需求记录并标明历史语境。
