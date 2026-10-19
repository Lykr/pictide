# 词库版本

[English](vocabularies.md)

[文档导航](../README.zh-CN.md) · [提示词与预设](prompts.zh-CN.md)

词库帮助 Pictide 组合提示词。便携包附带默认词库，可以直接开始；想拓宽可探索的内容，再换用另一版。

## 选择版本

| 版本 | 内容范围 |
| --- | --- |
| `filtered`（默认） | 使用 `general` 和 `sensitive` 评级的数据，不含 `questionable`、`explicit` 来源 |
| `all-ratings` | 使用全部四种评级的数据 |

词库决定可组合的提示词，最终画面也取决于模型和生图服务。

## 下载与切换

下载所需词库：

- [filtered](https://github.com/Lykr/pictide/releases/download/corpus-editions-fa4d623c2a7d32d2569a3e1657e4aa5b1f6937284cc42091d60c1bcc8d899c5b/pictide-vocabulary-filtered.sqlite3)
- [all-ratings](https://github.com/Lykr/pictide/releases/download/corpus-editions-fa4d623c2a7d32d2569a3e1657e4aa5b1f6937284cc42091d60c1bcc8d899c5b/pictide-vocabulary-all-ratings.sqlite3)

在「提示词 → 词库 → 上传」中选择下载的 `.sqlite3` 文件，上传后自动选用。两版可以并存，之后从词库列表切换即可。

切换会用于后续生成提示词，个人预设、已有图片和任务保留。
