# 后端修正后恢复漫游预取

状态：已确认并实现。

## 原因

当前版本的失败任务会通过 Store.ensure_roam 持久暂停漫游 epoch。保存后端仅发布 backends 事件，不更新漫游 epoch；旧失败任务在下次读取时仍会让同一版本暂停。已核实本机是 CheckpointLoaderSimple 的 ckpt_name 不可用导致 HTTP 400，任务为 failed，未取得 backend_prompt_id。

## 架构

保留 Browser → Host → Application → Task Connections / Store / RoamSettings 的既有模块边界。恢复规则属于 Application，不让任务、推荐、候选互相调用，不新增恢复接口、数据库表、定时重试或自动重提旧任务。

## 调用与数据流

1. 用户在设置中保存后端，沿原链路解析并持久化配置。
2. Application 在既有漫游锁内读取漫游配置与暂停状态。保存的是当前漫游实际使用的后端（含自动选取的首个后端），且漫游已暂停时，调用既有 RoamSettings.save，用相同预取数、历史上限、后端和预设创建新的 epoch；其余选项从存储保留。
3. 不改变偏好范围、漫游方式、候选数、推荐力度、播放间隔；不清空图片、预取结果或现有任务，也不重试旧失败任务。旧版本的失败不再暂停新版本。
4. 发布既有 backends 和 roam_settings 事件。浏览器复用 loadRoamSettings → applyRoamSettings，清除暂停提示；处于漫游时按现有预取入口补图，不主动恢复自动播放。
5. 修改未使用的后端、保存失败或漫游未暂停时，不更新 epoch。新的配置仍不可用时，新任务失败后按现有规则再次暂停，不循环重试。

## 接口

HTTP 字段、Application.save_backend 返回值、Store 和 RoamSettings 的对外签名均不改。新增 Application.save_backend 成功路径到现有 RoamSettings.save 的恢复调用，以及 roam_settings 事件。保留原显式保存完整漫游设置的手动恢复方式。

## 验证与发布

只用临时 SQLite 和模拟后端，冒烟覆盖当前后端失败→保存修正配置→新 epoch 可排队、旧失败不重新阻塞；未使用后端及未暂停配置不重置；已有图片、排队任务与漫游选项保留。不提交 GPU 任务。发布前备份数据库、核对任务并告知后端重启。


## 实施验证

Application.save_backend 保存成功后，在现有漫游锁内检查实际选中的后端和暂停状态。仅当保存当前后端且已暂停时，复用 RoamSettings.save 生成新 epoch；不传会保留 epoch 的候选数/推荐参数，其他设置由存储原样保留。最后发布 roam_settings 事件，防止容量为 1 的事件队列只保留 backends 而丢失恢复通知。

两项隔离 HTTP 冒烟通过：自动选择后端的缺模型失败 → 保存修正配置 → 新候选可排队，旧失败保留且不再阻塞；原图片、排队任务及其后端快照、所有漫游选项保留。未暂停、保存其他后端和保存校验失败均不重置。测试使用模拟后端和临时 SQLite，未提交真实 GPU 任务。
