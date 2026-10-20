# 开发文档

[English](../../dev/README.md)

[项目首页](../README.md) · [用户文档](../index.md#用户文档)

开发前先了解[产品定位与体验目标](../guides/about.md)，再按任务展开技术细节。首次检出先按[开发流程](development.md#首次准备检出目录)准备环境，再按任务查阅架构、接口或界面规范。

优先实现让用户更轻松发现喜欢画面、或更自然引导探索的改动；功能取舍依据见[产品边界与体验目标](../guides/about.md#产品边界)。

## 架构与参考

| 主题 | 概览 | 进一步查阅 |
| --- | --- | --- |
| 模块与调用 | [架构与边界](architecture.md) | [调用和数据流](architecture/flows.md)、[推荐模块](architecture/recommendation.md) |
| HTTP 接口 | [API 索引与通用约定](api.md) | 按操作进入专题接口页 |
| 数据 | [目录与职责](data-layout.md) | [SQLite 存储参考](reference/storage.md)、[项目清理](cleanup.md) |

## 开发与维护

- [数据处理工具](corpus.md)：可配置处理、输入输出结构与[预构建发行词库](corpus.md#预构建词库)。
- [开发流程](development.md)：开始任务 → 准备环境 → 验证 → 集成发布。
- [分组冒烟检查](testing.md)：核心业务、界面、词库与浏览器分组，以及发版门禁。
- [GitHub Actions 发版](development.md#github-actions-发版)：准备锁定资源，推送版本标签，构建各平台便携包。
- [页面设计规范](design-system.md)：术语、视觉、组件、布局和交互。
- [Web 代码入口](web.md)：页面、控制器和共享组件。

## 文档维护

开发导航只列理解、开发和维护当前应用所需的核心文档；需求记录、变更提案和历史验证报告不列入这些导航，当前说明统一维护在对应专题文档中。

用户指南从用户需求出发，先说明能做什么、如何开始。只讲核心流程和需要理解的关键结果，次要操作留给用户在界面中探索；算法、穷举参数、边界情况与实现历史放在开发文档，避免把指南写成功能规格说明。

README 用户指南在前，开发者入口在后。入口只保留摘要和下一步；英文用户步骤放在 `docs/guides/`，英文开发文档放在 `docs/dev/`，其中接口与数据细节放 `reference/`、架构细节放 `architecture/`。一个规则只保留一个当前说明，其他页面链接引用；行为变更更新所属主题，旧决定在需求记录中保留历史语境。

用户指南及描述现状的架构、数据与 API 文档以英文为唯一维护源。日常开发只更新英文，中文译文按需或发版前集中同步，不要求每次交付同时修改两份。译文与英文有差异时，以英文为准。

中文文档统一放在 `docs/zh-CN/`，使用普通 `.md` 文件名：

| 英文原文 | 中文译文 |
| --- | --- |
| `README.md` | `docs/zh-CN/README.md` |
| `docs/README.md` | `docs/zh-CN/index.md` |
| `docs/guides/<主题>.md` | `docs/zh-CN/guides/<主题>.md` |
| `docs/dev/<主题>.md` | `docs/zh-CN/dev/<主题>.md` |
| `corpus/README.md`、`web/README.md` | `docs/zh-CN/corpus/README.md`、`docs/zh-CN/web/README.md` |

有英文原文的页面在标题下互相链接，中文导航优先指向已有中文页面；图片等共享资源保留原位置。

仅有中文的开发流程、界面规范、设计模板与需求记录也放在 `docs/zh-CN/dev/`，保留 `setup/`、`reference/`、`issues/` 等分类；英文入口标明这些资料的语言。`AGENTS.md` 作为协作入口保留在仓库根目录。发行前端的第三方声明以英文保留在 `web/src/THIRD_PARTY_NOTICES.md`，中文译文放在 `docs/zh-CN/web/src/`。
