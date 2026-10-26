# 调用和数据流

[English](../../../dev/architecture/flows.md)

[架构概览](../architecture.md) · [API 入口](../api.md)

这里说明现有模块间的调用顺序与数据关联；静态职责以架构概览为准。

## 候选、评分与生成

```mermaid
sequenceDiagram
    participant App as 应用编排
    participant Rules as 候选模块
    participant Rec as 推荐模块
    participant Jobs as 任务模块
    App->>Rules: 请求候选模块提供完整提示词组合集合
    Rules-->>App: 各组合的标识、完整正负提示词及标签快照
    App->>Rec: 提交完整候选组合集合，请求评分
    Rec-->>App: 组合标识对应的分数
    Note over App: 根据评分选择一个完整组合
    App->>Jobs: 提交生成请求及关联信息
    Jobs-->>App: 任务状态与产物信息
    Note over App: 保存图片与实际提示词的关联
    Note over App: 接收用户反馈，读取对应生成记录
    Note over App: 反馈及待学习记录落库后返回客户端
    App->>Rec: 编排后台任务提交反馈及生成时的特征快照
```

- 候选模块先根据标签库与规则提供本次请求的全部候选提示词组合，每个候选都是可提交生成的完整正负提示词，包含组合标识、标签快照及版本；共现门槛与连续预算由候选模块处理；共现不足时组合可能短于目标长度。
- 推荐模块对 App 提供的完整组合评分，返回组合标识与分数，不逐词打分后交回抽取，不新增、修改或删除组合。Thompson Sampling 的探索体现在组合评分中。
- App 获取候选组合集合，交给推荐模块评分，再根据评分选择一个完整组合并提交任务；不将评分交回候选模块重新组装提示词。任务模块只接收确定的生成请求。推荐不可用时，由 App 在既有合法组合中按默认策略选择。
- 生成记录保存所选组合及实际标签内容与版本；反馈由 App 关联历史记录后交给推荐模块，不以最新标签库重新解释历史，也不把一次点赞直接视为喜欢全部标签。撤回喜欢不等同于不喜欢。

## 自然语言准备

每个生图后端选择 `danbooru`（默认）或 `natural_language`，并选择已保存的 `llm_id`。App 仍对完整标签组合评分；自然语言模式只把选中的组合交给 `PromptPreparation`，由它解析 LLM 配置，经 `backend/prompting/` 串行转换，在创建图片任务前保存成功文本。Task 和生图适配器只接收最终字符串，不调用 LLM。

