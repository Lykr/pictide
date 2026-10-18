# 开箱即用的便携发行包

## 概述

将程序、运行依赖、前端、精简词库和 MiniLM 一起交付，让用户解压后双击启动，达到能够完整漫游的就绪状态。

目录式便携发行方案已确认，按下述接口实施。词库上传与选择已完成，详见[词库管理](library-selection.md)。

## 架构

```mermaid
flowchart TD
    Build["scripts/build_portable.py：构建发行包"] --> Program["PyInstaller 程序与依赖"]
    Build --> Assets["已构建前端 / 干净词库 / MiniLM / 资源清单"]
    Program --> Package["各系统便携目录与压缩包"]
    Assets --> Package
    Package --> Entry["平台启动入口"]
    Entry --> Host["现有 Host：路径 / HTTP / 生命周期"]
    Host --> Init["应用编排：首次资源初始化"]
    Init --> Data[("用户所选 data")]
    Host --> Browser["就绪后打开浏览器"]
```

## 职责边界

| 组成 | 接口及职责 |
| --- | --- |
| 发行构建 `scripts/build_portable.py` | `python scripts/build_portable.py --source-data-dir PATH --output-dir PATH`：读取源数据目录中当前选中的词库与 MiniLM，导出干净资源，打包当前已构建前端和后端，生成便携目录及 ZIP；输出目录使用新目录。 |
| 平台启动入口 | Windows 双击 `start.cmd`；Linux 执行 `start.sh`；macOS 双击 `start.command`。入口仅运行随包程序并传递参数。 |
| Host 启动 | 沿用 `--port`、`--data-dir`、`--host`；增加 `--lan` 作为局域网入口、`--no-browser` 用于验证。便携启动默认就绪后打开浏览器，源码入口保留现有默认行为。 |
| 应用编排初始化 | 新增 `PictideApplication.prepare_startup(paths, seed_dir)`：在服务组装前补齐所选数据目录中缺失的默认词库和模型；预设复用候选模块现有默认值。已有个人预设、所选词库、模型和业务数据保留。 |
| 数据路径 `DataPaths` | 便携程序默认使用发行目录下的 `data/`，与当前工作目录无关；显式路径和环境变量继续按[数据目录约定](../data-layout.md#数据位置)生效。 |
| 资源清单 | 记录种子资源的相对路径、大小、SHA-256 与来源版本，供构建校验和定位资源问题；启动检查所需文件齐备。 |

Windows 发行目录示意：

```text
Pictide/
  start.cmd
  data/
    runtime/pictide/
      Pictide.exe
      _internal/                  Python 与运行依赖
        web/dist/                 前端成品
        resources/                默认词库、固定版本 MiniLM、资源清单
    libraries/                    首次启动生成，可替换词库
    cache/embeddings/             首次启动生成，离线 MiniLM
    candidate.sqlite3             首次启动生成，个人预设与选择
    pictide.sqlite3                首次启动生成，业务数据
```

- 随包词库仅含 `tags/correlations/dataset` 和索引，默认使用当前精简版；推荐模型只导出当前编码器实际需要的 ONNX、tokenizer 配套文件及快照引用。
- 发行资源与个人数据分开，包内种子用于首次初始化和指定新数据目录；后续启动沿用用户已有资源。压缩包包含种子，个人运行副本在首次启动时生成。
- 前端依赖安装、构建和 PyInstaller 安装属于开发构建流程；所需打包依赖统一列在 `backend/requirements-release.txt`。
- 发行导出读取统计与模型，个人后端配置、密钥、图片、评价和偏好留在本地数据目录。
- HTTP 接口保持现有契约；候选、推荐与任务继续由应用编排协调。ComfyUI 和生图模型由用户配置。

## 调用和数据流

```mermaid
sequenceDiagram
    participant Dev as 发行构建
    participant Source as 源词库 / 模型 / 前端成品
    participant Package as 便携目录与 ZIP
    actor User as 用户
    participant Host as Host
    participant App as 应用编排
    participant Data as 所选 data
    Dev->>Source: 读取资源，导出干净统计与所需模型文件
    Dev->>Package: 打包程序、依赖、页面和种子资源
    User->>Host: 解压后运行平台启动入口
    Host->>Host: 解析数据目录与启动参数
    Host->>App: prepare_startup(paths, seed_dir)
    App->>Data: 补充缺失资源，保留个人配置与选择
    App-->>Host: 初始化完成
    Host->>Host: 组装现有服务并开始监听
    Host->>User: 打开浏览器
    opt 首次配置生图后端
        User->>Host: 现有后端设置与连接检查
        Host-->>User: 后端可用，具备漫游条件
    end
```

## 重点关注

- 验收终点是应用、前端、词库和推荐模型就绪，连接可用 ComfyUI 后能够开始完整漫游。
- Windows 优先验证真实产物：从新的解压目录运行程序，确认随包依赖、候选生成、离线 MiniLM 编码和页面资源可用；记录 ZIP 体积、解压占用与启动耗时。
- 少数冒烟覆盖首次启动、再次启动、带空格的移动路径、自定义数据目录和已有个人配置保留；验证实例使用独立端口与数据。
- Linux/macOS 按系统与 CPU 架构在本机构建；分别维护启动说明，原生运行结果按实际验证状态记录。
- 发行依赖的第三方许可证与现有前端声明随包保留。用户操作集中在获取、解压、启动和首次后端配置。
- 源码启动脚本继续用于开发，发布完成后同步 [README](../../README.md) 与各系统[安装路径](../guides/getting-started.md)。

参考：[PyInstaller 打包方式](https://pyinstaller.org/en/stable/operating-mode.html)。

交付与验证（2026-10-19）：

- Windows x64 目录式程序及 ZIP 已构建，产物位于 `data/releases/portable-compact-20261019/`。ZIP 为 154,793,286 B（147.6 MiB），解压目录为 257,461,991 B（245.5 MiB）；首次运行另生成约 110 MiB 的词库与模型工作副本。
- 三项冒烟通过：干净资源导出与已有数据保留、便携默认路径、服务就绪后打开浏览器；实际解压程序通过页面资源、候选、MiniLM 编码与推荐评分验证。
- 在本机已缓存磁盘条件下，新数据目录初始化至 bootstrap 响应约 1.04 秒，再次启动约 0.62 秒，移动目录后约 1.13 秒；该时间包含资源准备和服务就绪，浏览器展示及首次模型推理另计。
- 验证采用独立数据和端口，只配置测试生图地址；真实 GPU 生图和 Linux/macOS 原生运行未执行。报告与日志保存在 `data/verification/portable-startup-20261019/`。
