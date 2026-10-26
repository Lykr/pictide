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
| `core`（默认） | 12 项冒烟：本地 ComfyUI 生命周期、macOS 更新重启模式、预设到漫游、队列恢复、数据库迁移、可撤回反馈、OpenAI/Gemini 协议、自然语言停泊复用与明确重试、具名 LLM 引用、OAuth 回调校验 | 应用 Python 依赖 |
| `ui` | 8 个 Node 测试文件：本地 ComfyUI 启动草稿、引导状态与定位、生成草稿、通知、主题/语言竞态、API 密钥编辑、HTTP 环境请求 ID | Node.js |
| `corpus` | 3 项离线冒烟：图片过滤、过期/损坏预构建资源拒绝、两版词库导出 | 安装了 `corpus/requirements.txt` 的 Python 环境 |
| `browser` | 真实页面流程：共享布局与安全区、通知、引导、API 表单、明确更新、漫游反馈与自动播放、主屏幕请求 ID、桌面/手机自然语言配置与预览 | 应用 Python 依赖、前端依赖、测试前端产物与浏览器 |

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

每个浏览器测试在可用端口启动独立本机 HTTP 服务，临时数据放在 `dev/verification/browser/`，结束后关闭服务并删除数据；设置、喜欢和图片不会在用例之间泄漏。生图使用模拟后端、小型中性词库和确定性的测试编码器，不下载模型，不提交 GPU 或付费 API 请求。通过这些检查代表应用交互正常，真实模型兼容性和出图质量需另行验证。

失败时，截图、trace 与 JSON 报告保留在 `dev/verification/browser/`。使用 `pnpm --dir web exec playwright show-trace TRACE_PATH` 查看 trace。浏览器测试不自动重试。

应用更新另运行 `python -m unittest tests.backend.updates.test_updates -v` 和 `web/tests/browser/updates.spec.mjs`，覆盖显式操作、相同/旧版本、未保存草稿、版本刷新、重连等待上限及移动端展示。发行 CI 为便携冒烟加上 `--previous-release`：启动上一稳定版保存设置，验证替换失败后恢复旧程序，再验证成功升级后的版本、数据与模型保留。可用 `--previous-archive PATH` 指定本地旧包；只有跨版本原生冒烟成功才允许直接安装，同版本替换单独报告。

Python 测试按职责放在 `tests/backend/`，离线检查位于 `tests/corpus/`，工具检查位于 `tests/scripts/`；包使用显式导入，并共享 `tests.ROOT` 定位仓库资源；前端单元测试和浏览器流程分别位于 `web/tests/unit/`、`web/tests/browser/`。运行单个 Python 模块时使用包名，例如 `python -m unittest tests.backend.desktop.test_desktop_launcher -v`。

受控表单覆盖位于 `web/tests/unit/generation-draft.test.mjs` 和 `web/tests/browser/react-forms.spec.mjs`，检查结果不确定的请求 ID、重复提交、草稿保留、工作流节点/JSON 编辑、校验和过时响应；任务历史浏览器检查保留元数据和展开状态。

自然语言变更使用 `python -m unittest tests.backend.application.test_natural_prompts -v` 及 `web/tests/browser/natural-prompts.spec.mjs`，覆盖标签/文本分离、历史反馈、漂流/顺流/停泊、预览复用、部分批次恢复、设置失效、中断自动请求、云端负向通道限制、JSON 协议、凭据掩码和桌面/手机只读预览。LLM 与生图 API 均模拟，语义保真和句式稳定性仍需单独授权的真实服务验证。

## 发版检查

版本标签推送和已有标签的完整手动重跑，都会在四平台构建前统一运行一次 `core`、`ui` 与 `browser`。工作流在编译隔离浏览器前端之前，先准备 HTTP 核心夹具所需的静态目录。离线 `corpus` 组在数据处理变更时单独执行。各平台继续保留成品解压启动冒烟。

日常分支推送不触发 Actions。本次调整从后续版本标签开始生效，不重新构建 v0.5.0。

分组清单维护在 `scripts/check.py` 与 `web/scripts/test.mjs`，优先覆盖用户行为和数据保留约定；更细的改动按需运行单个已有测试。Playwright 的环境和浏览器选项见[官方文档](https://playwright.dev/docs/browsers)。

LLM 连接变更另运行 `tests.backend.application.test_llm_connections`、`tests.backend.application.test_chatgpt` 和 `web/tests/browser/llm-connections.spec.mjs`。OAuth 检查签发本地身份夹具，执行真实回环回调并模拟全部服务商接口；真实账号资格及服务商授权独立手动验证，自动检查不执行付费推理。

本地 ComfyUI 生命周期变更使用 `python -m unittest tests.backend.setup.test_comfy_lifecycle tests.backend.setup.test_local_generation_session tests.backend.desktop.test_desktop_launcher -v` 与 `web/tests/browser/local-generation.spec.mjs`，覆盖明确的下次启动保存、真实轻量子服务启动/复用/退出、进程树所有权、关闭/旧配置、失败和超时恢复、回环配置限制、只读识别、草稿、多候选及桌面/手机布局。夹具不提交图片任务或加载 GPU 模型；各声明支持的平台仍需原生验证，模拟服务不能证明兼容所有 ComfyUI 发行方式。

ComfyUI 启动显示变更另运行 `python -m unittest tests.backend.desktop.test_startup_progress tests.backend.desktop.test_desktop_text tests.backend.runtime.test_managed_output_logging -v`，检查中英文耗时、窄终端、不虚构百分比的等待动画、重定向纯文本、日志脱敏及真实 Windows worker stdout/就绪交接。延迟服务夹具不加载 ComfyUI 模型或提交图片请求。
