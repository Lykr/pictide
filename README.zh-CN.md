# <img src="web/public/icons/pictide.svg" alt="" width="36" height="36" /> Pictide

[English](README.md)

**随你漫游，画面世界徐徐展开。**

![Pictide roaming demo](docs/assets/roam.gif)

新的画面沿途生成，由你的反馈与锚点引导方向。

画流 Pictide 是一款在本地运行、通过反馈逐渐贴近个人喜好的生成式图片漫游应用。无需手动编写提示词，也不必先有明确的创作目标——从浏览图片开始，表达喜好，随时引导后续画面的方向。图片和偏好保存在本地。[了解 Pictide](docs/guides/about.zh-CN.md)。

## 用户指南

### 快速开始（便携版本）

1. 准备 ComfyUI 与文生图模型，或 OpenAI Images / Gemini 的 API Key 和图片输出模型。
2. 解压对应系统的便携包，运行启动入口：[Windows](docs/guides/setup/windows.zh-CN.md#便携版本) · [Linux](docs/guides/setup/linux.zh-CN.md#便携版本) · [macOS](docs/guides/setup/macos.zh-CN.md#便携版本)。程序就绪后自动打开浏览器。
3. 按[接入指南](docs/guides/getting-started.zh-CN.md)在「设置 → 生图 API」连接生图服务，进入「漫游」开始浏览。云端漫游默认关闭自动预取，请使用负向提示词为空的预设。

便携包随带运行环境、前端和 `filtered` 统计词库；下载与切换 `all-ratings` 见[词库版本](docs/guides/vocabularies.zh-CN.md)。首次启动先下载并校验 MiniLM，完成后才打开应用，进度显示在启动窗口。后续复用本地模型。离线准备与下载重试见[推荐模型启动准备](docs/guides/getting-started.zh-CN.md#推荐模型启动准备)。个人数据保存在包内 `data/`。Windows 已验证真实产物，Linux/macOS 的本机构建与原生验证状态见各系统说明。

### 从源码开始

1. 准备 ComfyUI 与文生图模型，或 OpenAI Images / Gemini 的 API Key 和图片输出模型。
2. 按系统完成安装与启动：[Windows](docs/guides/setup/windows.zh-CN.md) · [Linux](docs/guides/setup/linux.zh-CN.md) · [macOS](docs/guides/setup/macos.zh-CN.md)。打开 http://127.0.0.1:8189 。
3. 在「设置 → 生图 API」配置生图服务、测试并保存；词库与推荐模型准备完成后，进入「漫游」点击「开始漫游」，浏览、评价并切换下一张。

共现生成需要词库，推荐学习需要本地 MiniLM；准备与接入步骤见[安装与接入](docs/guides/getting-started.zh-CN.md)。关闭启动窗口或按 Ctrl+C 停止应用。

### 工作台

| 栏目 | 用途 | 说明 |
| --- | --- | --- |
| 漫游 | 浏览推荐图片、评价、锚定画面元素 | [漫游指南](docs/guides/roam.zh-CN.md) |
| 生成 | 手动或按预设批量生图 | [生成与喜欢](docs/guides/images.zh-CN.md) |
| 喜欢 | 图片网格、标签筛选、偏好评分排序 | [生成与喜欢](docs/guides/images.zh-CN.md#喜欢标签筛选) |
| 提示词 | 查看只读词库、编辑预设、预览共现扩展 | [提示词指南](docs/guides/prompts.zh-CN.md) |
| 设置 | 通用、漫游、生图 API和任务历史 | [设置与清理](docs/guides/settings.zh-CN.md) |

### 更多帮助

- [局域网与主屏幕应用](docs/guides/access.zh-CN.md)：手机访问与 PWA。
- [数据备份与恢复](docs/guides/backup.zh-CN.md)：数据保存位置、备份和恢复。
- [用户文档导航](docs/README.zh-CN.md#用户文档)：按使用问题查找说明。

Pictide 作为独立应用连接 ComfyUI、OpenAI Images 与 Gemini 原生生图。云端接入已用协议模拟服务验证，收费服务的真实出图尚未验证。本功能已包含在当前源码中，已有便携包需要更新版本。当前为概念验证版本，尚无多用户账号、图像特征学习或离线网页缓存。

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
