# 文档导航

`docs/` 保存长期维护的项目约定；`docs/issues/` 保存需求设计、功能变更与交付记录。新增需求文档继续使用原文件名风格，并遵循[设计模板](design-template.md)。

## 项目约定

- [架构与模块边界](architecture.md)
- [Git 开发流程](development.md)
- [Pictide 页面设计规范](design-system.md)
- [设计文档模板](design-template.md)
- [数据目录](data-layout.md)

## 需求与功能记录

### 候选与提示词

- [共现提示词候选](issues/cooccurrence-candidates-v1.md)
- [PMI 候选数据与生成调整](issues/candidate-pmi.md)
- [共现扩展屏蔽关键词](issues/candidate-blocked-keywords.md)
- [候选生成增量优化方案](issues/candidate-generation-optimization.md)

### 推荐与偏好

- [第一版推荐模块设计](issues/recommendation-v1.md)
- [用户偏好查看与重置](issues/recommendation-preferences.md)
- [用户偏好导出](issues/preference-export.md)
- [反馈快速返回与后台偏好学习](issues/feedback-background-learning.md)
- [不喜欢与负反馈学习](issues/dislike-feedback.md)
- [图片偏好评分](issues/image-preference-score.md)
- [图片偏好评分缓存](issues/image-score-cache.md)
- [喜欢页按偏好评分排序](issues/liked-score-sort.md)

### 漫游

- [漫游锚点](issues/roam-anchors.md)
- [漫游自动播放](issues/roam-autoplay.md)
- [漫游喜欢标签范围](issues/roam-liked-tags.md)
- [偏好范围与漫游方式](issues/roam-modes.md)
- [漫游候选组合数量](issues/roam-candidate-count.md)
- [漫游推荐力度](issues/roam-recommendation-strength.md)
- [漫游预取流水线](issues/roam-pipeline.md)
- [后端修正后恢复漫游预取](issues/roam-backend-recovery.md)

### 界面与设置

- [通用设置](issues/general-settings.md)
- [跟随系统主题](issues/system-theme.md)
- [简体中文与英文国际化](issues/i18n.md)
- [图片切换动效](issues/image-transitions.md)
- [喜欢页标签筛选](issues/liked-tag-filter.md)
- [Pictide 图标](issues/brand-icon.md)

### 任务与基础流程

- [生图任务事件通知](issues/task-events.md)
- [两个在途生图任务](issues/task-window.md)
- [默认文生图与数据目录统一](issues/0001-default-workflow-data.md)
