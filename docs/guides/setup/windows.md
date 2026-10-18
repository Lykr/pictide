# Windows 安装与启动

[安装与接入](../getting-started.md) · [文档导航](../../README.md)

先查看[启动前准备](../getting-started.md#启动前准备)，以下命令均在项目根目录的 PowerShell 中执行。

## 启动

已准备好前端的目录，双击 `start.cmd`。打开 http://127.0.0.1:8189 ，按 Ctrl+C 或关闭启动窗口停止应用。接下来[连接 ComfyUI](../getting-started.md#接入-comfyui)。

启动器会创建 `data/runtime/venv` 并安装后端依赖，也会尝试寻找本机已有的 Codex Python 运行时。需要指定 Python 时：

```powershell
$env:PICTIDE_PYTHON = 'C:\Path\To\python.exe'
.\start.cmd
```

## 从源码准备

首次检出源码时，先准备[开发环境要求](../../development.md#首次准备检出目录)中的 Node.js 和 pnpm，再构建前端：

```powershell
$projectData = Join-Path (Get-Location) 'data'
New-Item -ItemType Directory -Path "$projectData\tmp" -Force | Out-Null
$env:TEMP = "$projectData\tmp"
$env:TMP = $env:TEMP
Push-Location web
pnpm install --frozen-lockfile
pnpm run typecheck
pnpm run build
Pop-Location
.\start.cmd
```

启动时自动准备 Python 环境，无需在系统 Python 中安装应用依赖。

## 端口与数据目录

```powershell
.\start.cmd -Port 8191 -DataDir 'E:\PictideData'
```

开发验证使用独立端口与数据：`.\start.cmd -Port 8191 -DataDir .\data`。数据目录选择规则见[数据位置](../../data-layout.md#数据位置)。

## 局域网访问

```powershell
.\start.cmd -Lan
```

启动窗口会列出本机局域网地址。Windows 网络需为可信的“专用网络”；如需放行防火墙，在管理员 PowerShell 执行：

```powershell
New-NetFirewallRule -Name 'Pictide-LAN-8189' -DisplayName 'Pictide LAN (8189)' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8189 -Profile Private -RemoteAddress LocalSubnet
```

使用其他端口时同步修改规则。手机访问与共享范围见[局域网与主屏幕应用](../access.md)。
