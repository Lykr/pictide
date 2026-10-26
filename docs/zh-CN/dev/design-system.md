# Pictide 页面设计规范

[English](../../dev/design-system.md)

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

React、TypeScript、Tailwind 和共享 shadcn 组件使用唯一的 `web/index.html → web/src/main.tsx` 入口。React 功能组件负责布局与页面结构，功能模型负责草稿和动作；修改展示时保留语义目标、草稿值和保存行为。见[前端职责](web.md#代码入口)。

可见 Select、Checkbox、Radio、Toggle、Dialog 和 Collapsible 使用共享 Radix 组件，直接传值与回调，不通过隐藏原生控件镜像状态。保留键盘焦点、禁用状态、表单约束和校验。

Node.js 是开发构建依赖，运行时由 aiohttp 提供构建产物，字体随包，不依赖 CDN 或 Node 进程。第三方声明位于 `web/src/THIRD_PARTY_NOTICES.md`，可读[中文译文](../web/src/THIRD_PARTY_NOTICES.md)。

引入基础组件前先检查共享库和官方 shadcn Vite 说明。在隔离检出中应用预设，审查差异并复用共享组件配方；使用锁定的 pnpm 版本并提交锁文件。构建与产物发布按[开发流程](development.md)执行。
