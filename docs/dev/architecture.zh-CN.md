# 架构与模块边界

[English](architecture.md)

[文档导航](README.zh-CN.md)。本页只说明模块、职责和依赖；具体调用顺序见[调用和数据流](architecture/flows.zh-CN.md)，推荐内部见[推荐模块](architecture/recommendation.zh-CN.md)。

Pictide 是前后端分离的本地 Web 应用。`web/` 是唯一浏览器入口，`backend/` 提供业务 API；部署时由同一 Python 进程提供已编译前端与 API，正常运行不需要 Node 服务。

## 架构图

当前模块职责如下。Web 后端中的应用编排层是交互核心，统一传递候选、评分、生成请求与反馈；候选、推荐、任务模块之间不直接调用或互相依赖。HTTP 宿主是独立 Web 服务；ComfyUI、OpenAI Images 与 Gemini 只承担生图能力，云端提示词会离开本地应用。

```mermaid
flowchart TD
    UI["浏览器：图片 Feed / 喜好 / 生成设置"]
    Host["Web 后端接入：HTTP API / 实时事件 / 生命周期"]
    App["应用编排核心：生成 / 反馈 / 预取 / 模块协调"]
    Rules["候选模块：共现扩展 / 完整提示词组合 / 连续变化预算"]
    Rec["推荐模块：候选组合评分 / MiniLM 特征 / 正负偏好学习"]
    Jobs["任务模块：调度 / 恢复 / 结果关联"]
    Backend["生成后端接口"]
    Comfy["ComfyUI API"]
    Cloud["OpenAI Images / Gemini Interactions"]
    Store["存储接口"]
    DB[("SQLite + 图片文件")]

    UI <--> Host
    Host <--> App
    App <--> Rules
    App <--> Rec
    App <--> Jobs
    Jobs --> Backend
    Backend --> Comfy
    Backend --> Cloud
    App --> Store
    Rules --> Store
    Rec --> Store
    Jobs --> Store
    Store --> DB
```


## 目录映射

```text
pictide/
  web/                         唯一前端，npm 包名 pictide-web
    index.html                 单一 HTML 入口
    src/main.tsx               React 应用入口与视图导航
    src/                       页面、交互控制器、共享组件与主题
    dist/                      Vite 发布资源
  backend/
    host.py                    HTTP API、SSE、静态资源、启动与关闭
    desktop.py                 Windows 桌面会话、单实例锁与托盘生命周期
    desktop_launcher.py        临时进度进程与无控制台窗口的服务启动
    windows_tray.py            Windows 原生托盘与自有启动终端管理
    desktop_text.py            跟随系统语言的启动与托盘文案
    application.py             生成、候选、评价、清理等应用编排
    domain.py                  公共输入校验及错误
    paths.py                   数据路径与本进程运行环境
    candidate/                 只读共现词库、预设、连续变化预算与离线导入
    recommand/                 组合特征、MiniLM、贝叶斯评分与学习；沿用目录拼写
    task/                      调度、恢复、取消与结果关联
    generation/                生图接口、ComfyUI 工作流、OpenAI Images 与 Gemini
    store/                     SQLite、图片/JSON、清理策略及回收
  data/                        可替换的数据根目录
  docs/                        文档入口
    guides/                    使用指南
    dev/                       开发文档与主题概览
      architecture/            架构与流程细节
      reference/               API、数据与设计参考
      issues/                  需求设计、功能变更与交付记录
  tests/
  start.cmd
  start.ps1
```

| 图中模块 | 实际位置 | 职责与边界 |
| --- | --- | --- |
| UI | `web/` | 展示、草稿、键盘与交互；通过 HTTP/SSE 与宿主通信 |
| Host | `backend/host.py` | 请求与响应、来源检查、错误映射、静态资源、事件与生命周期；调用应用编排 |
| App | `backend/application.py` | 连接候选、推荐、任务与存储，编排漫游缓冲、设置版本与暂停条件 |
| Rules | `backend/candidate/` | 只读词库、共现预设与候选生成、序列预算；不调用生图服务 |
| Rec | `backend/recommand/` | 完整组合评分、标签特征编码与正负偏好学习；不生成候选或调用生图服务 |
| Jobs | `backend/task/` | 任务状态、幂等、恢复、取消与产物关联；依赖生图及存储接口 |
| Backend / Comfy / Cloud | `backend/generation/` | 注册适配器与能力，准备请求、提交、按能力查询并读取图片结果 |
| Store / DB | `backend/store/` | SQLite 与文件存储、原子反馈、图片提示词关联及懒清理 |

