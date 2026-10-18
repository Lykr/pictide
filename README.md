# Pictide

画流 Pictide 是一个会学习个人审美的生成式图片漫游工具。通过浏览、评价和锚点，发现、引导并收藏喜欢的画面。

漫游是体验核心，生成、提示词与设置提供控制；图片和偏好保存在本地。[了解 Pictide](docs/guides/about.md)。

## 用户指南

### 快速开始（便携版本）

1. 启动 ComfyUI，准备可用的文生图模型。
2. 解压对应系统的便携包，运行启动入口：[Windows](docs/guides/setup/windows.md#便携版本) · [Linux](docs/guides/setup/linux.md#便携版本) · [macOS](docs/guides/setup/macos.md#便携版本)。程序就绪后自动打开浏览器。
3. 在「设置 → 后端」连接 ComfyUI，进入「漫游」开始浏览。

便携包随带运行环境、前端、精简词库和 MiniLM；个人数据保存在包内 `data/`。Windows 已验证真实产物，Linux/macOS 的本机构建与原生验证状态见各系统说明。

### 从源码开始

1. 启动 ComfyUI，准备可用的文生图模型。
2. 按系统完成安装与启动：[Windows](docs/guides/setup/windows.md) · [Linux](docs/guides/setup/linux.md) · [macOS](docs/guides/setup/macos.md)。打开 http://127.0.0.1:8189 。
3. 在「设置 → 后端」填写 ComfyUI 地址、测试并保存；词库与推荐模型准备完成后，进入「漫游」点击「开始漫游」，浏览、评价并切换下一张。

共现生成需要词库，推荐学习需要本地 MiniLM；准备与接入步骤见[安装与接入](docs/guides/getting-started.md)。关闭启动窗口或按 Ctrl+C 停止应用。

### 工作台

| 栏目 | 用途 | 说明 |
| --- | --- | --- |
| 漫游 | 浏览推荐图片、评价、锚定画面元素 | [漫游指南](docs/guides/roam.md) |
| 生成 | 手动或按预设批量生图 | [生成与喜欢](docs/guides/images.md) |
| 喜欢 | 图片网格、标签筛选、偏好评分排序 | [生成与喜欢](docs/guides/images.md#喜欢标签筛选) |
| 提示词 | 查看只读词库、编辑预设、预览共现扩展 | [提示词指南](docs/guides/prompts.md) |
| 设置 | 通用、漫游、后端和任务历史 | [设置与清理](docs/guides/settings.md) |

### 更多帮助

- [局域网与主屏幕应用](docs/guides/access.md)：手机访问与 PWA。
- [数据备份与恢复](docs/guides/backup.md)：数据保存位置、备份和恢复。
- [用户文档导航](docs/README.md#用户文档)：按使用问题查找说明。

ComfyUI 是独立的生成后端；Pictide 不作为其插件加载。当前为概念验证版本，尚无多用户账号、图像特征学习或离线网页缓存。

## 开发者文档

- [便携发行构建与验证](docs/dev/issues/automatic-startup.md)：目录式打包、资源初始化和平台验证。
- [开发流程](docs/dev/development.md)：从源码安装、构建、验证及发布；首次检出从[准备环境](docs/dev/development.md#首次准备检出目录)开始。
- [架构与模块边界](docs/dev/architecture.md)：模块职责、依赖和调用流程。
- [数据处理工具](docs/dev/data-processing.md)：词库下载、离线统计与处理记录。
- [HTTP API 参考](docs/dev/api.md)：接口索引、请求参数和响应。
- [页面设计规范](docs/dev/design-system.md)：组件、视觉与交互约定。
- [开发者文档导航](docs/dev/README.md)：代码入口、存储参考、需求记录与设计模板。
