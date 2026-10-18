# Pictide Web

Pictide 的唯一浏览器入口，npm 包名 `pictide-web`。产品操作见[使用指南](../README.md#使用指南)，接口见[API 索引](api.md)。

## 代码入口

本节代码路径相对于项目根目录的 `web/`。

- `index.html` → `src/main.tsx`：唯一 React 根节点，先挂载全部工作区，再各初始化一次业务控制器。
- `src/feed.tsx`：应用壳层、侧栏、漫游、生成与分类设置页。
- `src/editor.tsx`：React 管理的只读词库、生成预设与预览工作区；没有独立页面入口。
- `src/controllers/`：浏览器状态、事件和 API 调用；预设校验、共现扩展与预算连续生成由后端候选模块负责。
- `src/components/ui/`、`src/styles/theme.css`：共享 shadcn/ui 组件与设计 token；规范见 [设计规范](design-system.md)。

React 壳层与既有 DOM 控制器管理展示和草稿，控制器在页面生命周期内只初始化一次。共享控件层通过 portals 接入官方 shadcn/Radix 组件，保持单一 React 根；隐藏的表单状态接口用于衔接旧控制器，不能作为可见的原生控件。新增功能复用该层，不创建独立页面入口或按控件创建 React 根。


## 页面与状态

内部路由为 `#feed`、`#generate`、`#liked`、`#prompts` 及 `#settings/general|roam|backend|history`。任务记录位于设置的历史分区，没有独立任务栏目。

React 页面壳层与控制器共同维护草稿。图片窗口按 source 区分生成、漫游，喜欢跨来源；观看位置由后端保存。UI 不直接访问文件、SQLite 或 Python 模块，业务算法在后端。

`components/generated-results.tsx` 和 `generated-viewer.tsx` 管理生成/喜欢网格及大图；漫游控制器管理当前图、预取与自动播放；`components/page-controls.tsx` 管理常规分页。来源、数量和反馈语义以[图片接口](reference/api/images.md)为准。

全应用共用 `/api/events` EventSource；断线时保留既有轮询回退，切换栏目不创建第二条连接。候选使用 `/api/candidate/tags|presets|dataset|generate|relations`，具体方法与字段见[候选接口](reference/api/candidate.md)。

## 构建

在 `web/` 中执行 `pnpm install --frozen-lockfile`、`pnpm run typecheck`、`pnpm run build`。首次环境、验证及发布顺序统一见[开发流程](development.md)，不要在正在提供页面的目录直接清空 dist。

构建使用项目根 `dev/runtime/frontend/` 下的依赖与 `dev/cache/` 下的缓存；`web/node_modules` 指向依赖实体，`web/dist` 为发布资源。Node.js 仅用于构建，运行由 Python 宿主提供 `/static/ui/`。

## 进一步查阅

- [共享组件、主题及页面规范](design-system.md)
- [模块边界](architecture.md)
- [图片操作与快捷键](../guides/roam.md#浏览与自动播放)
- [第三方组件声明](../../web/src/THIRD_PARTY_NOTICES.md)
