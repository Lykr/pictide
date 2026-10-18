# HTTP API 参考

Pictide 当前已实现的 HTTP API 统一入口。先阅读通用约定，再按操作进入对应主题；字段和返回值只在主题页维护。

## 按操作查找

| 要做什么 | 接口详情 |
| --- | --- |
| 初始化页面、订阅状态变化 | [初始化与实时事件](reference/api/events.md) |
| 修改语言、主题、清理期限 | [通用与历史设置](reference/api/settings.md) |
| 配置漫游、保存观看位置、补足预取 | [漫游](reference/api/roam.md) |
| 接入 ComfyUI、检查连接、管理工作流 | [生图后端与工作流](reference/api/backends.md) |
| 创建、分页查看和取消任务 | [生成任务](reference/api/jobs.md) |
| 查询图片、反馈、清理、偏好评分与排序 | [图片、反馈与评分](reference/api/images.md) |
| 查看、导出和重置偏好 | [用户偏好](reference/api/preferences.md) |
| 搜索词库、保存预设、生成和预览相关性 | [候选词库与预设](reference/api/candidate.md) |

## 通用约定

- 默认地址：`http://127.0.0.1:8189`；以下路径均相对此地址。局域网启动方式见[项目 README](../../docs/guides/access.md#局域网访问)。当前没有账号认证，数据和偏好共用本地用户 `local`。
- 除图片、下载和 SSE 外，响应为 JSON。成功通常返回 `200`；提交任务为 `202`，单独新建工作流为 `201`。
- 词库上传 `POST /api/candidate/library` 使用 multipart/form-data；其余非 GET/HEAD 的 `/api/` 请求，包括 DELETE，必须携带 `Content-Type: application/json`；无参数时发送 `{}`。请求体须为 JSON 对象，不允许重复字段或 NaN/Infinity。通常上限 8 MiB，候选请求 1,100,000 字节，重置偏好请求 2,048 字节。
- 修改请求的 `Origin` 若存在须与访问地址同源，`Sec-Fetch-Site: cross-site` 被拒绝；Host 限制为本机地址或局域网入口允许的本机内网 IP。未开放通用跨域调用。
- API 响应使用 `Cache-Control: no-store`。这不表示图片偏好评分每次重新计算，评分另有持久缓存。
- 时间通常为 ISO 8601 UTC 字符串；观看位置 `viewed_at` 是毫秒整数。安全整数上限为 `9007199254740991`。
- `{id}` 代表对应资源 ID。列表中的 ID 应作为不透明标识使用，调用方不依赖其生成规则。

### 错误

业务错误通常返回 `{"error":"说明"}`；候选接口的校验错误另有 `"kind":"validation"`。HTTP 层拒绝可能返回纯文本，调用方应先检查状态码与 Content-Type。

| 状态 | 含义 |
| --- | --- |
| 400 | 参数、JSON 或生图后端校验错误 |
| 403 | Host 或跨站修改限制 |
| 404 | 路由或资源不存在 |
| 409 | 修订号、重复请求内容或名称冲突 |
| 410 | 资源已清理且不再可访问 |
| 413 / 415 | 请求过大 / Content-Type 不符合接口要求 |
| 502 | 获取图片时上游后端失败 |

部分接口通过 `200` 返回业务不可用状态，例如连接检查 `ok:false`、漫游 `paused:true`、评分 `status:"unavailable"`，不能仅靠 HTTP 状态判断业务成功。

## 调用示例

以下示例请求读取词库及预览提示词，不提交图片生成任务：

```powershell
Invoke-RestMethod 'http://127.0.0.1:8189/api/candidate/tags?query=black_hair&page=1&page_size=15'

$preview = '{"preset_id":"default","mode":"fixed_seed","seed":42}'
Invoke-RestMethod 'http://127.0.0.1:8189/api/candidate/generate' -Method Post `
  -ContentType 'application/json' -Body $preview
```

浏览器建立事件连接：

```javascript
const events = new EventSource('/api/events');
events.addEventListener('change', (event) => {
  const { topic, revision } = JSON.parse(event.data);
  // 根据 topic 重读相关资源；revision 用于识别本次通知。
});
```

## 实现与维护入口

- [HTTP 路由、请求解析及状态码](../../backend/host.py)
- [应用编排与 HTTP 返回对象](../../backend/application.py)
- [候选参数与结果](../../backend/candidate/service.py)、[种子和序列参数](../../backend/candidate/rounds.py)
- [推荐模块内部契约](../../backend/contracts/recommendation.py)
- [任务存储与分页模型](../../backend/store/sqlite.py)

本文是 HTTP 参考，不将模块内部的评分、学习等 Python 方法作为额外公开 HTTP 接口；当前没有 OpenAPI / Swagger 页面。新增、删除或调整路由时同步维护对应章节和导航。
