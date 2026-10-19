# Windows 安装与启动

[English](windows.md)

[安装与接入](../getting-started.zh-CN.md) · [用户文档](../../README.zh-CN.md)

## 便携版本

以下启动方式适用于当前源码及据此新构建的便携包。

解压 Windows 便携包，双击 `start.cmd`。临时窗口会显示启动进度，首次启动时包含[推荐模型下载](../getting-started.zh-CN.md#推荐模型启动准备)。就绪后启动进程退出，自动打开浏览器，服务通过系统托盘运行，不保留服务终端窗口；启动失败时保留错误提示。接下来[连接生图服务](../getting-started.zh-CN.md)，开始漫游。

关闭网页后程序继续运行。通过托盘菜单可以重新打开 Pictide、查看日志或退出。启动提示与托盘菜单跟随系统语言，支持简体中文和英文。个人数据保存在包内 `data/`。

希望保留终端时，运行 `.\start.cmd --cli`，按 Ctrl+C 停止。

## 局域网访问

在便携包目录打开 PowerShell，运行：

```powershell
.\start.cmd --lan
```

手机连接同一个局域网，打开启动日志中的局域网地址；通过托盘菜单「查看日志」可以找到日志。Windows 网络需设为可信的「专用网络」。连接被防火墙拦截时，在管理员 PowerShell 放行：

```powershell
New-NetFirewallRule -Name 'Pictide-LAN-8189' -DisplayName 'Pictide LAN (8189)' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8189 -Profile Private -RemoteAddress LocalSubnet
```

使用其他端口时同步修改规则。手机主屏幕安装见[局域网与主屏幕应用](../access.zh-CN.md)。

## 端口与数据目录

需要换端口或把数据放到其他磁盘时，在便携包目录运行：

```powershell
.\start.cmd --port 8191 --data-dir 'E:\PictideData'
```

## 从源码准备

先按[Windows 源码准备](../../dev/setup/windows.md#从源码准备)安装环境并构建前端，再在项目目录运行 `.\start.cmd`。

源码启动器的参数使用 `-Lan`、`-Port` 和 `-DataDir`，例如 `.\start.cmd -Lan -Port 8191 -DataDir 'E:\PictideData'`；加 `-Cli` 保留终端。构建发行包见[开发文档](../../dev/setup/windows.md#构建便携包)。
