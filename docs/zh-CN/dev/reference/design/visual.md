# 视觉基础

[English](../../../../dev/reference/design/visual.md)

[设计规范入口](../../design-system.md) · [开发流程](../../development.md)

## 视觉基础

使用预设的浅色 Neutral 主题、Luma 胶囊按钮与柔和填充输入框。浅色与深色复用官方 token；「设置 → 通用」提供共享 ToggleGroup 单选分段控件（跟随系统 / 黑色 / 白色），默认跟随系统，立即切换并保存到应用 SQLite。页面挂载前读取已保存主题；system 通过 prefers-color-scheme 实时解析，明确选择黑白主题时保持固定，不在浏览器 storage 另存副本；所有栏目和浮层跟随根节点主题。

| 项目 | 约定 |
| --- | --- |
| 正文字号 | 14px，行高约 1.5；辅助说明 12px，业务表格可紧凑展示 |
| 标题 | 页面 20px、分区 16px、卡片/字段组 14px；以字重区分层级 |
| 字体 | Inter Variable 本地打包，中文使用系统回退；代码、ID、提示词原文使用共享等宽字体 token |
| 间距 | 4px 基础刻度：4 / 8 / 12 / 16 / 24 / 32px |
| 控件高度 | 预设默认 36px；必要的次级操作显式使用 sm（32px），不全局覆盖组件高度 |
| 圆角 | 采用官方预设的圆角尺度；按钮、输入框、文本域保留各自 Luma 配方，禁止统一强制为一个圆角 |
| 边框与阴影 | 1px 边框区分分区；浮层使用轻阴影，常规卡片避免厚阴影 |
| 动画 | 仅用于悬停、焦点和状态反馈；短时过渡，遵循减少动态效果偏好 |

颜色通过语义 token 引用，遵循 [shadcn 主题约定](https://ui.shadcn.com/docs/theming)。主题值以源码为准，本说明不复制色值。

| Token | 用途 |
| --- | --- |
| `background` / `foreground` | 页面底色与主要文字 |
| `card` / `card-foreground` | 卡片、面板 |
| `popover` / `popover-foreground` | 弹窗、浮层 |
| `primary` / `primary-foreground` | 当前区域的主要操作 |
| `secondary` / `secondary-foreground` | 次要操作和辅助容器 |
| `muted` / `muted-foreground` | 次要信息、占位、说明 |
| `accent` / `accent-foreground` | 悬停、选中背景 |
| `border` / `input` / `ring` | 分隔、表单边框、键盘焦点 |
| `destructive` | 错误与删除操作 |
| `success` / `warning` | 成功与警告状态 |

业务状态使用共享状态样式与语义颜色，并配合文字或图标。成功、等待、错误、禁用不能仅用颜色区分。页面 CSS 不新增同义色板。
