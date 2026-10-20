# 安装与接入

[English](getting-started.md)

[用户文档](../README.zh-CN.md) · 下一步：[漫游](roam.zh-CN.md)

选一个生图服务，连接好后就能开始漫游，无需手动编写提示词。

## 启动前准备

下载并解压便携包，按系统启动：[Windows](setup/windows.zh-CN.md#便携版本) · [Linux](setup/linux.zh-CN.md#便携版本) · [macOS](setup/macos.zh-CN.md#便携版本)。便携包已带好运行环境和词库；首次启动还需下载下方的推荐依赖。浏览器打开后，在「设置 → 生图 API」接入服务。

已有本地 ComfyUI 就连接它；希望使用云端模型，可以选择 OpenAI Images 或 Gemini。Pictide 不自带生图模型。使用 ComfyUI 时，需要分别启动两个应用。

旧版 Windows、Linux 和 macOS 便携包已通过原生构建与启动检查。新桌面分发方式见各平台指南，Mac 桌面体验仍待实机验证；云端服务真实出图尚待验证。

首次进入时，选择「带我看看」，跟着简短引导接入服务、探索图片。随时可以结束，也能在「设置 → 通用 → 新手引导」重新开始。

## 接入 ComfyUI

1. 启动 ComfyUI，确认已安装生图模型。
2. 在「设置 → 生图 API」添加 ComfyUI，填写地址，例如 `http://127.0.0.1:8188`（以实际端口为准）。
3. 使用「默认文生图」，读取并选择 checkpoint，测试连接后保存。

默认文生图适用于完整的 SD/SDXL checkpoint。准备好后进入「漫游」，点击「开始漫游」，等待第一张图片；喜欢或不喜欢都能帮助后续推荐贴近你的偏好。

### 自定义工作流

使用 Anima、Flux 等其他模型或自己的流程时，选择「自定义 API 工作流」，导入 ComfyUI 导出的 **API 格式 JSON**，指定正负提示词输入和图片输出节点，再保存。普通界面工作流 JSON 不能直接使用。

### 推荐使用的生图模型

想生成动漫和插画，推荐 [Anima Turbo v1.1](https://huggingface.co/circlestone-labs/Anima)。它支持 Danbooru 标签，只需 ComfyUI 内置节点。下载以下三个文件，合计约 **5.63 GB**，放入 ComfyUI 模型目录下对应的文件夹：

| 文件夹 | 文件 |
| --- | --- |
| `diffusion_models/` | [anima-turbo-v1.1.safetensors](https://huggingface.co/circlestone-labs/Anima/resolve/f973fc41ec7545364ac9776c2440285f43ff2a30/split_files/diffusion_models/anima-turbo-v1.1.safetensors) |
| `text_encoders/` | [qwen_3_06b_base.safetensors](https://huggingface.co/circlestone-labs/Anima/resolve/f973fc41ec7545364ac9776c2440285f43ff2a30/split_files/text_encoders/qwen_3_06b_base.safetensors) |
| `vae/` | [qwen_image_vae.safetensors](https://huggingface.co/circlestone-labs/Anima/resolve/f973fc41ec7545364ac9776c2440285f43ff2a30/split_files/vae/qwen_image_vae.safetensors) |

在「自定义 API 工作流」导入 [Anima Turbo API 工作流](../assets/workflows/anima-turbo-v1.1.api.json)，正向绑定 `11 → text`，负向绑定 `12 → text`，种子绑定 `19 → seed`，图片输出选择 `1 · Save Image`。默认参数为 **832×1248（2:3 竖图）、10 步、CFG 1、Euler / simple**；CFG 1 下负向提示词不参与引导。

模型采用[非商业许可](https://huggingface.co/circlestone-labs/Anima#license)，生成图片可商用。Windows 自动安装流程仍在设计中，目前按以上步骤手动准备。

## 接入 OpenAI Images 或 Gemini

1. 在「设置 → 生图 API」添加 API，选择 **OpenAI Images** 或 **Gemini**。
2. 填写 API Key、支持生图的模型 ID 和 Base URL。官方地址分别是 `https://api.openai.com/v1`、`https://generativelanguage.googleapis.com/v1beta`。
3. 测试连接并保存，再到「生成」页生成一张图片。连接测试不出图，也不产生生图费用；成功出图才说明账号与模型可用。

云端接入使用正向提示词；用于漫游的预设需将负向提示词留空。

图片、喜欢和偏好记录保存在本地，提示词与生成参数会发送给所选服务，并按服务商规则计费和处理数据。漫游首次切换到云端 API 时自动预取为 `0`；增加预取量会提前生成图片并产生费用，关闭预取时请求下一张仍会生成图片。

请求发出后，本地取消不能保证远端停止或免于计费。超时或结果不确定时，先查看服务商记录，再决定是否重试。

## 推荐依赖准备

首次启动会下载推荐依赖 MiniLM（约 **91 MB**）。保持启动窗口打开，下载与校验完成后才能进入应用。下载失败时，恢复网络后重新启动即可续传；下载完成后可离线复用。

<details>
<summary>离线首次启动：手动准备模型</summary>

在可联网的机器下载以下五个文件，保留文件名，放入所选[数据目录](backup.zh-CN.md#数据位置)的 `models/minilm/`，再启动 Pictide。版本和校验值见[模型清单](../../backend/recommand/model.json)。

- [model.onnx](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/d13954661f83248295ba75c1ed411eef3b7b936e/model.onnx)
- [tokenizer.json](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/d13954661f83248295ba75c1ed411eef3b7b936e/tokenizer.json)
- [config.json](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/d13954661f83248295ba75c1ed411eef3b7b936e/config.json)
- [tokenizer_config.json](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/d13954661f83248295ba75c1ed411eef3b7b936e/tokenizer_config.json)
- [special_tokens_map.json](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/d13954661f83248295ba75c1ed411eef3b7b936e/special_tokens_map.json)

</details>

## 从源码开始

源码运行需要 Python 3.10+，首次还需构建前端并[添加词库](prompts.zh-CN.md#添加与切换词库)。按系统准备：[Windows](setup/windows.zh-CN.md#从源码准备) · [Linux](setup/linux.zh-CN.md#从源码准备) · [macOS](setup/macos.zh-CN.md#从源码准备)。
