# Linux 安装与启动

[English](../../../guides/setup/linux.md)

[安装与接入](../getting-started.md) · [用户文档](../../index.md)

## 便携版本

解压 Linux 便携包，在解压目录打开终端并运行：

```bash
./start.sh
```

首次启动等待[推荐依赖下载](../getting-started.md#推荐依赖准备)，完成后自动打开浏览器；也可访问 `http://127.0.0.1:8189`。接下来[连接生图服务](../getting-started.md)，开始漫游。

保持终端打开，按 Ctrl+C 停止。个人数据保存在包内 `data/`，下次启动会继续使用。

## 局域网访问

在便携包目录运行：

```bash
./start.sh --lan
```

手机连接同一个局域网，打开电脑的局域网地址，例如 `http://192.168.50.50:8189`。如已启用防火墙，允许可信局域网访问对应端口。手机主屏幕安装见[局域网与主屏幕应用](../access.md)。

## 端口与数据目录

需要换端口或把数据放到其他位置时：

```bash
./start.sh --port 8191 --data-dir "$HOME/PictideData"
```

## 从源码准备

先按[Linux 源码准备](../../dev/setup/linux.md#从源码准备)安装环境并构建前端，再在项目目录运行 `bash start.sh`；局域网、端口和数据目录参数同上。

启动器需要 Python 3.10+。Debian / Ubuntu 若提示缺少 venv，安装与 Python 版本匹配的 `python3-venv`。构建发行包见[开发文档](../../dev/setup/linux.md#构建便携包)。
