# <img src="../../web/public/icons/pictide.svg" alt="" width="36" height="36" /> Pictide

[English](../../README.md)

**随你漫游，新的画面徐徐展开。**

![Pictide roaming demo](../assets/roam.gif)

新的画面沿途生成，由你的反馈与锚点引导方向。

画流 Pictide 是一款在本地运行、通过反馈逐渐贴近个人喜好的生成式图片漫游应用。无需手动编写提示词，也能轻松生成搭配自然的画面。不必先有明确的创作目标，从浏览开始，表达喜好，随时引导后续画面的方向。图片和偏好均保存在本地。[了解 Pictide](guides/about.md)。

## 用户指南

### 快速开始

1. 从 [GitHub Releases](https://github.com/Lykr/pictide/releases) 下载并解压适合系统的便携包。
2. 启动 Pictide，首次运行等待词库和推荐资源下载完成，再跟随应用内引导开始漫游。

Windows 可在首次启动时安装 ComfyUI 和推荐模型；macOS、Linux 用户需提前准备好 ComfyUI 或其他生图 API。

启动帮助：[Windows](guides/setup/windows.md#便携版本) · [Linux](guides/setup/linux.md#便携版本) · [macOS](guides/setup/macos.md#便携版本)。

服务器或 NAS 可使用 [Docker Compose 部署](guides/setup/docker.md)：下载发布页的 `compose.yaml`，执行 `docker compose up -d`。预构建镜像支持 Linux amd64 和 arm64。

### 功能概览

| 栏目 | 用途 | 说明 |
| --- | --- | --- |
| 漫游 | 边看边发现喜欢的画面，引导后续方向 | [漫游指南](guides/roam.md) |
| 生成 | 把明确的想法变成图片 | [生成](guides/generate.md) |
| 喜欢 | 回看收藏，找到想看的画面 | [喜欢](guides/liked.md) |
| 提示词 | 保存常用风格，调整画面组合 | [提示词指南](guides/prompts.md) |
| 设置 | 连接生图服务，管理使用偏好与数据 | [设置与清理](guides/settings.md) |

### 更多帮助

- [局域网与主屏幕应用](guides/access.md)：手机访问与 PWA。
- [数据备份与恢复](guides/backup.md)：数据保存位置、备份和恢复。
- [用户文档导航](index.md#用户文档)：按使用问题查找说明。

Pictide 目前处于概念验证阶段，接入与平台支持情况见[安装指南](guides/getting-started.md)。

## 开发者文档

- [开发流程](dev/development.md)：从源码安装、构建、验证及发布。
- [架构与模块边界](dev/architecture.md)：模块职责、依赖和调用流程。
- [数据处理工具](dev/corpus.md)：词库处理与发行数据准备。
- [HTTP API 参考](dev/api.md)：接口索引、请求参数和响应。
- [页面设计规范](dev/design-system.md)：组件、视觉与交互约定。
- [开发者文档导航](dev/README.md)：数据目录、代码入口与专题参考。

## 许可证

Pictide 自有源码和文档采用 [Apache License 2.0](../../LICENSE)，项目署名见 [NOTICE](../../NOTICE)。第三方组件、字体、模型权重、数据集和生成图片保留各自适用的许可与权利；项目许可证不为这些材料授予额外权利。
