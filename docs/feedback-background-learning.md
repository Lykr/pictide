# 反馈快速返回与后台偏好学习

## 概述

喜欢、不喜欢和撤回反馈保存到 SQLite 后返回，推荐学习与本次反馈触发的历史清理由应用编排后台执行。

## 架构

```mermaid
flowchart TD
    UI["浏览器：喜欢 / 不喜欢 / 撤回"] --> Host["HTTP Host"]
    Host --> App["应用编排：保存反馈 / 返回响应"]
    App --> Store["存储：反馈状态 + 待学习记录"]
    App --> Worker["编排内部：事件唤醒的单个后台任务"]
    Worker --> Rec["推荐模块：应用已保存反馈"]
    Worker --> Cleanup["既有历史清理"]
    Rec --> Model["既有偏好状态存储"]
```

## 职责边界

- `PUT /api/artifacts/{id}/feedback` 的请求和返回字段保持不变；成功响应表示反馈状态及可学习记录已提交，不表示推荐模型已更新。复用 `Storage.rate()` 返回的图片状态，再读取图片修订号，发布既有 feedback 事件并返回。
- 应用编排内部维护单个事件唤醒任务，调用现有推荐同步逻辑处理持久待学习记录；处理过程中收到新反馈时再执行一轮，连续唤醒合并。不逐次创建并发学习任务，不新增队列服务、定时器或数据库表。
- 推荐接口、反馈正负含义和撤回逻辑不变；仍按记录版本处理同一图片的最新有效反馈。候选、推荐、任务模块仍只与应用编排交互。
- 评分入口不再强制同步处理全部待学习记录，改为唤醒后台并使用已完成的偏好状态评分；启动与关闭由既有应用生命周期管理后台任务。

## 调用和数据流

```mermaid
sequenceDiagram
    participant UI as 浏览器
    participant Host as HTTP Host
    participant App as 应用编排
    participant Store as SQLite 存储
    participant Worker as 编排后台任务
    participant Rec as 推荐模块
    UI->>Host: PUT 反馈 value
    Host->>App: 保存反馈
    App->>Store: 同一事务保存状态与待学习记录
    Store-->>App: 当前图片状态
    App->>Store: 读取图片修订号
    App-->>Host: 图片状态 + 修订号
    Host-->>UI: 成功响应，恢复按钮操作
    App->>Worker: 唤醒后台任务（不等待处理结果）
    Worker->>Store: 读取待学习反馈
    Worker->>Rec: 应用反馈，更新偏好
    Worker->>App: 执行既有历史清理
```

## 重点关注

- 新偏好稍后生效，已有预取图片保持；仅取消客户端等待学习和清理，不对保存失败做成功反馈。
- 不喜欢或取消喜欢的图片可能在响应后按既有规则清理，通过既有 artifacts 事件更新界面。
- 复用持久记录处理失败与重启恢复，失败后等待后续反馈或评分入口再次唤醒；关闭时等待正在处理的一轮，未处理记录保留。
- 验证重点：模拟慢学习时 HTTP 已返回；连续喜欢／不喜欢／撤回最终状态正确；待处理反馈可在重启后学习；少量冒烟即可。
