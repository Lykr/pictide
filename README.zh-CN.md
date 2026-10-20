# <img src="web/public/icons/pictide.svg" alt="" width="36" height="36" /> Pictide

[English](README.md)

**随你漫游，新的画面徐徐展开。**

![Pictide roaming demo](docs/assets/roam.gif)

新的画面沿途生成，由你的反馈与锚点引导方向。

画流 Pictide 是一款在本地运行、通过反馈逐渐贴近个人喜好的生成式图片漫游应用。无需手动编写提示词，也能轻松生成搭配自然的画面。不必先有明确的创作目标，从浏览开始，表达喜好，随时引导后续画面的方向。图片和偏好均保存在本地。[了解 Pictide](docs/guides/about.zh-CN.md)。

## 用户指南

> [!IMPORTANT]
> Pictide 目前的体验依赖于生图模型对 Danbooru 标签提示词的支持程度。自然语言提示词支持正在计划中。

### 快速开始

1. 提前准备好 ComfyUI 或其他生图 API；也可通过 [Windows 本地准备引导](docs/guides/setup/windows.zh-CN.md#便携版本)下载 ComfyUI 与推荐模型。
2. 从 [GitHub Releases](https://github.com/Lykr/pictide/releases) 下载并解压适合系统的便携包。
3. 按系统选择启动方式：[Windows](docs/guides/setup/windows.zh-CN.md#便携版本) · [Linux](docs/guides/setup/linux.zh-CN.md#便携版本) · [macOS](docs/guides/setup/macos.zh-CN.md#便携版本)，然后跟随应用内引导快速上手。

发行包随带默认词库。Windows 和 Linux 的个人数据保存在程序旁的 `data/`，macOS 保存在用户目录。查看数据位置、从源码运行或更换词库，见[用户文档](docs/README.zh-CN.md)。

### 功能概览

| 栏目 | 用途 | 说明 |
| --- | --- | --- |
| 漫游 | 边看边发现喜欢的画面，引导后续方向 | [漫游指南](docs/guides/roam.zh-CN.md) |
| 生成 | 把明确的想法变成图片 | [生成](docs/guides/generate.zh-CN.md) |
| 喜欢 | 回看收藏，找到想看的画面 | [喜欢](docs/guides/liked.zh-CN.md) |
| 提示词 | 保存常用风格，调整画面组合 | [提示词指南](docs/guides/prompts.zh-CN.md) |
| 设置 | 连接生图服务，管理使用偏好与数据 | [设置与清理](docs/guides/settings.zh-CN.md) |

### 更多帮助

- [局域网与主屏幕应用](docs/guides/access.zh-CN.md)：手机访问与 PWA。
- [数据备份与恢复](docs/guides/backup.zh-CN.md)：数据保存位置、备份和恢复。
- [用户文档导航](docs/README.zh-CN.md#用户文档)：按使用问题查找说明。

Pictide 目前处于概念验证阶段，接入与平台支持情况见[安装指南](docs/guides/getting-started.zh-CN.md)。

## 开发者文档

- [便携发行构建与验证](docs/dev/issues/automatic-startup.md)：目录式打包、资源初始化和平台验证。
- [开发流程](docs/dev/development.md)：从源码安装、构建、验证及发布；首次检出从[准备环境](docs/dev/development.md#首次准备检出目录)开始。
- [架构与模块边界](docs/dev/architecture.zh-CN.md)：模块职责、依赖和调用流程。
- [数据处理工具](docs/dev/corpus.md)：词库下载、离线统计与处理记录。
- [HTTP API 参考](docs/dev/api.zh-CN.md)：接口索引、请求参数和响应。
- [页面设计规范](docs/dev/design-system.md)：组件、视觉与交互约定。
- [开发者文档导航](docs/dev/README.zh-CN.md)：代码入口、存储参考、需求记录与设计模板。

## 许可证

Pictide 自有源码和文档采用 [Apache License 2.0](LICENSE)，项目署名见 [NOTICE](NOTICE)。第三方组件、字体、模型权重、数据集和生成图片保留各自适用的许可与权利；项目许可证不为这些材料授予额外权利。