## 依赖规则

- Host 负责传输、来源检查和生命周期，通过 App 执行用例；不承载候选求解、推荐算法或 SQL。
- App 是候选、推荐、任务之间的唯一交互核心。它获取完整候选池、请求组合评分、选择组合并提交任务；评分不会回传候选进行重新抽取。
- Candidate、Recommendation、Task 不直接相互调用或导入。共享推荐请求/结果位于 `backend/contracts/recommendation.py`，候选快照位于 `backend/candidate/contracts.py`。
- Candidate 通过 Host 注入的存储接口读取在线词库和预设，不导入 SQLite 适配器；离线下载、导入工具独立使用 SQLite，不放入在线启动或请求链。
- Task 依赖 Generation 和 Store，负责确定任务的提交、事件核实、恢复、取消与结果关联；Generation 隔离协议差异；ComfyUI 返回远端任务引用，OpenAI Images 与 Gemini 在一次 HTTP 请求中返回完整结果。云端结果不确定的提交不自动重试。
- 浏览器通过 HTTP/SSE 管理展示、输入和草稿，不直接读写配置或数据库。提示词页是同一前端中的视图，没有额外站点或 iframe。
- Store 持久化任务、图片、反馈、快照和学习状态。反馈学习依据实际生成快照，不用当前词库覆盖历史语义。

## 前端引导

首次使用引导位于 `web/src/onboarding/`，分为通用可观察状态机、纯 Pictide 步骤规则和状态适配器。业务控制器与组件通过 `shared/ui-state.mjs` 发布已确认事实，通过 `shared/ui-targets.ts` 注册语义化元素引用，不导入引导步骤。`components/onboarding/` 的 React 展示层随布局变化测量组件，在目标附近展示带箭头和聚焦的提示卡，通过纯几何函数避开操作控件。

引导观察测试、保存、反馈、锚点变更的成功结果和图片实际载入状态。导航沿用既有 UI 意图入口，生成与数据修改由用户操作原有控件触发。浏览器本地只保存引导进度和必要图片标识，不新增后端 API、数据库表或运行依赖。详见[引导设计与验证](issues/first-run-guide.md)。

## 启动准备

源码与便携启动共用 `backend/application.py` 的 `PictideApplication.prepare_startup()`。该入口先初始化存在的随包词库，再通过 `backend/recommand/resources.py` 校验或下载固定 MiniLM 文件到所选运行数据目录。准备成功后，Host 才启动 HTTP/SSE 并打开浏览器；失败终止启动，保留未完成下载供下次重试。编码器只读取准备好的本地文件，离线 corpus 工具继续独立于启动链路。详见[推荐依赖准备](architecture/recommendation.zh-CN.md#推荐依赖准备)。

Windows 启动入口选择 `--desktop`：临时进度进程以 `CREATE_NO_WINDOW` 启动服务、转发启动输出，托盘注册成功后退出，兼容由 Windows Terminal 承载的启动终端。`backend/desktop.py` 在准备资源前取得数据目录锁并预留 HTTP 端口，HTTP 就绪后注册原生托盘并打开浏览器。启动失败时保留错误信息，托盘不可用时回退到原终端。托盘线程使用 Per-Monitor V2 DPI 感知，按任务栏 DPI 加载图标，不修改系统设置。托盘只负责打开网页、日志目录和请求 Host 正常退出，不承载业务状态。启动进度和托盘文案按系统显示语言使用简体中文或英文。`--cli` 与 `--no-browser` 保留终端模式；Linux/macOS 沿用既有入口。详见[桌面生命周期设计](issues/desktop-launcher.md)。

## 继续阅读

| 要了解的内容 | 主题 |
| --- | --- |
| 生成、预取与反馈的模块调用 | [调用和数据流](architecture/flows.zh-CN.md) |
| 推荐内部职责、特征和当前能力 | [推荐模块](architecture/recommendation.zh-CN.md) |
| 所有 HTTP 字段与状态码 | [API 参考](api.zh-CN.md) |
| 数据文件、备份与表的归属 | [数据目录](data-layout.zh-CN.md)、[存储参考](reference/storage.zh-CN.md) |
| 如何新增前端或生图适配器 | [开发流程](development.md)、[页面设计规范](design-system.md) |
| 当时的设计决定与验证 | [需求记录](issues/README.md) |
