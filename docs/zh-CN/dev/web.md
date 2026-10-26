# Pictide Web

[English](../../dev/web.md)

Pictide 的唯一浏览器入口，npm 包名 `pictide-web`。产品操作见[使用指南](../index.md#使用指南)，接口见[API 索引](api.md)。

## 代码入口

本节代码路径相对于项目根目录的 `web/`。

- `index.html` → `src/main.tsx`：唯一 React 根节点，创建一个应用会话，通过 `shared/application-context.tsx` 提供；挂载时绑定浏览器监听与 SSE，卸载时释放。
- `src/feed.tsx`：应用壳层、导航与漫游。`src/features/` 包含受控的生成、生图 API、漫游设置和历史表单。
- `src/editor.tsx`：React 管理的只读词库、生成预设与预览工作区，没有独立页面入口。
- `src/shared/notifications.mjs`、`src/components/notifications.tsx`：共用的错误与操作结果悬浮通知层，行为见[组件规范](reference/design/components.md#悬浮通知)。
- `src/controllers/`：浏览器状态、事件和 API 调用。预设校验、共现扩展与预算内连续生成由后端 Candidate 模块负责。
- `src/controllers/app.js`：组装页面控制器，协调导航、图库、漫游与实时刷新。`backend-settings.js` 管理生图 API/工作流草稿及保存、测试动作；`prompt-settings.js` 独立管理具名 LLM 配置与 ChatGPT 登录状态；`generation-controller.js` 管理生成表单、提示词计数及结果不确定的提交。`local-generation.js` 管理本地 ComfyUI 启动草稿、明确的识别/保存动作与状态，在导航和 SSE 刷新时保留未保存编辑。`components/job-history.tsx` 从分页状态渲染任务记录。
- `src/components/ui/`、`src/styles/theme.css`：共享 shadcn/ui 组件与设计 token，见[设计规范](design-system.md)。

React 拥有页面结构与受控输入。功能服务使用小型可观察模型（`shared/model.mjs`）保存普通草稿数据，`useModel` 通过 `useSyncExternalStore` 订阅。动作接收值，返回结果或 Promise。直接使用共享 shadcn/Radix 组件，不引入隐藏代理控件、原生属性拦截或基于 DOM 的业务状态同步。

`shared/ui-state.mjs` 保存引导及共享视图使用的不可变 UI 事实，通过明确绑定的应用命令执行跨功能动作。`shared/signals.mjs` 传递主题或词库变化等生命周期失效通知。持久数据属于模型/事实，不放在瞬时事件里。DOM refs 仍用于聚焦、测量、滚动、全屏、图片动效和文件选择等浏览器能力。

前端单元检查位于 `web/tests/unit/`，真实页面检查与夹具位于 `web/tests/browser/`，临时 Python 服务为 `tests/browser_server.py`。共享入口见[针对性检查](testing.md)。

## 页面与状态

内部路由为 `#feed`、`#generate`、`#liked`、`#prompts` 和 `#settings/general|roam|backend|llm|history`。任务记录位于设置的历史分区，没有独立任务栏目。

各功能模型拥有自己的草稿，React 视图跨导航保持挂载。服务端刷新更新服务数据，不覆盖未保存编辑。图片窗口按来源区分生成、漫游，喜欢跨来源；观看位置由后端保存。UI 不直接访问文件、SQLite 或 Python 模块，业务算法在后端。

`components/generated-results.tsx` 和 `generated-viewer.tsx` 管理生成/喜欢网格及大图；漫游控制器管理当前图片、预取与自动播放；`components/page-controls.tsx` 管理常规分页。来源、数量和反馈语义以[图片接口](reference/api/images.md)为准。

图片列表失效时，在渲染选择另一张图之前保留当前漫游图片的身份与就绪状态。保留图片的 `src` 不变，浏览器不会再次触发 load；若重置就绪状态，自动播放会停滞。

全应用共用一个 `/api/events` EventSource，断线时保留既有轮询回退，切换栏目不新建第二条连接。Candidate 使用 `/api/candidate/tags|presets|dataset|generate|relations`，方法与字段见[候选接口](reference/api/candidate.md)。

## 构建

在 `web/` 中执行 `pnpm install --frozen-lockfile`、`pnpm run typecheck` 和 `pnpm run build`。首次准备、验证和发布顺序见[开发流程](development.md)，不要直接清空正在提供页面的 dist 目录。

构建使用项目根 `dev/runtime/frontend/` 下的依赖与 `dev/cache/` 下的缓存；`web/node_modules` 指向依赖实体，`web/dist` 保存发布资源。Node.js 只用于构建，运行时由 Python 宿主提供 `/static/ui/`。

编译后的 JavaScript 和 CSS 文件名带内容哈希，HTML 入口通过 `Cache-Control: no-cache` 重新验证。先发布新资源，最后更新 HTML，保留旧资源供已打开的页面读取。已打开页面在重新加载前继续运行原有代码；主屏幕应用可能需要彻底关闭再打开。

## 进一步查阅

- [共享组件、主题与页面规范](design-system.md)
- [模块边界](architecture.md)
- [图片操作与快捷键](../guides/roam.md#浏览与自动播放)
- [第三方组件声明](../web/src/THIRD_PARTY_NOTICES.md)
