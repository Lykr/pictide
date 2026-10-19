# macOS 安装与启动

[English](macos.md)

[安装与接入](../getting-started.zh-CN.md) · [用户文档](../../README.zh-CN.md)

## 便携版本

解压与 Mac 芯片匹配的便携包，双击 `start.command`。首次启动等待[推荐依赖下载](../getting-started.zh-CN.md#推荐依赖准备)，完成后自动打开浏览器。接下来[连接生图服务](../getting-started.zh-CN.md)，开始漫游。

保持启动终端打开，按 Ctrl+C 停止。个人数据保存在包内 `data/`，下次启动会继续使用。

首次启动时，macOS 可能分别要求允许 `start.command` 和内部的 `Pictide` 程序。便携版目前尚未使用 Developer ID 签名和 Apple 公证。确认下载来自本仓库后，可按 Apple 的[“仍要打开”说明](https://support.apple.com/zh-cn/102445)分别允许被拦截的入口。

## 局域网访问

在便携包目录打开终端，运行：

```bash
./start.command --lan
```

手机连接同一个局域网，打开电脑的局域网地址，例如 `http://192.168.50.50:8189`。若防火墙询问是否允许传入连接，按可信局域网使用场景允许。手机主屏幕安装见[局域网与主屏幕应用](../access.zh-CN.md)。

## 端口与数据目录

需要换端口或把数据放到其他位置时：

```bash
./start.command --port 8191 --data-dir "$HOME/PictideData"
```

## 从源码准备

先按[macOS 源码准备](../../dev/setup/macos.md#从源码准备)安装环境并构建前端，再在项目目录双击 `start.command`；局域网、端口和数据目录参数同上。

源码启动需要 Python 3.10+。若源码启动脚本缺少执行权限，在项目目录运行 `chmod +x start.sh start.command`。构建发行包见[开发文档](../../dev/setup/macos.md#构建便携包)。