文本服务使用 [Chat Completions](https://developers.openai.com/api/reference/python/resources/chat/subresources/completions/methods/create)，请求含 `stream:false` 和 `response_format:{type:"json_object"}`，要求返回 `positive`、`negative` 字符串及 `finish_reason:stop`。传输沿用共享代理与 TLS，超时 120 秒，禁止重定向，响应大小有界，不自动重试。不公开服务商错误正文或凭据。

ChatGPT 连接使用官方[开源应用登录流程](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)。Host 提供本地控制接口，Prompting 适配器管理短时回环监听、授权和服务商传输，`store/chatgpt.py` 负责受保护的凭据文件。PyJWT 与 cryptography 校验 RS256 签名、issuer、audience、到期时间和 nonce；跨进程刷新串行执行。Responses 使用 `store:false`、`stream:true`、developer 指令和 JSON 输出，只有 `response.completed` 才表示成功。失败不切换到 API Key 计费。账号模型发现只保留 `visibility:list`，沿用服务商顺序。

漂流不传此前文本；顺流传入之前的标签与文本，要求尽量少改措辞，标签不变时复用兼容文本；停泊在标签输入与生图/LLM 配置签名匹配时复用完整文本，否则先初始化一次。参考来自预取链最近选中的组合，找不到时使用当前图。LLM 指令引导语义与结构保持，校验只检查形状和大小，不验证真实含义。

漫游在设置锁外异步准备，通过 `preparing_prompt:true` 报告状态；重复 ensure 共享进行中的准备。入队前，App 再次检查 epoch 与生图配置。失败暂停该 epoch；完整保存漫游设置会明确开启新 epoch 并允许重试，即使提交值完全不变。健康 epoch 下的普通保存仍保留准备与预取。已持久化为尝试过却没有结果的转换，重启后不自动重复；已完成结果可直接恢复，无需再次调用服务。

生成页先准备全部轮次，再提交任何图片任务；保存所选轮次和已完成转换，使相同请求的明确重试可继续未完成部分，不重复已完成工作。同轮图片共享文本，候选各轮分别转换。预览 ID 必须匹配标签与当前配置。准备结果属于有界可丢弃历史，过期预览返回冲突；已完成批次继续使用原有持久幂等重放。

图片/任务提示词字段保存实际提交文本，`source_prompts` 保存原始正负概念，漫游候选快照另存结构化词项与渲染文本。锚点、喜欢标签筛选、评分校验和反馈使用这些历史标签。缺少独立来源快照的旧记录保持原有行为。界面中的自然语言文本只读，用户通过标签与锚点编辑。

## 手动生成批次

App 接收每次数量和生成次数，必要时调用 Candidate 逐轮产生完整文本，再一次校验并保存整批任务。Task 执行确定的生成请求，不重新抽词。每轮内共用提示词；支持图像种子的后端逐任务独立随机或按序递增。Danbooru 云端适配器拒绝非空负向提示词，云端适配器均拒绝指定图像种子；候选种子仍只在本地控制提示词选择。

批次幂等与容量检查在存储事务中执行，不足时整批拒绝；同一 request_id 重试恢复原计划，不再次抽取。新计划最多 100 个待处理任务，旧式无 repetitions/candidate 的 Danbooru 提交沿用 10 个入队门槛。自然语言提交还会在转换前检查容量，并在提交事务前再次核对 LLM 配置。具体字段见[任务接口](../reference/api/jobs.md)。

## 漫游预取与出图

```mermaid
sequenceDiagram
    participant UI as 浏览器
    participant App as 应用编排
    participant Store as 存储
    participant Candidate as 候选
    participant Rec as 推荐
    participant Task as 任务
    participant Gen as 生图适配器
    UI->>App: ensure(anchor_id, demand)
    App->>Store: 读取设置、窗口及待完成任务
    App->>Candidate: 请求完整候选组合
    Candidate-->>App: 组合池与实际词项快照
    App->>Rec: 对组合池评分
    Rec-->>App: 组合分数与均值分
    App->>Store: 保存选中组合、任务与快照
    App->>Task: 唤醒任务调度
    App-->>UI: 当前预取状态
    Task->>Gen: 提交确定请求
    alt ComfyUI 异步任务
        Gen-->>Task: 远端引用，随后完成事件或轮询
        Task->>Gen: 核实完成并读取结果
    else OpenAI Images 或 Gemini HTTP 响应
        Gen-->>Task: 完整图片结果
    end
    Task->>Store: 保存图片、实际提示词和评分缓存
    Task->>App: on_change 通知结果变化
    App-->>UI: 经 Host/SSE 发布变更通知
```

浏览器在进入漫游、切图、任务状态更新等入口检查缺口，不另设投喂循环。每次 ensure 最多创建一个任务，最多两个未完成漫游任务，让提示词准备与上一张出图重叠；全应用最多两个任务在后端在途，手动任务优先占用新空位。Task 收到完成事件后核实状态、补位并保存结果；ComfyUI 事件不可用时回退轮询。OpenAI Images 与 Gemini 经异步 HTTP I/O 等待同步完整结果，将 Base64 或 URL 下载图片存入本地。它们没有远端恢复引用；超时或中断的提交保持不确定，不自动重发。新选择的云端漫游后端先关闭预取，用户明确开启后再预取。

ComfyUI 建立连接失败属于确定的提交失败并释放名额。不确定任务始终不重发：Task 按请求 ID 查询后端队列和历史；查询成功且未找到时释放名额，保留不确定记录以继续恢复迟到结果；查询失败时保留占用。

切换偏好范围、漫游方式或锚点时，App 经 Store 保存设置与预取失效状态，迟到产物隐藏。顺流从实际选中组合继续，停泊复用整组提示词；候选、推荐和任务之间始终不直接交互。

当前设置版本失败、状态不确定或取消时暂停预取。保存完整漫游设置可解除暂停；修正并保存当前漫游后端也可恢复。保留历史图片和任务，不自动重提旧失败任务。详情见[漫游指南](../../guides/roam.md)、[预取接口](../reference/api/roam.md)。

## 反馈与后台学习

```mermaid
sequenceDiagram
    participant UI as 浏览器
    participant App as 应用编排
    participant Store as 存储
    participant Worker as App 后台学习任务
    participant Rec as 推荐
    UI->>App: 设置喜欢、不喜欢或撤回
    App->>Store: 同事务保存反馈和待学习记录
    App-->>UI: 返回已保存图片状态
    App->>Worker: 唤醒
    Worker->>Store: 读取待应用反馈及历史快照
    Worker->>Rec: apply_feedback(组合, 评价, 修订)
    Rec->>Store: 保存偏好状态及证据
    Worker->>Store: 执行本次反馈触发的懒清理
```

学习使用当时实际文本、方向与组合关联，不按当前词库重解释历史。未评价是未知，撤回取消原贡献；反馈请求成功表示已保存，不能据此认定推荐已经学习完成。模型暂不可用时记录保留，由后续操作唤醒处理。

## 进一步查阅

- [生图提交窗口设计](../issues/task-window.md)
- [存储与图片来源](../reference/storage.md)
- [推荐内部特征流程](recommendation.md)
