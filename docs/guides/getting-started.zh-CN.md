# 安装与接入

[English](getting-started.md)

[文档导航](../README.zh-CN.md) · 下一步：[提示词](prompts.zh-CN.md) / [漫游](roam.zh-CN.md)

本页说明便携版与源码版的启动准备和生图后端接入。可以连接本地 ComfyUI、OpenAI Images 或 Gemini 原生生图。

## 启动前准备

便携版随包提供程序、前端、精简词库和推荐推理依赖，MiniLM 模型文件在首次启动前下载。解压后运行对应系统的启动入口即可，详见 [Windows](setup/windows.zh-CN.md#便携版本) · [Linux](setup/linux.zh-CN.md#便携版本) · [macOS](setup/macos.zh-CN.md#便携版本)。

源码版需要 Python 3.10+；新检出的源码还需要先构建前端，Node.js 与 pnpm 版本见[开发环境要求](../dev/development.md#首次准备检出目录)。已准备好前端的目录日常运行不需要 Node.js 服务。

源码启动器自动准备所选数据目录下的 Python 环境、依赖与缓存。源码版与便携版都先完成下文的 MiniLM 准备，再启动 HTTP 服务和打开页面。生图模型由所选生图服务提供。不同系统分别创建源码运行环境。Linux/macOS 原生 CI 构建与启动验证待实际运行。

## 推荐模型启动准备

首次启动时，Pictide 将下载约 91 MB 的 MiniLM 模型文件到所选数据目录的 `models/minilm/`（默认 `data/models/minilm/`）。保持启动窗口打开，查看下载进度。所有必需文件通过大小与 SHA-256 校验后，才启动 HTTP 服务并允许打开应用页面；下载属于进入应用前的启动准备。

下载失败时终止启动，终端显示错误。恢复网络后重新运行同一启动器即可；中断下载的 `.part` 文件会保留，下次续传。完整且校验有效的本地模型直接离线复用，日常缓存清理保留模型目录。

需要离线首次启动时，在可联网的机器下载以下五个文件，保留文件名，直接放入所选数据目录的 `models/minilm/`。固定版本和校验值以[模型清单](../../backend/recommand/model.json)为准，使用这里的固定快照链接：

- [model.onnx](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/d13954661f83248295ba75c1ed411eef3b7b936e/model.onnx)
- [tokenizer.json](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/d13954661f83248295ba75c1ed411eef3b7b936e/tokenizer.json)
- [config.json](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/d13954661f83248295ba75c1ed411eef3b7b936e/config.json)
- [tokenizer_config.json](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/d13954661f83248295ba75c1ed411eef3b7b936e/tokenizer_config.json)
- [special_tokens_map.json](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx/resolve/d13954661f83248295ba75c1ed411eef3b7b936e/special_tokens_map.json)

## 按系统安装与启动

选择当前系统，沿对应页面完成启动、源码准备、自定义参数与局域网配置：

- [Windows](setup/windows.zh-CN.md)
- [Linux](setup/linux.zh-CN.md)
- [macOS](setup/macos.zh-CN.md)

启动完成后，选择下面的生图后端。使用 ComfyUI 时，两个应用分别启动、停止，没有自启动或常驻服务。

## 接入 OpenAI Images 或 Gemini

1. 打开「设置 → 生图 API」，添加 API 并选择 **OpenAI Images** 或 **Gemini**。
2. 填写名称、包含版本路径的 API Base URL、API Key 和支持图片输出的模型 ID。官方服务分别使用 `https://api.openai.com/v1`、`https://generativelanguage.googleapis.com/v1beta`。模型 ID 需要明确填写，Pictide 不自动选择或下载云端模型。
3. 按所选模型支持的值，选填 OpenAI 的尺寸和质量，或 Gemini 的宽高比和图像尺寸。留空使用服务默认值。
4. 测试连接并保存。检查只查询所选模型，不提交生图，也不能确认账号具有生图权限；准备好后，在「生成」页提交一个小量手动请求验证出图。

OpenAI 使用 `/images/generations`，Gemini 使用 `/interactions` 单轮图片输出。本次接入不包含 Gemini `generateContent`、Imagen、图片编辑和多轮对话。自定义 Base URL 可用于相同端点的服务，但模型、字段和图片返回格式需逐项验证；路径与 OpenAI 相同本身不能证明完整兼容。

这两个适配器接收正向提示词，不支持负向提示词和确定的图像种子；「生成」页会反映可用能力。候选生成与漫游需要选择或新建负向提示词为空的预设；非空负向提示词会明确报错，包括预设产生的负向内容。候选种子仍在本地控制抽词，不控制云端图像的随机性。标签提示词和锚点按原文发送，效果由所选模型决定。

图片、提示词记录、喜欢和学习偏好保存在本地；提示词及生成参数会发送给所选服务，计费和数据处理遵循服务约定。漫游切换到新的云端后端时，自动预取先设为 `0`；明确增加数量后，才通过原有浏览事件开启付费后台生成。预取关闭时，向右请求缺失的下一张仍会生成一张。

云端生成等待完整 HTTP 响应，再将 Base64 或下载的图片保存到数据目录。请求发出后，本地取消不能保证远端停止或免于计费。提交超时或应用在记录响应前停止时，任务保持结果不确定，不会自动重发；发起新请求前请先检查服务商记录。

协议模拟验证覆盖接入行为；收费官方服务及第三方兼容端点的真实出图仍未验证。只读连接检查与成功出图是两项不同的验证。

## 接入 ComfyUI

1. 启动 ComfyUI，打开 Pictide「设置 → 生图 API」，填写API 名称和实际地址，例如 `http://127.0.0.1:8188`。Desktop 的实际端口可能不同。
2. 保持“默认文生图”，读取并选择已安装的 checkpoint；留空自动使用列表中第一个模型，无需导入工作流或绑定输入。
3. 测试连接并保存；完成词库与推荐模型准备后，进入「漫游」点击「开始漫游」，查看首图、表达偏好并切换下一张。需要验证手动文本生图时，也可在「生成」页提交提示词。

内置工作流使用 ComfyUI 自带节点，适用于兼容 SD/SDXL 的完整 checkpoint，默认 832×1216、16 步、CFG 2.5、DPM++ 2M / Karras、denoise 1。不会下载模型；Flux 等其他模型架构请使用对应的自定义工作流。

### 自定义工作流

需要自定义流程时，切换“自定义 API 工作流”，导入 **API 格式** JSON，选择正负文本、可选种子和图片输出节点。普通包含 `nodes` 数组的界面工作流不适用。清空自定义工作流会回退默认文生图；已有非空工作流保留为自定义。

设置中的「工作流」将名称输入与下拉选择合并：可选默认文生图、已保存工作流或自定义 API 工作流，也可直接输入名称并筛选已有项。选择已有项后修改输入文字就是重命名，保留原 ID；选择自定义项会填写可修改的默认名称，并避免与已有名称重复。点击「保存 API」同时保存模板到 `data/workflows` 并应用到后端，无需单独另存或应用。保存时核对读取的修订号，外部修改冲突会保留草稿并阻止覆盖。新建自定义工作流时，同名同内容复用已有模板，同名不同内容拒绝保存。模板更新前的版本保存在 `data/workflows/.backups`。

工作流更新应用于本次保存的后端，其他后端保留各自已保存的工作流快照；重新选择工作流并保存可应用最新版。已有任务始终使用提交时的后端配置，不受后续编辑影响。

删除工作流会从选择列表移除并保留文件备份，同时解除当前后端对模板的引用；后端中已经应用的节点、绑定和输出快照保留，可以继续生成。删除后端只移除当前可选配置，原配置修订、历史任务、图片和评价保留；已提交任务继续使用原配置执行。删除操作不会清理图片或 ComfyUI 数据，恢复说明见 [数据目录](backup.zh-CN.md)。

默认文生图的「节点参数」可展开为自定义草稿，支持模型、尺寸、批次数、采样步数、CFG、采样器、调度器和降噪等普通输入；连线保持不变。API 工作流 JSON 默认折叠，展开后可编辑或导入 API JSON，普通参数编辑与 JSON 使用同一草稿。

### 提示词与图片记录

导入前请将工作流中的随机提示词生成节点替换为固定文本输入。平台把最终文本注入绑定的输入，工作流应将这些文本直接送入文本编码器，并保持输出提示词记录使用同一文本来源。不要在下游再次随机或改写文本，否则记录无法准确代表编码器实际输入。

ComfyUI 只执行生图 API，不再安装提示词生成、预览或提示词保存节点。工作流使用原生 PreviewImage / SaveImage 等图像输出，图片及对应的正负提示词 JSON 由 Pictide 保存。旧工作流如含已移除的 RulePrompt 节点，需要替换为原生文本输入和图像输出后再导入。

### 任务执行与检查

多个后端可分别保存。修改某个后端的地址或工作流后，旧任务继续使用提交时的后端配置，防止任务和图片指向错误的服务。新任务先订阅 ComfyUI 结束事件，再提交生图；全应用最多两个任务在途，通常一个出图、一个在 ComfyUI 排队；收到通知后通过 HTTP 核实，先补入下一项，再保存图片。通知不可用时自动回到轮询，详见 [任务事件通知](../dev/issues/task-events.md) 和 [提交窗口](../dev/issues/task-window.md)。生成完成后，Feed 将图片复制到 `data/images`，并保存同名 JSON，仅包含实际提交的正负提示词；不保存配置或额外 TXT。已保存图片可以在 ComfyUI 关闭后浏览。升级前的历史图片首次访问时补存，需要对应后端图片仍可读取。ComfyUI 自己的 output/temp 文件仍由 ComfyUI 管理。

测试连接执行只读预检，能发现常见的缺模型、缺输入图、连接或枚举错误；不提交生图，也不替代 ComfyUI 自定义节点的正式校验。HTTP 400 会展示可识别的节点及输入原因。

## 从源码开始

新检出仓库没有依赖、词库、推荐模型或前端构建产物。先按[开发流程](../dev/development.md#首次准备检出目录)安装和构建；词库导入见[提示词指南](prompts.zh-CN.md#数据准备)，推荐模型准备见[推荐模型启动准备](#推荐模型启动准备)。数据路径和备份见[数据目录](backup.zh-CN.md)。
