# 通用设置（已确认）

沿用浏览器 → Host → Application → Store；不调用候选、推荐或任务，不新增进程或定时器。

`GET /api/settings/general` 读取设置，`PUT /api/settings/general` 保存；输入与输出为 `{"theme":"system"}`、`{"theme":"light"}` 或 `{"theme":"dark"}`。默认 system，非法值返回 400 且保留原值。设置存于所选 data 目录的 pictide.sqlite3 / general_settings 单行表；system 以没有显式主题记录表示，已有 light/dark 选择保留，Host 注入存储，Application 编排读取/保存并发送 general_settings 实时事件。

浏览器挂载页面前读取主题；使用共享单选分段控件提供“跟随系统 / 黑色 / 白色”；选择切换立即应用根节点 dark 类并提交，失败恢复原主题并在当前控件附近显示错误。成功设置通过既有 SSE 同步其他页面，不保存浏览器 storage 副本。通用标签页是设置默认入口，已有后端等标签页和深链接继续可用。

跟随系统通过浏览器 prefers-color-scheme 解析并订阅 change，无需轮询或保存系统颜色；明确选择黑色/白色时不受系统变化影响。设置项始终显示主题选择而非解析后的颜色。数据流和验证见 [跟随系统主题](system-theme.md)。
