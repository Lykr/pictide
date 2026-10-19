# macOS 安装与启动

[English](macos.md)

[安装与接入](../getting-started.md) · [文档导航](../../README.md)

先查看[启动前准备](../getting-started.md#启动前准备)，以下命令均在项目根目录的终端中执行。

## 便携版本

解压对应系统与 CPU 架构的发行包，双击 `start.command`。就绪后自动打开系统默认浏览器，关闭启动窗口或按 Ctrl+C 停止。个人数据保存在包内 data，下一次启动继续使用。

已提供本机构建与启动路径；原生运行尚待该系统验证。首次使用到[后端设置](../getting-started.md#接入-comfyui)连接 ComfyUI。启动参数支持 `--port`、`--data-dir`、`--lan` 和 `--no-browser`；桌面环境可自动打开浏览器，服务器环境通过终端显示的地址访问。

## 源码启动

已准备好前端的目录，双击 `start.command`。打开 http://127.0.0.1:8189 ，按 Ctrl+C 或关闭启动窗口停止应用。接下来[连接 ComfyUI](../getting-started.md#接入-comfyui)。

如果归档文件丢失了执行权限，先执行：

```bash
chmod +x start.sh start.command
```

启动器查找 `python3`，创建 `data/runtime/venv` 并安装后端依赖；没有合适 Python 时需先安装。需要指定 Python 时：

```bash
PICTIDE_PYTHON=/path/to/python3 ./start.command
```

## 从源码准备

详见[macOS 开发与构建](../../dev/setup/macos.md#从源码准备)。

## 端口与数据目录

```bash
./start.command --port 8191 --data-dir "$HOME/PictideData"
```

开发验证使用独立端口与数据：`./start.command --port 8191 --data-dir ./dev/verification/example/data`。`./start.command --help` 查看参数；数据目录选择规则见[数据位置](../backup.md#数据位置)。

## 局域网访问

```bash
./start.command --lan
```

使用本机的局域网 IP 访问。若系统防火墙询问是否允许 Python 接受传入连接，按可信局域网使用场景允许；脚本不会修改防火墙。手机访问与共享范围见[局域网与主屏幕应用](../access.md)。

## 构建便携包

详见[macOS 开发与构建](../../dev/setup/macos.md#构建便携包)。
