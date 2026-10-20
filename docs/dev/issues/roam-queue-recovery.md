# 漫游队列的断连恢复

## 概述

修复 ComfyUI 断连后旧的不确定任务长期占满生成名额，使新漫游任务一直排队的问题。

## 架构

```mermaid
flowchart LR
    Task[Task 调度与核对] --> Adapter[现有 ComfyUI 适配器]
    Adapter --> Comfy[ComfyUI 队列与历史]
    Task --> Store[现有任务存储]
```

## 职责边界

- 保持现有模块和接口；ComfyUI 适配器区分连接建立失败与请求发出后结果不确定。
- Task 核对远端记录后管理名额；Store 沿用 `finish_dispatch`，保留任务、图片与反馈记录。
- 本次为现有边界内的内部修复，不增加 API、数据库字段或前端交互。

## 调用和数据流

```mermaid
flowchart TD
    Submit[提交任务] --> Connect{连接是否建立}
    Connect -->|建立前失败| Failed[标记失败并释放名额]
    Connect -->|结果不确定| Unknown[保留 unknown 且不重发]
    Unknown --> Reconcile[按请求 ID 查询队列与历史]
    Reconcile -->|查询失败| Hold[保留名额，稍后核对]
    Reconcile -->|找到任务| Track[关联远端 ID 并继续跟踪]
    Reconcile -->|查询成功且未找到| Release[释放占用，保留状态并继续核对]
    Release --> Next[调度后续排队任务]
```

## 重点关注

- `ClientConnectorError` 表示 HTTP 请求尚未发出；超时、连接中断、服务端错误和无效成功响应仍按不确定结果处理。
- 成功查询未找到只表示当前队列和可查询历史没有记录，不将旧任务改为已完成或重新排队；后续发现迟到记录仍可关联并保存结果。
- 已知仍在远端排队或执行的任务保留名额；远端不可达时继续保留占用，避免仅凭本地等待时间推断结果。
- 启动恢复复用同一核对逻辑，解决已有数据中的占用，不编写专项数据迁移。
- 使用隔离 SQLite 与模拟后端覆盖断连、查询失败、两个旧占用、重启恢复和迟到结果；部署前备份运行数据库，检查任务后重启，验证当前用户队列恢复。
