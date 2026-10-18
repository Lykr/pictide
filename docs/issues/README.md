# 需求与功能记录

[返回文档导航](../README.md)。这里保存设计背景、变更决定与验证记录；记录反映当时版本，不作为当前安装或升级步骤。当前行为优先查[使用指南](../README.md#使用指南)、[架构](../architecture.md)与[API](../api.md)。

## 候选与提示词

- [词库上传与选择](library-selection.md)
- [词库最低共现次数约束（待确认）](library-cooccurrence-floor.md)
- [共现提示词候选](cooccurrence-candidates-v1.md)
- [PMI 候选数据与生成调整](candidate-pmi.md)
- [共现 ≥1,000 次的极限裁剪](candidate-pair1000.md)
- [共现扩展屏蔽关键词](candidate-blocked-keywords.md)
- [候选生成增量优化方案](candidate-generation-optimization.md)
- [加权随机正向锚点（待确认）](weighted-positive-anchors.md)

## 推荐与偏好

- [第一版推荐模块设计](recommendation-v1.md)
- [用户偏好查看与重置](recommendation-preferences.md)
- [用户偏好导出](preference-export.md)
- [反馈快速返回与后台偏好学习](feedback-background-learning.md)
- [不喜欢与负反馈学习](dislike-feedback.md)
- [图片偏好评分](image-preference-score.md)
- [图片偏好评分缓存](image-score-cache.md)
- [喜欢页按偏好评分排序](liked-score-sort.md)

## 漫游

- [漫游锚点](roam-anchors.md)
- [漫游自动播放](roam-autoplay.md)
- [漫游喜欢标签范围](roam-liked-tags.md)
- [偏好范围与漫游方式](roam-modes.md)
- [漫游候选组合数量](roam-candidate-count.md)
- [漫游推荐力度](roam-recommendation-strength.md)
- [漫游预取流水线](roam-pipeline.md)
- [后端修正后恢复漫游预取](roam-backend-recovery.md)

## 界面与设置

- [通用设置](general-settings.md)
- [跟随系统主题](system-theme.md)
- [简体中文与英文国际化](i18n.md)
- [图片切换动效](image-transitions.md)
- [喜欢页标签筛选](liked-tag-filter.md)
- [Pictide 图标](brand-icon.md)

## 任务与基础流程

- [生图任务事件通知](task-events.md)
- [两个在途生图任务](task-window.md)
- [默认文生图与数据目录统一](default-workflow-data.md)

## 项目与部署历史

- [开发资料与发行产物分离](development-release-directories.md)
- [数据目录整理](data-directory-organization.md)
- [开箱即用的便携发行包](automatic-startup.md)
- [项目独立迁移记录](project-move.md)
- [数据部署历史记录](data-layout-history.md)
