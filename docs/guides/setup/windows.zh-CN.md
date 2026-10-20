# Windows 安装与启动

[English](windows.md)

[安装与接入](../getting-started.zh-CN.md) · [用户文档](../../README.zh-CN.md)

## 便携版本

以下步骤适用于当前源码新构建的发行包；已有发行版本沿用原启动方式。

解压 Windows 便携包，双击 `Pictide.exe`。首次启动的终端引导会询问：已有生图 API、安装本地 ComfyUI，还是稍后配置。本地准备会显示检测到的显卡型号并推荐运行环境，也可以手动选择其他环境。随后可选择 **ComfyUI + Anima Turbo v1.1**，或只安装 ComfyUI。下载前会展示预计下载体积、所需磁盘空间、位置和模型许可；中断后可续传。

安装推荐模型后，默认工作流会自动接入。浏览器打开后选择「带我看看」，直接点击「开始漫游」生成第一张图片；「生成」页也已准备好。选择已有服务、稍后配置或仅安装 ComfyUI 时，按需跟随[生图服务接入说明](../getting-started.zh-CN.md)完成配置。

每个模型在下载前都会显示并检查硬件要求。Anima Turbo 当前自动准备门槛为 **8 GB 独立显存、16 GB 内存**容量档位；不满足或无法检测时会阻止模型下载。仍可只准备 ComfyUI，或连接已有生图服务。

临时窗口显示下载和启动进度，首次还包含[推荐依赖下载](../getting-started.zh-CN.md#推荐依赖准备)。就绪后窗口关闭，Pictide 通过系统托盘运行；启动失败时保留错误提示。NVIDIA 安装与真实出图已验证，AMD、Intel 和 CPU 选项尚未在对应硬件实测；CPU 生图速度较慢。

关闭网页后程序继续运行。通过托盘菜单可以重新打开 Pictide、查看日志或退出；退出时也会停止由 Pictide 启动的 ComfyUI。启动提示与托盘菜单跟随系统语言，支持简体中文和英文。个人数据与下载的本地生图资源保存在包内 `data/`。

请将 `Pictide.exe` 与 `_internal/` 放在一起。希望使用终端时，运行 `.\Pictide.exe --cli`，按 Ctrl+C 停止。

需要重新准备时，先退出 Pictide，在便携包目录打开 PowerShell，运行 `.\Pictide.exe --setup`；已有生图 API 会保留。`--cli` 与 `--no-browser` 启动默认不提问，显式添加 `--setup` 才进入准备引导。

## 局域网访问

在便携包目录打开 PowerShell，运行：

```powershell
.\Pictide.exe --lan
```

手机连接同一个局域网，打开启动日志中的局域网地址；通过托盘菜单「查看日志」可以找到日志。Windows 网络需设为可信的「专用网络」。连接被防火墙拦截时，在管理员 PowerShell 放行：

```powershell
New-NetFirewallRule -Name 'Pictide-LAN-8189' -DisplayName 'Pictide LAN (8189)' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8189 -Profile Private -RemoteAddress LocalSubnet
```

使用其他端口时同步修改规则。手机主屏幕安装见[局域网与主屏幕应用](../access.zh-CN.md)。

## 端口与数据目录

需要换端口或把数据放到其他磁盘时，在便携包目录运行：

```powershell
.\Pictide.exe --port 8191 --data-dir 'E:\PictideData'
```

## 从源码准备

先按[Windows 源码准备](../../dev/setup/windows.md#从源码准备)安装环境并构建前端，再在项目目录运行 `.\start.cmd`。

源码启动器的参数使用 `-Lan`、`-Port` 和 `-DataDir`，例如 `.\start.cmd -Lan -Port 8191 -DataDir 'E:\PictideData'`；加 `-Cli` 保留终端。构建发行包见[开发文档](../../dev/setup/windows.md#构建便携包)。
