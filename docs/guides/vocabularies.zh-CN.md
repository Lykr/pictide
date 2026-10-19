# 词库版本

[English](vocabularies.md)

[文档导航](../README.zh-CN.md) · [提示词与预设](prompts.zh-CN.md)

Pictide 提供两版处理好的统计词库。便携包默认随带 `filtered`；需要使用全部源评级的统计时，可单独下载 `all-ratings`。

## 选择版本

| 版本 | 纳入统计的源图片数据 | 普通标签最低出现次数 | 标签对最低共现次数 | 便携包默认 |
| --- | --- | --- | --- | --- |
| `filtered` | `general`、`sensitive`；统计前整条排除包含 `questionable` 或 `explicit` 的图片数据 | 100 | 1,000 | 是 |
| `all-ratings` | 全部四种评级：`general`、`sensitive`、`questionable`、`explicit` | 100 | 1,000 | 否 |

两版均统计普通标签与观察到的评级，不额外移除单个标签名称。`all-ratings` 包含全部源评级，仍应用上述频次门槛，保存处理后的统计而非原始图片记录。版本名描述源数据过滤范围，因此使用 `filtered` / `all-ratings`，而非 SFW / NSFW。

## 下载与切换

从[词库资源 Release](https://github.com/Lykr/pictide/releases/tag/corpus-editions-fa4d623c2a7d32d2569a3e1657e4aa5b1f6937284cc42091d60c1bcc8d899c5b)下载所需的 `.sqlite3`：

- [filtered](https://github.com/Lykr/pictide/releases/download/corpus-editions-fa4d623c2a7d32d2569a3e1657e4aa5b1f6937284cc42091d60c1bcc8d899c5b/pictide-vocabulary-filtered.sqlite3)
- [all-ratings](https://github.com/Lykr/pictide/releases/download/corpus-editions-fa4d623c2a7d32d2569a3e1657e4aa5b1f6937284cc42091d60c1bcc8d899c5b/pictide-vocabulary-all-ratings.sqlite3)

在「提示词 → 词库 → 上传」中选择下载文件，上传成功后自动选用。也可复制到当前数据目录的 `libraries/`（默认 `data/libraries/`），点击「刷新」，再从词库下拉列表选择。保留各自文件名即可让两版并存。

个人预设、固定词、草稿、已有任务与预取图片保留，新建候选使用所选词库。共现下限与固定词重新识别规则见[词库切换](prompts.zh-CN.md#添加与切换词库)。

每版提供对应 `.report.json`；资源 Release 另有 `manifest.json` 和 `SHA256SUMS`，用于核对来源和文件完整性。这些元数据供查看与校验，上传到 Pictide 时选择 `.sqlite3` 即可。可重复导出步骤见[数据处理](../dev/corpus.zh-CN.md#导出两版词库)。
