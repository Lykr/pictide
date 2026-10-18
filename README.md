# Pictide

画流 Pictide 是一个会学习个人审美的生成式图片漫游工具。通过浏览、评价和锚点，发现、引导并收藏喜欢的画面。

漫游是体验核心，生成、提示词与设置提供控制；图片和偏好保存在本地。[了解 Pictide](docs/guides/about.md)。

## 用户指南

### 快速开始

1. 启动 ComfyUI，准备可用的文生图模型。
2. 在已安装的 Pictide 目录启动：Windows 双击 `start.cmd`；Linux / macOS 执行 `bash start.sh`（macOS 也可双击 `start.command`）。打开 http://127.0.0.1:8189 。
3. 在「设置 → 后端」填写 ComfyUI 地址、测试并保存；进入「生成」提交图片。

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
- [数据目录与备份](docs/data-layout.md)：数据保存位置、备份和恢复。
- [用户文档导航](docs/README.md#用户文档)：按使用问题查找说明。

ComfyUI 是独立的生成后端；Pictide 不作为其插件加载。当前为概念验证版本，尚无多用户账号、图像特征学习或离线网页缓存。

## 开发者文档

- [开发流程](docs/development.md)：从源码安装、构建、验证及发布；首次检出从[准备环境](docs/development.md#首次准备检出目录)开始。
- [架构与模块边界](docs/architecture.md)：模块职责、依赖和调用流程。
- [HTTP API 参考](docs/api.md)：接口索引、请求参数和响应。
- [页面设计规范](docs/design-system.md)：组件、视觉与交互约定。
- [开发者文档导航](docs/README.md#开发者文档)：代码入口、存储参考、需求记录与设计模板。
