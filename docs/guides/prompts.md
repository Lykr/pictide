# Prompts and Presets

[简体中文](../zh-CN/guides/prompts.md)

[Documentation](../README.md)

Save a subject or style as a preset and let Pictide fill out the prompts for you. You can start with the default preset and adjust it as you go.

## Libraries and presets

A library supplies tags to combine; a preset saves your fixed terms and how those combinations are made.

In Arrange, select a preset and add positive terms you want to keep. Put things you want to avoid in the negative prompt. Fixed terms can be library tags or your own complete descriptions. The initial preset includes `general` as a positive term; you can remove or replace it. Leave the negative prompt empty when using OpenAI Images or Gemini.

Use Preview to try combinations before generating images: it produces prompt text only. Save when you are happy with it. The selected preset is shared by Roam and Generate; edits take effect after saving. Text already entered on Generate stays as it is, and the next preset-based prompt request uses the new selection.

Edit the preset name directly, or copy a preset to keep separate settings for different subjects.

## Adjust combinations

Try the defaults first, then adjust as needed:

- **Minimum and maximum counts**: control prompt length, including fixed positive terms.
- **PMI threshold and minimum co-occurrence count**: set the statistical association requirements between tags. Higher thresholds usually leave fewer terms available, so a result can be shorter than the target.
- **Sequence change budget**: control how much Flow and continuous previews can change. `0` keeps the previous combination.

Statistical association helps combine tags; the image model determines the resulting picture.

## Add and switch libraries

Portable packages include `filtered`, ready to use. For a broader range of tags, download `all-ratings` from [Vocabulary editions](vocabularies.md).

Under Prompts → Library → Upload, select the downloaded `.sqlite3` file. It is selected automatically after upload. You can also place a finished library in `libraries/` under your data directory, refresh, and select it. Multiple versions can coexist. Switching preserves your personal presets and fixed terms; newly generated prompts use the selected library.

## Data preparation

To build your own library from raw data, see [Corpus Processing](../dev/corpus.md). For everyday use, download a ready-made edition.
