# 通用设置

沿用浏览器 → Host → Application → Store；不调用候选、推荐或任务，不新增进程或定时器。

`GET /api/settings/general` 返回完整设置，例如 `{"theme":"system","language":"system"}`；`PUT /api/settings/general` 可单独提交主题或语言，也可同时提交，未提供的字段保持原值。保存成功沿用 `general_settings` 实时事件同步其他页面。空请求和非法值返回 400，保留原设置。

- `theme`：`system`、`light` 或 `dark`，默认 `system`。
- `language`：`system`、`zh-CN` 或 `en`，默认 `system`。

设置存于所选 data 目录的 `pictide.sqlite3` / `general_settings` 单行表；主题与语言均保存用户选择，system 不再通过删除记录表示。初始化时调整原主题表结构并保留已有 light/dark 选择，新增语言为 system。保存时在同一事务中更新提供的字段，语言修改不会覆盖主题选择，主题修改也不会覆盖语言选择。

浏览器挂载页面前读取设置。主题通过共享单选分段控件提供“跟随系统 / 黑色 / 白色”，跟随系统通过 `prefers-color-scheme` 解析并订阅 change；明确选择黑色或白色时不受系统变化影响。主题和语言不保存浏览器 storage 副本。通用标签页是设置默认入口。

语言提供“跟随系统 / 简体中文 / English”，由前端解析浏览器首选语言，简体中文以外的不支持语言使用英文。跟随系统状态订阅 `languagechange`，明确选择优先；局域网设备各自解析系统语言。只翻译界面，提示词、标签原名和用户内容保留原文。具体语言匹配、切换和词典约定见 [国际化设计](i18n.md)，主题数据流见 [跟随系统主题](system-theme.md)。
