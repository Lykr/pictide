# MiniLM 首次启动下载

## 概述

便携包只携带 MiniLM 的固定下载清单，应用首次启动时后台下载模型，后续启动复用所选数据目录中的本地文件。

## 架构

```mermaid
flowchart LR
  Build[发行构建] --> Package[程序 / 运行依赖 / 前端 / 词库 / 模型清单]
  Package --> Host[Host 生命周期]
  Host --> App[应用编排]
  App --> Prepare[推荐模块：模型准备]
  Prepare --> Hub[固定版本 Hugging Face 文件]
  Prepare --> Models[data/models/minilm]
  Models --> Encoder[现有 MiniLM 编码器]
  App --> UI[现有 HTTP / SSE 状态]
```

## 职责边界

- 发行构建：导出词库和固定模型清单；移除构建阶段模型下载、模型文件复制和 `--models-dir` 参数，保留 FastEmbed、ONNX Runtime、tokenizer 等运行依赖及许可证声明。
- 推荐模块：维护唯一的模型来源、revision、文件大小与 SHA-256；提供异步模型准备入口，按需下载缺失文件，使用 `.part` 续传并在校验后原子发布文件。编码器继续只读取本地文件并执行 CPU 推理。
- 应用编排：在现有启动/停止生命周期内管理一次模型准备任务；模型准备成功后唤醒反馈学习，通过现有 `recommendation` 事件刷新页面。退出时停止下载并保留可续传文件。
- 浏览器：沿用推荐可用状态与错误字段，展示准备中或下载失败；模型准备期间可浏览和配置应用，生成沿用现有推荐不可用时的降级行为，反馈继续保存。
- 数据目录：模型落在所选 `data/models/minilm/`，构建与测试均使用独立数据；完整的用户已有模型继续使用，个人记录保留。

## 调用和数据流

```mermaid
sequenceDiagram
  actor User as 用户
  participant Host as Host
  participant App as 应用编排
  participant Model as 推荐模型准备
  participant Hub as Hugging Face
  participant UI as 页面
  User->>Host: 启动应用
  Host->>App: 初始化词库并启动现有服务
  App->>Model: 启动一次后台准备任务
  Host->>UI: 打开可使用的页面
  alt 本地模型完整
    Model-->>App: 就绪，复用本地文件
  else 缺失模型文件
    App-->>UI: 推荐模型准备中
    Model->>Hub: 下载固定 revision，按文件续传
    Model->>Model: 校验大小和 SHA-256，发布到 data/models/minilm
    Model-->>App: 就绪或失败
  end
  App-->>UI: 现有 recommendation 状态事件
  App->>App: 就绪后恢复反馈学习
```

## 重点关注

- 页面启动与模型下载并行；模型下载失败时保留可使用的页面与反馈，显示错误，下次启动自动重试。
- 源码和便携启动共用准备流程，离线环境可按文档预放模型；已有完整模型继续复用，不在运行中切换用户模型。
- 模型来源与校验信息由推荐模块唯一维护；离线 corpus 工具继续只处理词库，线上启动不导入 corpus。
- Actions 保持复用已发布词库；更新真实便携包冒烟，覆盖首次下载、再次启动复用与下载失败保留数据；不提交 GPU 生图任务。
- 同步双语 README、安装指南、架构/数据文档和构建说明；记录模型移出后实测的 ZIP 体积。
