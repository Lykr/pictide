# Pictide 页面设计规范

适用于图片 Feed、提示词编辑器、设置与后续新增页面。目标是简约、紧凑、层级清晰，主要空间留给图片、提示词与正在编辑的数据。

视觉基准固定为用户提供的 [shadcn Create 预设 b1VlIttI](https://ui.shadcn.com/create?preset=b1VlIttI)：Radix Luma、Neutral 配色、Inter 字体、Lucide 图标、默认圆角，菜单使用 default / subtle。预设记录在 `web/shadcn-preset.json`，生成器配置在 `web/components.json`。不再以笼统的“类似官网”作为验收标准。

## 按需查阅

| 修改内容 | 规范 |
| --- | --- |
| 配色、字体、间距与语义 token | [视觉基础](reference/design/visual.md) |
| 按钮、表单、帮助、列表和分页 | [组件规范](reference/design/components.md) |
| 页面、响应式、触屏、PWA 和语言 | [布局与交互](reference/design/layout.md) |
| 开发步骤及界面验证 | [开发与验收](reference/design/validation.md) |

## 提示词领域命名

- 标签（tag）是数据集中的完整描述，词库只读；词库包含普通描述标签与从图片 rating 转换的 general / sensitive / questionable / explicit 评级标签，不展示角色 / 作品 / 作者分类。
- 预设包含用户固定正负词与共现生成参数，存于 SQLite。提示词页依次使用「词库」「编排」「预览」，不再展示可编辑标签库或槽位。
- 「编排 → 共现扩展」提供共享 Textarea「屏蔽关键词」，每行一个，复用字段标题与 HelpTip；多行草稿保留换行，保存和预览使用去空行、去首尾空白及去重的关键词列表。帮助明确包含匹配、忽略大小写、空格／下划线等价，仅限制新抽取标签；固定正负词与停泊保持的提示词不重新过滤。
- 固定词支持自由输入并回车添加、方向键/点击选取匹配项、编辑和移除；左侧手柄支持拖拽排序及 ↑/↓ 键排序，右侧移除按钮与输入框展开按钮同列对齐；无匹配的自由文本可保存，明确说明不参与共现计算。固定词输入框右侧以共享 Badge 标记「词库词 / 自定义」，按完整文本匹配词库（空格与下划线等价），编辑后重新识别；查询期间与失败分别显示「识别中 / 未识别」，不把查询失败当作自定义词。复用已有只读相关性接口的 known 字段，不改变预设结构。连续配置只保留标签变化预算；界面复用既有 shadcn 组件与主题。

## 技术与维护入口

- 基础组件采用 [shadcn/ui](https://github.com/shadcn-ui/ui) 的源码组件，保存在 `web/src/components/ui/`；页面使用 React、TypeScript 与 Tailwind CSS，由 Vite 编译为静态资源。
- `web/src/styles/theme.css` 是颜色、字体、尺寸与基础交互样式的唯一维护入口；页面布局分别放在 `web/src/styles/feed.css` 和 `web/src/styles/editor.css`。
- Feed 与编辑器共用页面入口 `web/src/main.tsx`，内部视图组件为 `web/src/feed.tsx`、`web/src/editor.tsx`。现有 JavaScript 控制器继续处理业务状态、接口、动态列表与表单；动态 DOM 通过 `web/src/dom-primitives.ts` 复用共享组件的样式配方。这次统一包含 React 页面壳层和组件接入，尚未把全部业务控制器改写为 React。
- 可见下拉菜单、复选框、单选、分段切换、弹窗及折叠区域复用官方 `radix-luma` 源码组件和 Radix 行为，不使用原生菜单或自行开发交互。DOM 控制器通过共享状态适配层接入组件；隐藏状态接口不是可见 UI。新控件同时验证展开样式、键盘、表单提交、焦点与禁用继承。
- Node.js 仅用于开发构建。发布的静态资源由现有 aiohttp 应用提供；正常启动不需要 Node 服务、CDN、远程字体或额外前端进程。

新增基础组件先查现有源码，再按 [官方 Vite 接入说明](https://ui.shadcn.com/docs/installation/vite) 引入需要的组件。引入时使用 `radix-luma` 样式，保留预设配方，并更新 [第三方声明](../../../web/src/THIRD_PARTY_NOTICES.md)。不要手工编辑构建产物。

项目使用 pnpm，按 `package.json` 的 `packageManager` 版本和 `pnpm-lock.yaml` 安装。重新应用预设先在副本运行 `pnpm dlx shadcn@4.21.4 apply --preset b1VlIttI -y` 并核对差异；保留动态 DOM 所需的样式配方导出，不直接覆盖业务适配。新增组件可运行 `pnpm dlx shadcn@latest add <组件名>`；检查生成的别名，将共享工具导入统一为 `@/lib/utils`，避免升级生成器时引入第二套工具函数或主题。
