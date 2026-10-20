# 分组冒烟检查

[English](../../dev/testing.md)

按本次改动选择一小组检查，统一入口不会自动发现或运行全量测试：

```shell
python scripts/check.py core
python scripts/check.py ui
python scripts/check.py corpus
python scripts/check.py browser
```

在仓库根目录执行，或使用 `scripts/check.py` 的绝对路径。添加 `--list` 可只查看清单；检查失败返回非零退出码。

建议使用 Python 3.12，与发版 CI 保持一致。

| 分组 | 检查内容 | 环境要求 |
| --- | --- | --- |
| `core`（默认） | 6 项 HTTP/存储冒烟：预设到漫游、阻塞队列恢复、数据库迁移、反馈撤回、OpenAI 与 Gemini 协议请求 | 应用 Python 依赖 |
| `ui` | 6 个 Node 测试文件：引导状态与定位、按钮反馈、通知、主题/语言竞态、API 密钥编辑 | Node.js |
| `corpus` | 3 项离线冒烟：图片过滤、过期/损坏预构建资源拒绝、两版词库导出 | 安装了 `corpus/requirements.txt` 的 Python 环境 |
| `browser` | 3 条真实页面流程：通知不挤动布局、弹窗内重试、移动端引导与锚点保存 | 应用 Python 依赖、前端依赖、测试前端产物与浏览器 |

前端快捷入口为 `pnpm --dir web test` 和 `pnpm --dir web run test:browser`。统一 Python 入口会把当前解释器传给浏览器测试服务；前端快捷入口使用 `PATH` 中的 `python`。

## 准备浏览器检查

按[开发环境说明](development.md#首次准备检出目录)准备后，构建独立产物并安装 Chromium：

```shell
pnpm --dir web run typecheck
pnpm --dir web run build --out-dir ../dev/verification/browser/dist
pnpm --dir web exec playwright install chromium
python scripts/check.py browser
```

本机已有 Edge 时，也可使用 `python scripts/check.py browser --channel msedge`。Linux CI 在 runner 上通过 `playwright install --with-deps chromium` 准备系统依赖。

每个浏览器测试 worker 使用可用端口启动本机 HTTP 服务，数据临时保存在 `dev/verification/browser/`，结束后关闭服务并删除临时数据。生图使用模拟后端、小型中性词库和确定性的测试编码器，不下载模型，不提交 GPU 或付费 API 请求。通过这些检查代表应用交互正常，真实模型兼容性和出图质量需另行验证。

失败时，截图、trace 与 JSON 报告保留在 `dev/verification/browser/`。使用 `pnpm --dir web exec playwright show-trace TRACE_PATH` 查看 trace。浏览器测试不自动重试。

## 发版检查

标签触发的发行流程在四个平台构建前统一运行一次 `core`、`ui` 与 `browser`。离线 `corpus` 组在数据处理变更时单独执行。各平台继续保留成品解压启动冒烟。

日常分支推送不触发 Actions。本次调整从后续版本标签开始生效，不重新构建 v0.5.0。

分组清单维护在 `scripts/check.py` 与 `web/scripts/test.mjs`，优先覆盖用户行为和数据保留约定；更细的改动按需运行单个已有测试。Playwright 的环境和浏览器选项见[官方文档](https://playwright.dev/docs/browsers)。
