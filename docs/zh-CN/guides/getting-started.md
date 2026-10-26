# 安装与接入

[English](../../guides/getting-started.md)

[用户文档](../index.md) · 下一步：[漫游](roam.md)

选一个生图服务，连接好后就能开始漫游，无需手动编写提示词。

## 启动前准备

下载并解压便携包，按系统启动：[Windows](setup/windows.md#便携版本) · [Linux](setup/linux.md#便携版本) · [macOS](setup/macos.md#便携版本)。便携包已带好运行环境和词库；首次启动还需下载下方的推荐依赖。

Windows 准备引导可下载 ComfyUI 与推荐的 Anima 模型，自动接入默认工作流；步骤见 [Windows 指南](setup/windows.md#便携版本)。生图模型按需下载，发行包保持轻量。

已有本地 ComfyUI，或希望使用 OpenAI Images、Gemini 云端服务时，在「设置 → 生图 API」接入。希望已有的本地 ComfyUI 随 Pictide 启停时，可在通用设置中开启[本地启动](settings.md#本地-comfyui-启停)。由 Pictide 安装的 Windows 环境保留原有自动启动行为。

旧版 Windows、Linux 和 macOS 便携包已通过原生构建与启动检查。新桌面分发方式见各平台指南，Mac 桌面体验仍待实机验证；云端服务真实出图尚待验证。

首次进入时，选择「带我看看」。已完成本地准备就直接引导点击「开始漫游」；还没接入服务时先引导配置。随时可以结束，也能在「设置 → 通用 → 新手引导」重新开始。

## 接入 ComfyUI

1. 启动 ComfyUI，确认已安装生图模型。
2. 在「设置 → 生图 API」添加 ComfyUI，填写地址，例如 `http://127.0.0.1:8188`（以实际端口为准）。
3. 使用「默认文生图」，读取并选择 checkpoint，测试连接后保存。

默认文生图适用于完整的 SD/SDXL checkpoint。准备好后进入「漫游」，点击「开始漫游」，等待第一张图片；喜欢或不喜欢都能帮助后续推荐贴近你的偏好。

### 自定义工作流

手动接入 Anima、Flux 等模型或自己的流程时，选择「自定义 API 工作流」，导入 ComfyUI 导出的 **API 格式 JSON**，指定正负提示词输入和图片输出节点，再保存。普通界面工作流 JSON 不能直接使用。通过 Pictide 准备的推荐模型已带好默认工作流与绑定。

### 推荐使用的生图模型

想生成动漫和插画，推荐 [Anima Turbo v1.1](https://huggingface.co/circlestone-labs/Anima)。它支持 Danbooru 标签，只需 ComfyUI 内置节点。Windows 本地准备会处理这些文件和工作流；手动安装时，下载以下三个文件，合计约 **5.63 GB**，放入 ComfyUI 模型目录下对应的文件夹：

| 文件夹 | 文件 |
| --- | --- |
| `diffusion_models/` | [anima-turbo-v1.1.safetensors](https://huggingface.co/circlestone-labs/Anima/resolve/f973fc41ec7545364ac9776c2440285f43ff2a30/split_files/diffusion_models/anima-turbo-v1.1.safetensors) |
| `text_encoders/` | [qwen_3_06b_base.safetensors](https://huggingface.co/circlestone-labs/Anima/resolve/f973fc41ec7545364ac9776c2440285f43ff2a30/split_files/text_encoders/qwen_3_06b_base.safetensors) |
| `vae/` | [qwen_image_vae.safetensors](https://huggingface.co/circlestone-labs/Anima/resolve/f973fc41ec7545364ac9776c2440285f43ff2a30/split_files/vae/qwen_image_vae.safetensors) |

在「自定义 API 工作流」导入 [Anima Turbo API 工作流](../../assets/workflows/anima-turbo-v1.1.api.json)，正向绑定 `11 → text`，负向绑定 `12 → text`，种子绑定 `19 → seed`，图片输出选择 `1 · Save Image`。默认参数为 **832×1248（2:3 竖图）、10 步、CFG 1、Euler / simple**；CFG 1 下负向提示词不参与引导。

模型采用[非商业许可](https://huggingface.co/circlestone-labs/Anima#license)，生成图片可商用。

## 接入 OpenAI Images 或 Gemini

1. 在「设置 → 生图 API」添加 API，选择 **OpenAI Images** 或 **Gemini**。
2. 填写 API Key、支持生图的模型 ID 和 Base URL。官方地址分别是 `https://api.openai.com/v1`、`https://generativelanguage.googleapis.com/v1beta`。
3. 测试连接并保存，再到「生成」页生成一张图片。连接测试不出图，也不产生生图费用；成功出图才说明账号与模型可用。

Danbooru 模式下，云端接入使用正向提示词，漫游预设需将负向提示词留空；自然语言模式可将回避要求合入正向描述。

图片、喜欢和偏好记录保存在本地，提示词与生成参数会发送给所选服务，并按服务商规则计费和处理数据。漫游首次切换到云端 API 时自动预取为 `0`；增加预取量会提前生成图片并产生费用，关闭预取时请求下一张仍会生成图片。

请求发出后，本地取消不能保证远端停止或免于计费。超时或结果不确定时，先查看服务商记录，再决定是否重试。

## 自然语言提示词

模型更适合自然语言描述时，在「设置 → LLM API」添加连接。可以配置 OpenAI 兼容文本 API 的 Base URL、模型 ID 和密钥，也可以选择「ChatGPT」并通过浏览器授权。API Key 连接的地址应包含 API 版本，例如 `https://api.openai.com/v1`；服务需支持 Chat Completions 和 JSON 输出。

然后在「设置 → 生图 API」选择「自然语言」提示词类型，选择已保存的 LLM API 并保存。多个生图 API 可以共用同一个 LLM 连接。

使用 ChatGPT 时，在运行 Pictide 的电脑上通过 localhost 地址登录，再读取并保存账号可用模型。符合条件的请求使用账号授权的套餐额度，图片仍交给生图 API 生成；可通过「管理用量」查看额度。账号或额度不可用时会暂停转换，不会自动改用付费 API。完成配置后，其他设备也能使用已保存的连接。

继续按原来的方式选择标签、预设和锚点即可，Pictide 会在生图前把它们转换成描述。在「提示词 → 预览」中选择该生图 API，可以查看标签和最终文本；文本仅供查看和复制。

所选概念会发送给文本服务，并可能产生额外用量或费用。漫游的「漂流」会重新组织描述，「顺流」要求尽量保留原句，「停泊」复用已准备好的文本。转换失败时不会提交图片任务，请检查服务后重试。描述和画面能否准确表达标签仍取决于所选模型。

选择「Danbooru」则直接使用标签，无需 LLM。

## 网络代理

互联网下载和生图服务会自动跟随系统 HTTP(S) 代理或代理环境变量。本机、私有 IP 和本地主机名直接连接。自定义内网域名可加入代理绕过列表或 `NO_PROXY`；没有配置代理时直接连接。Pictide 不会修改系统设置。macOS 下的 HTTPS 连接使用系统证书信任设置。

## 推荐依赖准备

首次启动会下载推荐依赖 MiniLM（约 **91 MB**）。保持启动窗口打开，下载与校验完成后才能进入应用。下载失败时，恢复网络后重新启动即可续传；下载完成后可离线复用。

<details>
<summary>离线首次启动：手动准备模型</summary>

在可联网的机器下载以下五个文件，保留文件名，放入所选[数据目录](backup.md#数据位置)的 `models/minilm/`，再启动 Pictide。版本和校验值见[模型清单](../../../backend/recommendation/model.json)。

- [model.onnx](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/d13954661f83248295ba75c1ed411eef3b7b936e/model.onnx)
- [tokenizer.json](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/d13954661f83248295ba75c1ed411eef3b7b936e/tokenizer.json)
- [config.json](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/d13954661f83248295ba75c1ed411eef3b7b936e/config.json)
- [tokenizer_config.json](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/d13954661f83248295ba75c1ed411eef3b7b936e/tokenizer_config.json)
- [special_tokens_map.json](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/d13954661f83248295ba75c1ed411eef3b7b936e/special_tokens_map.json)

</details>

## 从源码开始

源码运行需要 Python 3.10+，首次还需构建前端并[添加词库](prompts.md#添加与切换词库)。按系统准备：[Windows](setup/windows.md#从源码准备) · [Linux](setup/linux.md#从源码准备) · [macOS](setup/macos.md#从源码准备)。
