# Windows 安装与启动

[English](windows.md)

[安装与接入](../getting-started.zh-CN.md) · [用户文档](../../README.zh-CN.md)

## 便携版本

以下为新版便携包的启动方式；已有发行版沿用包内启动文件。

1. 解压便携包，双击 `Pictide.exe`。
2. 首次启动时确认数据保存位置，按引导准备生图服务。还没有服务？选择安装 **ComfyUI + Anima Turbo v1.1** 即可。
3. 等待准备完成，浏览器会自动打开。跟随应用内引导，开始漫游。

安装推荐模型后，生图服务和工作流会自动配置好。使用已有服务时，见[生图服务接入说明](../getting-started.zh-CN.md)。

关闭网页后，Pictide 会继续在系统托盘运行。右键托盘图标可重新打开、查看日志或退出；退出也会停止由 Pictide 启动的 ComfyUI。

<details>
<summary>本地安装要求与数据位置</summary>

引导会检查硬件，并在下载前展示预计体积和模型许可。Anima Turbo 自动准备需要 **8 GB 独立显存、16 GB 内存**容量档位；不满足或无法检测时，可连接已有生图服务。NVIDIA 安装与出图已验证，AMD、Intel 和 CPU 尚未实测。

图片、偏好及下载的生图资源保存在首次启动时选择的目录，默认是程序旁的 `data/`。选择程序目录之外的位置，删除程序时也能保留这些数据。

</details>

<details>
<summary>重新准备与终端启动</summary>

保留 `Pictide.exe` 与 `_internal/` 在同一目录。在便携包目录打开 PowerShell：

- 重新打开准备引导：先退出 Pictide，再运行 `.\Pictide.exe --setup`。更换目录后，旧数据留在原处，不会自动迁移。
- 使用终端运行：`.\Pictide.exe --cli`，按 Ctrl+C 停止。

`--cli` 与 `--no-browser` 默认跳过准备引导，需要时加上 `--setup`。

</details>

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
