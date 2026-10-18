# Pictide

画流 Pictide 是本地图片工作台：根据标签共现生成提示词，通过 ComfyUI 生图，并在漫游中学习喜欢与不喜欢。

## 快速开始

1. 启动 ComfyUI，准备可用的文生图模型。
2. 在已安装的 Pictide 目录双击 `start.cmd`，打开 http://127.0.0.1:8189 。
3. 在「设置 → 后端」填写 ComfyUI 地址、测试并保存；进入「生成」提交图片。

首次从源码使用需先[安装依赖和构建前端](docs/development.md#首次准备检出目录)。共现生成需准备词库，推荐学习需本地 MiniLM；完整步骤见[安装与接入](docs/guides/getting-started.md)。关闭启动窗口或按 Ctrl+C 停止应用。

## 工作台

| 栏目 | 用途 | 说明 |
| --- | --- | --- |
| 漫游 | 浏览推荐图片、评价、锚定画面元素 | [漫游指南](docs/guides/roam.md) |
| 生成 | 手动或按预设批量生图 | [生成与喜欢](docs/guides/images.md) |
| 喜欢 | 图片网格、标签筛选、偏好评分排序 | [生成与喜欢](docs/guides/images.md#喜欢标签筛选) |
| 提示词 | 查看只读词库、编辑预设、预览共现扩展 | [提示词指南](docs/guides/prompts.md) |
| 设置 | 通用、漫游、后端和任务历史 | [设置与清理](docs/guides/settings.md) |

## 按需阅读

- [文档导航](docs/README.md)：按使用、架构、参考、开发和需求记录查找。
- [局域网与主屏幕应用](docs/guides/access.md)：手机访问与 PWA。
- [数据目录与备份](docs/data-layout.md)：数据默认集中在 `data/`。
- [架构与模块边界](docs/architecture.md)：前后端职责及调用关系。
- [HTTP API](docs/api.md)：接口统一入口。
- [开发流程](docs/development.md)：安装、验证、分支和发布。

ComfyUI 是独立的生成后端；Pictide 不作为其插件加载。当前为概念验证版本，尚无多用户账号、图像特征学习或离线网页缓存。
