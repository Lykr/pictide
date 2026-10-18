# Windows 安装与启动

[安装与接入](../getting-started.md) · [文档导航](../../README.md)

先查看[启动前准备](../getting-started.md#启动前准备)，以下命令均在项目根目录的 PowerShell 中执行。

## 便携版本

解压对应系统与 CPU 架构的发行包，双击 `start.cmd`。就绪后自动打开系统默认浏览器，关闭启动窗口或按 Ctrl+C 停止。个人数据保存在包内 data，下一次启动继续使用。

Windows 真实便携产物已验证。首次使用到[后端设置](../getting-started.md#接入-comfyui)连接 ComfyUI。启动参数支持 `--port`、`--data-dir`、`--lan` 和 `--no-browser`；桌面环境可自动打开浏览器，服务器环境通过终端显示的地址访问。

## 源码启动

已准备好前端的目录，双击 `start.cmd`。打开 http://127.0.0.1:8189 ，按 Ctrl+C 或关闭启动窗口停止应用。接下来[连接 ComfyUI](../getting-started.md#接入-comfyui)。

启动器会创建 `data/runtime/venv` 并安装后端依赖，也会尝试寻找本机已有的 Codex Python 运行时。需要指定 Python 时：

```powershell
$env:PICTIDE_PYTHON = 'C:\Path\To\python.exe'
.\start.cmd
```

## 从源码准备

详见[Windows 开发与构建](../../../dev/docs/setup/windows.md#从源码准备)。

## 端口与数据目录

```powershell
.\start.cmd -Port 8191 -DataDir 'E:\PictideData'
```

开发验证使用独立端口与数据：`.\start.cmd -Port 8191 -DataDir .\dev\verification\example\data`。数据目录选择规则见[数据位置](../backup.md#数据位置)。

## 局域网访问

```powershell
.\start.cmd -Lan
```

启动窗口会列出本机局域网地址。Windows 网络需为可信的“专用网络”；如需放行防火墙，在管理员 PowerShell 执行：

```powershell
New-NetFirewallRule -Name 'Pictide-LAN-8189' -DisplayName 'Pictide LAN (8189)' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8189 -Profile Private -RemoteAddress LocalSubnet
```

使用其他端口时同步修改规则。手机访问与共享范围见[局域网与主屏幕应用](../access.md)。

## 构建便携包

详见[Windows 开发与构建](../../../dev/docs/setup/windows.md#构建便携包)。
